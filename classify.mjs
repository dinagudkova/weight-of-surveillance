// Classifies requests and cookies for "The Weight of Surveillance".
//
// Categories (first match wins):
//   consent     – the consent banner itself (CMP domains, lists/cmp_domains.txt)
//   tracking    – trackingType: advertising | analytics | identity (ID sync, cookie matching, telco IDs)
//   telemetry   – error monitoring, performance monitoring, A/B testing (reported separately, not tracking)
//   first-party – the site and domains owned by the same company (DDG entities + lists/site_aliases.csv)
//   other       – other third parties: CDNs, fonts, video, payment, embedded content
//
// Tracking sources: DDG Tracker Data Set (with categories), lists/custom_trackers.csv (German ad-tech),
// EasyPrivacy (any party), EasyList + EasyList Germany (third party only), CNAME cloaking (DNS).
import fs from 'fs';
import dns from 'dns/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import { getDomain, getHostname } from 'tldts';
import { FiltersEngine, Request } from '@ghostery/adblocker';

const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), 'lists');
const read = (f) => fs.readFileSync(path.join(dir, f), 'utf8');
const csv = (f) => read(f).trim().split('\n').slice(1).filter((l) => l && !l.startsWith('#')).map((l) => l.split(','));

const AD_CATS = new Set(['Advertising', 'Ad Motivated Tracking', 'Action Pixels', 'Ad Fraud']);
// Companies whose business is advertising: their scripts count as advertising even when DDG also lists analytics.
// Cookie syncing and ID matching, recognised by URL (user sync endpoints, cookie match pixels, ...).
const SYNC_RE = /(\/\/cm\.|usersync|user\.sync|user-sync|cookie[-_]?sync|cookiematch|cookie-match|\/sync(\?|\/|$)|\/psync|\/cm(\?|\/|$)|\/match(\?|\/|$)|\bmatch\.|\/getuid|\/setuid|piggyback|\/rid\?|adscalematch|\/tpui)/i;
const AD_OWNERS = /(relevant-digital|confiant|five media|geoedge|pubstack|integral ad science|doubleverify|criteo|taboola|outbrain|pubmatic|magnite|index exchange|trade desk|bytedance|teads|adform|yieldlove|virtual minds|ströer|amazon technologies|adnami|seedtag|smartadserver|equativ|openx|sovrn|triplelift)/i;
const ANALYTICS_CATS = new Set(['Analytics', 'Audience Measurement', 'Third-Party Analytics Marketing', 'Session Replay']);

const tds = JSON.parse(read('ddg-tds.json'));
const privacyEngine = FiltersEngine.parse(read('easyprivacy.txt') + '\n' + read('custom_privacy_filters.txt'), { loadCosmeticFilters: false });
const adsEngine = FiltersEngine.parse(read('easylist.txt') + '\n' + read('easylistgermany.txt') + '\n' + read('custom_ads_filters.txt'), { loadCosmeticFilters: false });

const custom = Object.fromEntries(csv('custom_trackers.csv').map(([d, owner, category]) => [d, { owner, categories: [category] }]));
const cmpDomains = new Set(read('cmp_domains.txt').split('\n').map((l) => l.trim()).filter((l) => l && !l.startsWith('#')));
const cookieNames = read('tracker_cookie_names.txt').split('\n').filter((l) => l && !l.startsWith('#')).map((l) => l.split('|'));
const aliases = {};
for (const [site, alias] of csv('site_aliases.csv')) (aliases[site] ||= new Set()).add(alias);

// DDG categories that are not tracking on their own.
const NON_TRACKING = new Set(['Content Delivery', 'Embedded Content', 'Online Payment', 'SSO', 'Federated Login', 'Badge',
  'Support Chat Widget', 'Social - Share', 'Social - Comment', 'Tag Manager']);

// Walk "a.b.example.com" -> "b.example.com" -> "example.com" in a lookup table.
function lookup(table, host) {
  const parts = host.split('.');
  for (let i = 0; i < parts.length - 1; i++) {
    const k = parts.slice(i).join('.');
    if (table instanceof Set ? table.has(k) : table[k]) return table instanceof Set ? k : table[k];
  }
  return null;
}

// --- CNAME cloaking via DNS ---------------------------------------------------------------
const cnameCache = new Map();
async function resolveChain(host) {
  const chain = [];
  let h = host;
  for (let i = 0; i < 4; i++) {
    let next;
    try { next = (await dns.resolveCname(h))[0]; } catch { break; }
    if (!next || chain.includes(next)) break;
    chain.push(next);
    h = next;
  }
  return chain;
}
// Only first-party-looking subdomains can be cloaked; resolution is cached per host.
export function cnameLookup(host, siteUrl) {
  const siteDomain = getDomain(siteUrl);
  if (!host || getDomain(host) !== siteDomain || host === getHostname(siteUrl)) return Promise.resolve([]);
  if (!cnameCache.has(host)) cnameCache.set(host, resolveChain(host));
  return cnameCache.get(host);
}

function trackerFor(host) {
  const t = lookup(custom, host) || lookup(tds.trackers, host);
  if (!t) return null;
  const cats = t.categories || [];
  // DDG marks some entries (e.g. Akamai edge hosts like de.edgekey.net) with default "ignore": not trackers.
  const ignored = t.default === 'ignore' && !cats.some((c) => AD_CATS.has(c) || ANALYTICS_CATS.has(c));
  const onlyNonTracking = ignored || (cats.length > 0 && cats.every((c) => NON_TRACKING.has(c)));
  const cdnLike = cats.includes('Content Delivery') || cats.includes('Embedded Content');
  return { owner: t.owner?.ownedBy || t.owner?.name || t.owner, categories: cats, onlyNonTracking, cdnLike };
}

export function isFirstParty(host, siteUrl) {
  const regDomain = getDomain(host) || host;
  const siteDomain = getDomain(siteUrl) || getHostname(siteUrl);
  if (regDomain === siteDomain || aliases[siteDomain]?.has(regDomain)) return true;
  const a = lookup(tds.domains, host);
  const b = lookup(tds.domains, getHostname(siteUrl) || '');
  return Boolean(a && b && a === b);
}

export function classify(url, siteUrl, resourceType, cnameChain = []) {
  const host = getHostname(url) || '';
  const regDomain = getDomain(url) || host;
  const firstParty = isFirstParty(host, siteUrl);
  const thirdParty = !firstParty;

  let easyprivacy = false;
  let easylist = false;
  try {
    const req = Request.fromRawDetails({ url, sourceUrl: siteUrl, type: resourceType || 'other' });
    easyprivacy = privacyEngine.match(req).match;
    easylist = adsEngine.match(req).match;
  } catch {}

  // CNAME: first-party subdomain pointing to a known tracker (DNS chain or DDG's static list).
  const cnameTargets = [...cnameChain, tds.cnames?.[host]].filter(Boolean);
  const cnameTracker = cnameTargets.map(trackerFor).find((t) => t && !t.onlyNonTracking && !t.cdnLike) || null;

  const tracker = thirdParty ? trackerFor(host) : null;
  const viaList = Boolean(tracker && !tracker.onlyNonTracking && (!tracker.cdnLike || easyprivacy));
  const viaEasyList = easylist && thirdParty;
  const isConsent = Boolean(lookup(cmpDomains, host));
  const isTracking = !isConsent && Boolean(viaList || cnameTracker || easyprivacy || viaEasyList);

  const t = cnameTracker || tracker;
  const cats = t?.categories || [];
  const isTelemetry = cats.includes('Telemetry');
  let trackingType = null;
  if (isTracking && !isTelemetry) {
    if (cats.includes('Identity') || SYNC_RE.test(url)) trackingType = 'identity';
    else if (viaEasyList) trackingType = 'advertising';
    else if (cats.includes('Action Pixels')) trackingType = 'advertising'; // conversion pixels (Meta, TikTok, ...)
    else if (AD_OWNERS.test(t?.owner || '')) trackingType = 'advertising';
    else if (cats.some((c) => AD_CATS.has(c)) && !cats.some((c) => ANALYTICS_CATS.has(c))) trackingType = 'advertising';
    else trackingType = 'analytics';
  }
  const tracking = isTracking && !isTelemetry;
  const category = isConsent ? 'consent' : isTelemetry && isTracking ? 'telemetry' : tracking ? 'tracking' : firstParty ? 'first-party' : 'other';
  return {
    host, regDomain, thirdParty, category, trackingType, isTracking: tracking, isConsent,
    viaTds: viaList, viaCname: Boolean(cnameTracker), viaEasyPrivacy: easyprivacy, viaEasyList,
    cname: cnameTargets[0] || null,
    owner: t?.owner || (thirdParty ? lookup(tds.domains, host) || regDomain : `${getDomain(siteUrl)} (first-party)`),
    categories: cats,
  };
}

export const isCmpHost = (host) => Boolean(lookup(cmpDomains, host));

// A cookie is a tracker cookie if its domain is a known third-party tracker,
// or if it is a first-party cookie with a known tracking-script name (_ga, _fbp, ...).
export function classifyCookie(cookie, siteUrl) {
  const host = cookie.domain.replace(/^\./, '');
  const byName = cookieNames.find(([prefix]) => cookie.name.startsWith(prefix));
  if (isFirstParty(host, siteUrl)) {
    return { thirdParty: false, tracker: Boolean(byName), owner: byName ? byName[1] : null };
  }
  const t = trackerFor(host);
  return { thirdParty: true, tracker: Boolean((t && !t.onlyNonTracking && !t.categories.includes('Telemetry')) || byName), owner: t?.owner || byName?.[1] || getDomain(host) };
}
