// Crawler for "The Weight of Surveillance".
// Visits each site in three consent states (none / accept / reject) and records every request.
//
// Timeline of one visit (all modes):
//   load page -> settle -> PRE snapshot (banner? bot block? pay-or-okay? cookies)
//   -> consent action (accept/reject only) -> verify banner closed -> t0
//   -> observation WINDOW of fixed length with scrolling -> END snapshot
// The main metrics use only requests that START inside the window, so all modes are observed equally long.
//
// Usage:
//   node crawl.mjs --sites sites_pilot.csv --out results --workers 3 --repeats 1
//   node crawl.mjs --mock            (offline self-test against fake sites)
//   options: --retry-failed --fresh --headed --window 30 --visit-timeout 150 --pause 3 --no-shuffle --restart-every 6
import fs from 'fs';
import path from 'path';
import { createRequire } from 'module';
import { chromium } from 'playwright';
import { classify, classifyCookie, cnameLookup, isCmpHost } from './classify.mjs';

const require = createRequire(import.meta.url);
const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, arr) => {
    if (a.startsWith('--')) acc.push([a.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : true]);
    return acc;
  }, []),
);

const OUT = args.out || 'results';
const WORKERS = Number(args.workers || 3);
const REPEATS = Number(args.repeats || 1);
const MODES = (args.modes || 'none,accept,reject').split(',');
const MOCK = Boolean(args.mock);
const SITES_FILE = args.sites || (MOCK ? null : 'sites_pilot.csv');

// Timings (ms). Reported in the methodology.
const T = {
  nav: 45000, load: 20000, settle: 4000, consentMax: 15000, verify: 2500,
  window: Number(args.window || 30) * 1000, op: 8000, visit: Number(args['visit-timeout'] || 150) * 1000,
};

// Resolves to `fallback` if `p` does not settle within `ms`. Nothing in a visit may wait forever.
const withTimeout = (p, ms, fallback = null) =>
  Promise.race([Promise.resolve(p).catch(() => fallback), new Promise((r) => setTimeout(() => r(fallback), ms))]);

const ACCEPT_RE = /^(alle(s)? (cookies )?(akzeptieren|annehmen|zulassen|erlauben)|(alle )?(cookies )?akzeptieren( und weiter| & weiter)?|(allem |allen )?zustimmen( und weiter| & weiter)?|alle(n)? zustimmen|(alle(n)? )?einwilligen( und weiter| & weiter)?|ich willige ein|einverstanden|ok(ay)?,? (verstanden|einverstanden)|accept( all)?( cookies)?|accept all cookies|agree( and continue)?|allow all( cookies)?|i agree)$/i;
const REJECT_RE = /^(alle(s)? (cookies )?ablehnen|(cookies )?ablehnen( und weiter)?|nicht einwilligen|ohne (einwilligung|zustimmung) (weiter|fortfahren)|weiter ohne (einwilligung|zustimmung)|nur (notwendige|erforderliche|essenzielle|technisch notwendige)( cookies)?( (akzeptieren|zulassen|verwenden|erlauben))?|reject( all)?( cookies)?|decline( all)?( cookies)?|necessary only|only necessary)$/i;
const CONSENT_WORDS = /(cookie|einwillig|zustimm|tracking|datenschutz|consent|partner|werbung|personalis)/i;
const PAY_OR_OKAY = /(werbefrei|ohne werbung|ohne werbetracking|pur[- ]?abo|jetzt abonnieren|abo abschließen|abonnieren|contentpass|ad-?free)/i;
const BOT_BLOCK = /(zugriff (auf .{0,40})?(wurde )?verweigert|aus sicherheitsgründen mussten wir|access denied|are you a robot|bist du ein mensch|sind sie ein mensch|verify you are human|unusual traffic|request blocked|pardon our interruption|just a moment|attention required|captcha)/i;

// Clicks the first visible button-like element (in any frame, including open shadow roots) whose label
// matches `re`. The label is the element text, its value, aria-label, title, or the text of aria-labelledby.
async function clickByText(page, re) {
  for (const frame of page.frames()) {
    const label = await withTimeout(frame.evaluate((src) => {
      const re = new RegExp(src, 'i');
      const SEL = 'button, [role=button], a, input[type=button], input[type=submit]';
      const roots = [document];
      const all = [];
      while (roots.length) {
        const root = roots.shift();
        all.push(...root.querySelectorAll(SEL));
        for (const el of root.querySelectorAll('*')) if (el.shadowRoot) roots.push(el.shadowRoot);
      }
      const labelOf = (el) => {
        const by = el.getAttribute('aria-labelledby');
        const byText = by ? by.split(/\s+/).map((id) => (el.getRootNode().getElementById?.(id) || document.getElementById(id))?.innerText || '').join(' ') : '';
        return [el.innerText, el.value, el.getAttribute('aria-label'), el.title, byText]
          .map((t) => (t || '').replace(/\s+/g, ' ').trim()).find((t) => t && t.length < 60 && re.test(t)) || null;
      };
      for (const el of all) {
        const r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) continue;
        const t = labelOf(el);
        if (t) { el.click(); return t; }
      }
      return null;
    }, re.source), T.op);
    if (label) return label;
  }
  return null;
}

// Looks for a visible consent dialog in the page and its first-level frames (autoconsent heuristics),
// and for bot-protection pages. Returns { banner, bannerText, payOrOkay, botBlocked }.
async function inspect(page) {
  const out = { banner: false, bannerText: null, payOrOkay: false, botBlocked: false };
  for (const frame of page.frames()) {
    const isMain = frame === page.mainFrame();
    // Consent iframes (Sourcepoint, consentmanager, ...) are recognised by host and on-screen size,
    // because the heuristics do not always see their content.
    let cmpFrame = false;
    if (!isMain) {
      let host = '';
      try { host = new URL(frame.url()).hostname; } catch {}
      // CMP iframes are recognised by host, or by the iframe's id/name/title, because some CMPs run on a
      // first-party subdomain (e.g. Sourcepoint on sp-*.site.de, iframe id "sp_message_iframe_...").
      const el = await withTimeout(frame.frameElement(), T.op);
      const attrs = el ? await withTimeout(el.evaluate((e) => `${e.id} ${e.name} ${e.title}`), T.op, '') : '';
      if (el && ((host && isCmpHost(host)) || /(sp_message|consent|cmp|cookie|privacy|gdpr|datenschutz)/i.test(attrs || ''))) {
        // CMPs often keep the iframe in the page after a choice and only hide it, so check real visibility:
        // size, position inside the viewport, and display/visibility/opacity of the iframe and its ancestors.
        const visible = await withTimeout(el.evaluate((e) => {
          const r = e.getBoundingClientRect();
          if (r.width < 100 || r.height < 100) return false;
          if (r.bottom <= 0 || r.right <= 0 || r.top >= innerHeight || r.left >= innerWidth) return false;
          for (let n = e; n && n.nodeType === 1; n = n.parentElement || n.getRootNode()?.host) {
            const cs = getComputedStyle(n);
            if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) < 0.05) return false;
          }
          return true;
        }), T.op, false);
        cmpFrame = Boolean(visible);
      }
    }
    const r = await withTimeout(frame.evaluate(([cw, isMain, cmpFrame]) => {
      const re = new RegExp(cw, 'i');
      let texts = (window.autoconsentHeuristics?.getPotentialPopups(1500) || []).map((p) => p.text || '').filter((t) => re.test(t));
      if (!texts.length && cmpFrame) texts = [(document.body?.innerText || '').slice(0, 2000)];
      // Banners inside open shadow roots (web components, e.g. arbeitsagentur.de) are invisible to the heuristics.
      if (!texts.length) {
        for (const host of document.querySelectorAll('*')) {
          if (!host.shadowRoot) continue;
          const r = host.getBoundingClientRect();
          const inner = [...host.shadowRoot.querySelectorAll('*')].find((e) => { const b = e.getBoundingClientRect(); return b.width > 200 && b.height > 80; });
          const t = (host.shadowRoot.textContent || '').replace(/\s+/g, ' ');
          if ((r.width > 200 || inner) && re.test(t) && /(akzeptier|ablehn|zustimm|einwillig|accept|reject)/i.test(t)) { texts = [t.slice(0, 2000)]; break; }
        }
      }
      const body = isMain ? `${document.title}\n${(document.body?.innerText || '').slice(0, 3000)}` : '';
      return { text: texts.join('\n').slice(0, 2000), body };
    }, [CONSENT_WORDS.source, isMain, cmpFrame]), T.op);
    if (!r) continue;
    if (r.text) { out.banner = true; out.bannerText = (out.bannerText || '') + r.text; }
    if (r.body && BOT_BLOCK.test(r.body)) out.botBlocked = true;
  }
  if (out.bannerText) {
    out.payOrOkay = PAY_OR_OKAY.test(out.bannerText);
    out.bannerText = out.bannerText.replace(/\s+/g, ' ').slice(0, 300);
  }
  return out;
}

async function cookieSnapshot(context, siteUrl) {
  const cookies = (await withTimeout(context.cookies(), T.op)) || [];
  const cls = cookies.map((c) => classifyCookie(c, siteUrl));
  return {
    total: cookies.length,
    thirdParty: cls.filter((c) => c.thirdParty).length,
    tracker: cls.filter((c) => c.tracker).length,
    firstPartyTracker: cls.filter((c) => c.tracker && !c.thirdParty).length,
    trackerOwners: [...new Set(cls.filter((c) => c.tracker).map((c) => c.owner))],
  };
}

const acDir = path.dirname(require.resolve('@duckduckgo/autoconsent'));
const autoconsentScript = fs.readFileSync(path.join(acDir, 'autoconsent.playwright.js'), 'utf8');
const autoconsentRules = JSON.parse(fs.readFileSync(path.join(acDir, '..', 'rules', 'rules.json'), 'utf8'));

function acConfig(mode) {
  return {
    enabled: true,
    autoAction: mode === 'accept' ? 'optIn' : mode === 'reject' ? 'optOut' : null,
    disabledCmps: [],
    enablePrehide: false,
    enableCosmeticRules: false, // real clicks, never hiding the banner with CSS
    enableGeneratedRules: true,
    detectRetries: 20,
    isMainWorld: false,
    prehideTimeout: 2000,
    enableHeuristicDetection: true,
    enablePopupMutationObserver: true,
    visualTest: false,
    performanceLoggingEnabled: false,
    heuristicPopupSearchTimeout: 3000,
    heuristicMode: 'tier2',
    logs: { lifecycle: false, rulesteps: false, detectionsteps: false, evals: false, errors: false, messages: false, waits: false },
  };
}

function loadSites() {
  if (MOCK) return [
    { url: 'https://www.beispiel-news.test/', category: 'mock' },
    { url: 'https://www.beispiel-abo.test/', category: 'mock' }, // pay-or-okay banner, autoconsent cannot opt in
    { url: 'https://www.beispiel-iframe.test/', category: 'mock' }, // banner inside a CMP iframe (like Sourcepoint)
    { url: 'https://www.beispiel-shadow.test/', category: 'mock' }, // banner in a shadow root, "Alle Cookies akzeptieren"
    { url: 'https://www.beispiel-input.test/', category: 'mock' }, // Amazon-style <input> buttons labelled elsewhere
    { url: 'https://www.beispiel-block.test/', category: 'mock' }, // bot protection page
    { url: 'https://www.haengt-loop.test/', category: 'mock-hang' }, // main thread blocked forever
  ];
  const lines = fs.readFileSync(SITES_FILE, 'utf8').trim().split('\n').slice(1);
  return lines.map((l) => {
    const [url, category] = l.split(',');
    return { url: url.trim(), category: (category || '').trim() };
  });
}

const adblockType = (req, page) => {
  const t = req.resourceType();
  if (t === 'document') return req.frame() === page.mainFrame() ? 'main_frame' : 'sub_frame';
  if (t === 'fetch') return 'xhr';
  return t;
};

async function visit(browser, ua, site, mode, rep, handle) {
  const visitId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const context = await browser.newContext({ locale: 'de-DE', timezoneId: 'Europe/Berlin', viewport: { width: 1366, height: 900 }, userAgent: ua });
  handle.context = context;
  if (MOCK) (await import('./mock.mjs')).installMock(context);

  const page = await context.newPage();
  page.on('dialog', (d) => d.dismiss().catch(() => {})); // alert()/confirm() would block every evaluate
  const cdp = await context.newCDPSession(page);
  await withTimeout(cdp.send('Performance.enable'), T.op);

  const start = Date.now();
  const now = () => Date.now() - start;
  const ac = { foundAt: null, cmp: null, popupFound: false, result: null, done: false, clicks: null, at: null, errors: [] };
  const requests = [];
  const pending = [];
  const startedAt = new WeakMap();
  let t0 = null; // start of the observation window
  let tEnd = null; // end of the observation window

  await page.exposeBinding('autoconsentSendMessage', async ({ frame }, msg) => {
    if (!msg || typeof msg !== 'object') return;
    const reply = (m) => withTimeout(frame.evaluate((x) => window.autoconsentReceiveMessage && window.autoconsentReceiveMessage(x), m), T.op);
    switch (msg.type) {
      case 'init':
        return reply({ type: 'initResp', config: acConfig(mode), rules: { autoconsent: autoconsentRules.autoconsent } });
      case 'eval':
        return reply({ type: 'evalResp', id: msg.id, result: await withTimeout(frame.evaluate(msg.code), T.op, false) });
      case 'cmpDetected': ac.cmp = ac.cmp || msg.cmp; break;
      case 'popupFound': ac.popupFound = true; ac.cmp = msg.cmp; ac.foundAt ??= now(); break;
      case 'optOutResult':
      case 'optInResult': ac.result = msg.result; break;
      case 'autoconsentDone': ac.done = true; ac.cmp = msg.cmp; ac.clicks = msg.totalClicks ?? null; ac.at = now(); break;
      case 'autoconsentError': ac.errors.push(String(msg.details?.msg || msg.details || 'error').slice(0, 200)); break;
    }
  });
  await context.addInitScript({ content: autoconsentScript });

  page.on('request', (req) => {
    startedAt.set(req, now());
    // start DNS resolution early for possible CNAME cloaking
    try { cnameLookup(new URL(req.url()).hostname, site.url); } catch {}
  });
  const record = (req, failed) => {
    pending.push((async () => {
      let sizes = { responseBodySize: 0, responseHeadersSize: 0, requestBodySize: 0, requestHeadersSize: 0 };
      let status = null;
      let mime = null;
      if (!failed) {
        sizes = (await withTimeout(req.sizes(), T.op)) || sizes;
        const r = await withTimeout(req.response(), T.op);
        status = r?.status() ?? null;
        mime = r ? await withTimeout(r.headerValue('content-type'), T.op) : null;
      }
      const ts = startedAt.get(req) ?? now();
      let host = '';
      try { host = new URL(req.url()).hostname; } catch {}
      const chain = (await withTimeout(cnameLookup(host, site.url), 3000, [])) || [];
      const c = classify(req.url(), site.url, adblockType(req, page), chain);
      requests.push({
        visitId, site: site.url, mode, rep, ts, phase: null, // phase is assigned at the end, once t0 is known
        url: req.url().slice(0, 500), type: req.resourceType(), status, mime: mime?.split(';')[0] ?? null, failed,
        bytes: Math.max(0, sizes.responseBodySize) + Math.max(0, sizes.responseHeadersSize),
        bodyBytes: Math.max(0, sizes.responseBodySize),
        upBytes: Math.max(0, sizes.requestBodySize) + Math.max(0, sizes.requestHeadersSize),
        ...c,
        cnameChain: chain.length ? chain : undefined,
      });
    })());
  };
  page.on('requestfinished', (r) => record(r, false));
  page.on('requestfailed', (r) => record(r, true));

  // 1. Load. 'load' that never fires is not fatal: the page is measured and flagged.
  let navError = null, mainStatus = null, loadTimeout = false;
  try {
    const resp = await page.goto(site.url, { waitUntil: 'domcontentloaded', timeout: T.nav });
    mainStatus = resp?.status() ?? null;
    try { await page.waitForLoadState('load', { timeout: T.load }); } catch { loadTimeout = true; }
  } catch (e) {
    navError = e.message.split('\n')[0].slice(0, 200);
  }

  let pre = { banner: false, bannerText: null, payOrOkay: false, botBlocked: false };
  let post = null;
  let cookiesPre = null;
  const consent = { attempted: false, method: null, label: null, verified: null, clickAt: null };

  if (!navError) {
    await page.waitForTimeout(T.settle);

    // 2. PRE snapshot: state before any interaction.
    pre = await inspect(page);
    if ([403, 429].includes(mainStatus)) pre.botBlocked = true;
    cookiesPre = await cookieSnapshot(context, site.url);
    const tPre = now();
    const shot = (tag) => withTimeout(page.screenshot({ path: path.join(OUT, 'screens', `${new URL(site.url).hostname}_${mode}_${rep}_${tag}.jpg`), type: 'jpeg', quality: 40, timeout: T.op }), T.op + 1000);
    await shot('1pre');

    // 3. Consent action (accept / reject), then verify the banner is really gone.
    if (mode !== 'none' && !pre.botBlocked) {
      consent.attempted = true;
      const until = Date.now() + T.consentMax;
      while (!ac.done && Date.now() < until && (pre.banner || ac.popupFound || ac.cmp || Date.now() < until - 10000)) {
        await page.waitForTimeout(500);
      }
      if (ac.done) { consent.method = 'autoconsent'; consent.clickAt = Math.min(ac.foundAt ?? ac.at, ac.at); }
      await page.waitForTimeout(T.verify);
      let after = await inspect(page);
      // Fallback: autoconsent did nothing, or claimed success but the banner is still visible.
      // Also tried when nothing was detected: the patterns are exact button labels, so a click is unlikely to hit anything else.
      if (after.banner || !ac.done) {
        const tClick = now();
        const label = await clickByText(page, mode === 'accept' ? ACCEPT_RE : REJECT_RE);
        if (label) {
          consent.clickAt = tClick;
          consent.method = consent.method ? 'autoconsent+text-fallback' : 'text-fallback';
          consent.label = label;
          await page.waitForTimeout(T.verify);
          after = await inspect(page);
        }
      }
      // verified: true = a banner was there and is gone now; false = still visible; null = never saw one
      // verified only if something was clicked and no banner is visible afterwards
      const sawBanner = pre.banner || ac.popupFound || Boolean(consent.method);
      consent.verified = !sawBanner ? null : consent.method ? !after.banner : false;
      await shot('2consent');
    }

    // 4. Observation window of fixed length, starting at the consent click (accept/reject) or right after
    //    the PRE snapshot (none, or when no click happened). Verification above runs inside the window.
    t0 = mode !== 'none' && consent.clickAt !== null ? consent.clickAt : tPre;
    tEnd = t0 + T.window;
    const steps = 8;
    await withTimeout(page.evaluate(async ([n, pause]) => {
      for (let i = 0; i < n; i++) { window.scrollBy(0, window.innerHeight * 0.8); await new Promise((r) => setTimeout(r, pause)); }
    }, [steps, Math.floor(T.window / 2 / steps)]), T.window);
    const rest = tEnd - now();
    if (rest > 0) await page.waitForTimeout(rest);

    post = await inspect(page);
  }

  // 5. END snapshot
  const m = await withTimeout(cdp.send('Performance.getMetrics'), T.op);
  const metrics = m ? Object.fromEntries(m.metrics.map((x) => [x.name, x.value])) : {};
  const cookiesEnd = navError ? null : await cookieSnapshot(context, site.url);
  const screenshot = path.join(OUT, 'screens', `${new URL(site.url).hostname}_${mode}_${rep}_3end.jpg`);
  await withTimeout(page.screenshot({ path: screenshot, type: 'jpeg', quality: 40, timeout: T.op }), T.op + 1000);
  await withTimeout(Promise.allSettled(pending), T.op * 2);
  for (const q of requests) q.phase = t0 === null || q.ts < t0 ? 'pre' : q.ts <= tEnd ? 'window' : 'after';
  const finalUrl = page.url();
  await withTimeout(context.close(), T.op);

  const visitRow = {
    visitId, site: site.url, category: site.category, mode, rep, date: new Date().toISOString(),
    navError, loadTimeout, mainStatus, finalUrl,
    botBlocked: pre.botBlocked, bannerPre: pre.banner, bannerText: pre.bannerText, payOrOkay: pre.payOrOkay,
    bannerEnd: post?.banner ?? null,
    cmp: ac.cmp, autoconsentDone: ac.done, autoconsentResult: ac.result, clicks: ac.clicks,
    consentAttempted: consent.attempted, consentMethod: consent.method, fallbackLabel: consent.label, consentVerified: consent.verified,
    consentAt: consent.clickAt, t0, windowMs: T.window, acErrors: ac.errors.slice(0, 3),
    scriptMs: metrics.ScriptDuration ? Math.round(metrics.ScriptDuration * 1000) : null,
    taskMs: metrics.TaskDuration ? Math.round(metrics.TaskDuration * 1000) : null,
    cookiesPre, cookiesEnd,
    requests: requests.length,
  };
  return { visitRow, requests };
}

async function main() {
  fs.mkdirSync(path.join(OUT, 'screens'), { recursive: true });
  const visPath = path.join(OUT, 'visits.jsonl');

  // Resume: skip visits already recorded. --retry-failed also re-runs visits that ended with an error.
  const doneKeys = new Set();
  if (fs.existsSync(visPath) && !args.fresh) {
    for (const l of fs.readFileSync(visPath, 'utf8').split('\n').filter(Boolean)) {
      const v = JSON.parse(l);
      if (args['retry-failed'] && (v.navError || v.botBlocked)) continue;
      doneKeys.add(`${v.site}|${v.mode}|${v.rep}`);
    }
  }

  const reqOut = fs.createWriteStream(path.join(OUT, 'requests.jsonl'), { flags: 'a' });
  const visOut = fs.createWriteStream(visPath, { flags: 'a' });
  // Each worker has its own browser and restarts it every RESTART visits, so memory cannot pile up.
  const RESTART = Number(args['restart-every'] || 6);
  async function launch() {
    const browser = await chromium.launch({ headless: !args.headed, executablePath: args.chrome || undefined });
    const probe = await browser.newPage();
    const ua = (await probe.evaluate(() => navigator.userAgent)).replace('HeadlessChrome', 'Chrome');
    await probe.close();
    return { browser, ua };
  }

  const jobs = [];
  for (const s of loadSites()) for (const m of MODES) for (let r = 0; r < REPEATS; r++) {
    if (!doneKeys.has(`${s.url}|${m}|${r}`)) jobs.push([s, m, r]);
  }
  // Gentle crawling: random order (so the same site is not hit three times in a row) and a pause between visits.
  if (!args['no-shuffle']) for (let i = jobs.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [jobs[i], jobs[j]] = [jobs[j], jobs[i]]; }
  const PAUSE = Number(args.pause ?? 3) * 1000;
  const total = jobs.length;
  if (doneKeys.size) console.log(`Resuming: ${doneKeys.size} visits already done, ${total} to go.`);
  let done = 0;
  const running = new Map();

  // Heartbeat: shows what is still running, so a stuck visit is never silent.
  const hb = setInterval(() => {
    const mb = Math.round(process.memoryUsage().heapUsed / 1048576);
    if (running.size) console.log(`  … running: ${[...running].map(([k, t]) => `${k} (${Math.round((Date.now() - t) / 1000)}s)`).join(', ')}  [heap ${mb} MB]`);
  }, 30000);

  async function worker() {
    let b = await launch();
    let count = 0;
    while (jobs.length) {
      if (count >= RESTART) {
        await withTimeout(b.browser.close(), T.op);
        b = await launch();
        count = 0;
      }
      count++;
      const [s, m, r] = jobs.shift();
      const key = `${s.url} ${m}`;
      running.set(key, Date.now());
      const handle = { context: null };
      const watchdog = new Promise((res) => setTimeout(() => res('watchdog'), T.visit));
      try {
        const out = await Promise.race([visit(b.browser, b.ua, s, m, r, handle), watchdog]);
        if (out === 'watchdog') {
          await withTimeout(handle.context?.close(), T.op);
          count = RESTART; // a stuck visit may leave a leaking page behind: restart the browser next time
          throw new Error(`watchdog: visit exceeded ${T.visit / 1000}s`);
        }
        const { visitRow, requests } = out;
        visOut.write(JSON.stringify(visitRow) + '\n');
        for (const q of requests) reqOut.write(JSON.stringify(q) + '\n');
        const trk = requests.filter((q) => q.isTracking && q.phase === 'window').length;
        const flags = [visitRow.botBlocked && 'BOT-BLOCKED', visitRow.payOrOkay && 'pay-or-okay', visitRow.loadTimeout && 'load-timeout', visitRow.navError && 'ERR ' + visitRow.navError].filter(Boolean).join(' ');
        const cv = visitRow.consentVerified === null ? '-' : visitRow.consentVerified ? 'verified' : 'NOT closed';
        console.log(`[${++done}/${total}] ${key}: ${requests.length} req, ${trk} tracking, banner=${visitRow.bannerPre ? 'yes' : 'no'} consent=${visitRow.consentMethod ?? '-'}/${cv} ${flags}`);
      } catch (e) {
        console.error(`[${++done}/${total}] ${key}: FAILED ${e.message}`);
        visOut.write(JSON.stringify({ site: s.url, category: s.category, mode: m, rep: r, date: new Date().toISOString(), navError: 'crash: ' + e.message.slice(0, 200) }) + '\n');
      } finally {
        running.delete(key);
      }
      if (jobs.length && PAUSE) await new Promise((r) => setTimeout(r, PAUSE));
    }
    await withTimeout(b.browser.close(), T.op);
  }
  await Promise.all(Array.from({ length: WORKERS }, worker));
  clearInterval(hb);
  reqOut.end(); visOut.end();
  console.log('Done.');
  process.exit(0);
}

main();
