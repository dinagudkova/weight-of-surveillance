"""Boost under-represented categories with sites from a larger CrUX bucket (e.g. top 5,000).

Usage:
  python sample/build_sample.py --bucket 5000 --titles --candidates-out sample/candidates_top5000.csv
  python sample/build_boost.py                      # writes sample/boost_review.csv and sites_boost.csv

The study sample (sites_study.csv) stays unchanged. For every boosted category the script adds as many
sites as needed to reach --target, drawn at random (fixed seed) from candidates that are not in the study yet.
All boosted sites are marked sample_source = crux_top5000_boost, so the analysis can keep them apart from the
top-1,000 sample (they are less popular sites).

Review sample/boost_review.csv by hand (all eligible candidates, with page titles if --titles was used).
Record corrections in lists/category_overrides.csv and lists/exclude_domains.csv, re-run both commands.
"""
import argparse
import csv
import random
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--candidates", default=str(ROOT / "sample" / "candidates_top5000.csv"))
p.add_argument("--study", default=str(ROOT / "sites_study.csv"))
p.add_argument("--categories", default="government_public,health,finance_insurance")
p.add_argument("--target", type=int, default=28, help="sites per category after the boost")
p.add_argument("--market", default="de")
p.add_argument("--seed", type=int, default=42)
p.add_argument("--max-per-family", type=int, default=3,
               help="at most this many sites of one platform family (e.g. regional Sparkassen share one CMS)")
p.add_argument("--out", default=str(ROOT / "sites_boost.csv"))
args = p.parse_args()

cats = args.categories.split(",")
study = list(csv.DictReader(open(args.study, encoding="utf-8")))
in_study = {r["domain"] for r in study}
have = defaultdict(int)
for r in study:
    have[r["category"]] += 1

eligible = defaultdict(list)
for r in csv.DictReader(open(args.candidates, encoding="utf-8")):
    if r["keep"] != "1" or r["category"] not in cats or r["domain"] in in_study:
        continue
    if args.market != "all" and r["market"] != args.market:
        continue
    eligible[r["category"]].append(r)

review = ROOT / "sample" / "boost_review.csv"
with open(review, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["category", "domain", "url", "subcategory", "category_source", "status", "title"])
    for c in cats:
        for r in sorted(eligible[c], key=lambda r: r["domain"]):
            w.writerow([c, r["domain"], r["url"], r["subcategory"], r["category_source"], r.get("status", ""), r.get("title", "")])

# Sites of one platform family are near-identical (same CMS, same trackers); cap them so they do not dominate.
FAMILIES = {"sparkasse": re.compile(r"sparkasse"), "volksbank": re.compile(r"volksbank|vr-?bank|raiba"),
            "landkreis_wahlen": re.compile(r"^(wahl|wahlen)\.|votemanager"), "huk": re.compile(r"^huk")}


def family(r):
    host = r["url"].split("//")[1]
    return next((name for name, rx in FAMILIES.items() if rx.search(r["domain"]) or rx.search(host)), None)


rng = random.Random(args.seed)
chosen = []
print(f"{'category':<20} {'in study':>8} {'eligible':>8} {'added':>6} {'total':>6}")
for c in cats:
    need = max(0, args.target - have[c])
    pool = sorted(eligible[c], key=lambda r: r["domain"])
    rng.shuffle(pool)
    pick, per_family = [], defaultdict(int)
    for r in pool:
        f = family(r)
        if f and per_family[f] >= args.max_per_family:
            continue
        if len(pick) < need:
            pick.append(r)
            if f:
                per_family[f] += 1
    chosen += pick
    flag = "" if have[c] + len(pick) >= 25 else "  <- below 25: review exclusions or raise the bucket"
    print(f"{c:<20} {have[c]:>8} {len(pool):>8} {len(pick):>6} {have[c] + len(pick):>6}{flag}")

with open(args.out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["url", "category", "subcategory", "domain", "market", "sample_source"])
    for r in sorted(chosen, key=lambda r: (r["category"], r["domain"])):
        w.writerow([r["url"], r["category"], r["subcategory"], r["domain"], r["market"], "crux_top5000_boost"])
print(f"\nReview list: {review}\nBoost sample: {args.out} ({len(chosen)} sites)")
