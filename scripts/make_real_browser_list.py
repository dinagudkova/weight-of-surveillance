"""Site list for the real-browser crawl: the study sample minus sites that blocked the crawler.

Usage: python scripts/make_real_browser_list.py data/raw/study_merged
Writes sample/sites_real_browser.csv.

Sites whose bot protection blocked the automated crawler in the main study are left out on purpose: the
real-browser mode is meant to see pages as a regular user does, not to get past protection a site set up
against bots. They stay "not measurable" in the methodology.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) < 2:
    sys.exit(__doc__)
vis = pd.read_json(Path(sys.argv[1]) / "visits.jsonl", lines=True)
if "botBlocked" not in vis:
    vis["botBlocked"] = False
blocked = set(vis[vis.botBlocked.fillna(False).astype(bool)].site)

sample = pd.concat([pd.read_csv(ROOT / "sample" / f) for f in ["sites_study.csv", "sites_boost.csv"]], ignore_index=True)
keep = sample[~sample.url.isin(blocked)]
out = ROOT / "sample" / "sites_real_browser.csv"
keep.to_csv(out, index=False)
print(f"{len(sample)} sites in the sample, {len(blocked & set(sample.url))} excluded (bot protection) -> {len(keep)} sites in {out}")
