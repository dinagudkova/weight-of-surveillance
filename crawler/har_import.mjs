// Import manual visits recorded in Chrome DevTools (HAR files) into the crawler's JSONL format.
//
// Used for sites that block automated browsers: a person visits them in a normal Chrome, records the network
// log, and this script classifies every request with the same rules and lists as the crawler (classify.mjs).
//
// Usage:
//   node crawler/har_import.mjs --hars data/manual_hars --out data/raw/manual
//   (optional) --sites sample/sites_study.csv,sample/sites_boost.csv --window 30
//
// File names: <domain>_<mode>.har, e.g. zalando.de_accept.har, zalando.de_none.har (mode: none | accept | reject).
// Time 0: the visitor runs   fetch('https://example.com/?wos_t0')   in the DevTools console right before the
// consent click (or, for "none", about 5 seconds after the page opened). That marker request sets the start of
// the observation window; it is removed from the data. Requests before it are phase "pre", the next --window
// seconds "window", later ones "after".
import fs from 'fs';
import path from 'path';
import { getDomain, getHostname } from 'tldts';
import { classify, cnameLookup } from './classify.mjs';

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => {
    if (a.startsWith('--')) acc.push([a.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : true]);
    return acc;
  }, []),
);
if (!args.hars || !args.out) {
  console.error('Usage: node crawler/har_import.mjs --hars <folder with <domain>_<mode>.har> --out <output folder>');
  process.exit(1);
}
const WINDOW_MS = Number(args.window || 30) * 1000;
const MARKER = 'wos_t0';

// site list: url, category, ... (several files separated by commas)
const siteFiles = String(args.sites || 'sample/sites_study.csv,sample/sites_boost.csv').split(',');
const sites = siteFiles.flatMap((f) => {
  const [header, ...lines] = fs.readFileSync(f.trim(), 'utf8').trim().split('\n');
  const cols = header.split(',');
  return lines.map((l) => Object.fromEntries(l.split(',').map((v, i) => [cols[i], v.trim()])));
});
const siteFor = (domain) => sites.find((s) => getDomain(s.url) === domain || s.domain === domain);

// DevTools resource types -> adblock request types used by classify() (same mapping as the crawler)
const adblockType = (t, isFirstDocument) => {
  if (t === 'document') return isFirstDocument ? 'main_frame' : 'sub_frame';
  if (t === 'fetch') return 'xhr';
  return t || 'other';
};

fs.mkdirSync(args.out, { recursive: true });
const visOut = fs.createWriteStream(path.join(args.out, 'visits.jsonl'));
const reqOut = fs.createWriteStream(path.join(args.out, 'requests.jsonl'));

const files = fs.readdirSync(args.hars).filter((f) => f.endsWith('.har')).sort();
if (!files.length) console.error(`No .har files in ${args.hars}`);
for (const file of files) {
  const m = file.match(/^(.+)_(none|accept|reject)\.har$/);
  if (!m) { console.error(`skip ${file}: name must be <domain>_<mode>.har`); continue; }
  const [, domain, mode] = m;
  const site = siteFor(domain);
  if (!site) { console.error(`skip ${file}: ${domain} is not in the site lists`); continue; }

  const har = JSON.parse(fs.readFileSync(path.join(args.hars, file), 'utf8'));
  const entries = (har.log?.entries || []).slice().sort((a, b) => new Date(a.startedDateTime) - new Date(b.startedDateTime));
  if (!entries.length) { console.error(`skip ${file}: no requests`); continue; }
  const start = new Date(entries[0].startedDateTime).getTime();
  const marker = entries.find((e) => e.request.url.includes(MARKER));
  if (!marker) { console.error(`skip ${file}: marker request (${MARKER}) not found`); continue; }
  const t0 = new Date(marker.startedDateTime).getTime() - start;

  const visitId = `manual-${domain}-${mode}`;
  let n = 0;
  let firstDocument = true;
  for (const e of entries) {
    const url = e.request.url;
    if (url.includes(MARKER) || !/^https?:/.test(url)) continue;
    const ts = new Date(e.startedDateTime).getTime() - start;
    const type = e._resourceType || 'other';
    const host = getHostname(url) || '';
    const chain = (await Promise.race([
      Promise.resolve(cnameLookup(host, site.url)).catch(() => []),
      new Promise((res) => setTimeout(() => res([]), 3000)),
    ])) || [];
    const c = classify(url.slice(0, 4096), site.url, adblockType(type, type === 'document' && firstDocument), chain);
    if (type === 'document') firstDocument = false;
    const r = e.response || {};
    const body = Math.max(0, r.bodySize ?? 0);
    const headers = Math.max(0, r.headersSize ?? 0);
    const transfer = Math.max(0, r._transferSize ?? 0);
    reqOut.write(JSON.stringify({
      visitId, site: site.url, mode, rep: 0, ts,
      phase: ts < t0 ? 'pre' : ts <= t0 + WINDOW_MS ? 'window' : 'after',
      url: url.slice(0, 500), type, status: r.status ?? null, mime: (r.content?.mimeType || '').split(';')[0] || null,
      failed: !r.status || Boolean(e._error),
      bytes: transfer || body + headers, bodyBytes: body,
      upBytes: Math.max(0, e.request.bodySize ?? 0) + Math.max(0, e.request.headersSize ?? 0),
      ...c,
      cnameChain: chain.length ? chain : undefined,
    }) + '\n');
    n++;
  }

  // The visitor sees the banner and confirms the click, so consent is verified by hand for accept/reject.
  visOut.write(JSON.stringify({
    visitId, site: site.url, category: site.category, mode, rep: 0, date: new Date(start).toISOString(),
    machine: 'manual', browserMode: 'manual', webdriver: false,
    navError: null, botBlocked: false, bannerPre: true, cmp: null,
    consentAttempted: mode !== 'none', consentMethod: mode === 'none' ? null : 'manual',
    consentVerified: mode === 'none' ? null : true, consentAt: mode === 'none' ? null : t0,
    t0, windowMs: WINDOW_MS, requests: n,
  }) + '\n');
  console.log(`${file}: ${n} requests, window starts at ${(t0 / 1000).toFixed(1)} s`);
}
visOut.end();
reqOut.end();
