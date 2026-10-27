"""Build site lists for re-crawling problem visits of a finished crawl.

Usage: python make_rerun_lists.py results_study [--sites sites_study.csv]

Writes:
  sites_rerun_consent.csv  sites with an unverified accept or reject click (re-crawl modes accept,reject)
  sites_memory.csv         sites whose accept visit was aborted for memory (re-crawl mode accept, alone)
"""
import argparse
from pathlib import Path

import pandas as pd

p = argparse.ArgumentParser()
p.add_argument("folder")
p.add_argument("--sites", default="sites_study.csv")
args = p.parse_args()

vis = pd.read_json(Path(args.folder) / "visits.jsonl", lines=True)
for col in ["memoryAbort", "botBlocked", "navError", "consentVerified", "bannerPre", "cmp", "requests"]:
    if col not in vis:
        vis[col] = None
vis = vis.sort_values("date").drop_duplicates(["site", "mode", "rep"], keep="last")
vis["memoryAbort"] = vis["memoryAbort"].fillna(False).astype(bool)
vis["botBlocked"] = vis["botBlocked"].fillna(False).astype(bool)

measured = vis[vis.navError.isna() & ~vis.botBlocked & ~vis.memoryAbort & (vis.requests.fillna(0) > 1)]
banner_sites = set(measured[measured.bannerPre.fillna(False).astype(bool) | measured.cmp.notna()].site)
unverified = measured[(measured["mode"] != "none") & measured.site.isin(banner_sites) & (measured.consentVerified != True)]  # noqa: E712
memory = vis[vis.memoryAbort]

sample = pd.read_csv(args.sites)
consent_sites = sample[sample.url.isin(set(unverified.site))]
memory_sites = sample[sample.url.isin(set(memory.site))]
consent_sites.to_csv("sites_rerun_consent.csv", index=False)
memory_sites.to_csv("sites_memory.csv", index=False)
print(f"sites_rerun_consent.csv: {len(consent_sites)} sites ({len(unverified)} unverified visits) -> {2 * len(consent_sites)} visits to re-crawl")
print(f"sites_memory.csv:        {len(memory_sites)} sites -> {len(memory_sites)} accept visits to re-crawl")
