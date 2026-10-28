// Re-applies classify.mjs to an existing crawl, so updated lists take effect without crawling again.
// Usage: node crawler/reclassify.mjs data/raw/pilot_v3
// Keeps a backup of the first version as requests.orig.jsonl and rewrites requests.jsonl in place,
// so visits added later (e.g. re-crawled sites) are kept.
// Limitations: URLs are stored truncated to 500 characters; older crawls stored only the first CNAME hop;
// cookie counts in visits.jsonl are not recomputed.
import fs from 'fs';
import path from 'path';
import readline from 'readline';
import { classify } from './classify.mjs';

const dir = process.argv[2];
if (!dir) {
  console.error('Usage: node crawler/reclassify.mjs <folder>');
  process.exit(1);
}
const src = path.join(dir, 'requests.jsonl');
const orig = path.join(dir, 'requests.orig.jsonl');
if (!fs.existsSync(orig)) fs.copyFileSync(src, orig);

const typeMap = { document: 'sub_frame', fetch: 'xhr' };
const out = fs.createWriteStream(src + '.tmp');
const rl = readline.createInterface({ input: fs.createReadStream(src), crlfDelay: Infinity });
let n = 0, changed = 0;
for await (const line of rl) {
  if (!line) continue;
  const r = JSON.parse(line);
  const chain = r.cnameChain || (r.cname ? [r.cname] : []);
  const c = classify(r.url, r.site, typeMap[r.type] || r.type, chain);
  if (c.category !== r.category || c.trackingType !== r.trackingType) changed++;
  out.write(JSON.stringify({ ...r, ...c, cnameChain: r.cnameChain }) + '\n');
  n++;
}
await new Promise((res) => out.end(res));
fs.renameSync(src + '.tmp', src);
console.log(`Reclassified ${n} requests, ${changed} changed category or tracking type. Backup of the first version: ${orig}`);
