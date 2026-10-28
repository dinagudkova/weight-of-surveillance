"""Build dbt seed files from the project lists (lists/) and the site sample.

Usage: python scripts/build_seeds.py [--sites sample/sites_study.csv sample/sites_boost.csv]

Writes dbt/seeds/*.csv. Run it again whenever a list in lists/ or the site sample changes,
then `dbt build` re-classifies all requests without crawling again.

Tracker flags (ad, analytics, identity, ...) are derived here, in one place, with the same rules as
crawler/classify.mjs, so the SQL models only join and combine booleans.
"""
import argparse
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LISTS = ROOT / "lists"
SEEDS = ROOT / "dbt" / "seeds"

AD_CATS = {"Advertising", "Ad Motivated Tracking", "Action Pixels", "Ad Fraud"}
ANALYTICS_CATS = {"Analytics", "Audience Measurement", "Third-Party Analytics Marketing", "Session Replay"}
NON_TRACKING = {"Content Delivery", "Embedded Content", "Online Payment", "SSO", "Federated Login", "Badge",
                "Support Chat Widget", "Social - Share", "Social - Comment", "Tag Manager"}
AD_OWNERS = re.compile(r"(relevant-digital|confiant|five media|geoedge|pubstack|integral ad science|doubleverify|criteo|"
                       r"taboola|outbrain|pubmatic|magnite|index exchange|trade desk|bytedance|teads|adform|yieldlove|"
                       r"virtual minds|ströer|amazon technologies|adnami|seedtag|smartadserver|equativ|openx|sovrn|triplelift)", re.I)


def rows(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(line for line in f if line.strip() and not line.startswith("#")))


def tracker_flags(cats, default, owner):
    cats = [c for c in cats if c]
    ignored = default == "ignore" and not any(c in AD_CATS or c in ANALYTICS_CATS for c in cats)
    return {
        "only_non_tracking": ignored or (bool(cats) and all(c in NON_TRACKING for c in cats)),
        "cdn_like": "Content Delivery" in cats or "Embedded Content" in cats,
        "ad_category": any(c in AD_CATS for c in cats) and not any(c in ANALYTICS_CATS for c in cats),
        "action_pixel": "Action Pixels" in cats,
        "ad_owner": bool(AD_OWNERS.search(owner or "")),
        "identity": "Identity" in cats,
        "telemetry": "Telemetry" in cats,
    }


def write(name, fieldnames, data):
    SEEDS.mkdir(parents=True, exist_ok=True)
    # Quotes inside values (e.g. company names like 'LLC "AmberData"') break the DuckDB seed loader.
    data = [{k: (v.replace('"', "") if isinstance(v, str) else v) for k, v in row.items()} for row in data]
    with open(SEEDS / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        w.writerows(data)
    print(f"{name:<22} {len(data):>6} rows")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sites", nargs="+", default=[str(ROOT / "sample" / "sites_study.csv")],
                   help="one or more site lists, e.g. sample/sites_study.csv sample/sites_boost.csv")
    args = p.parse_args()

    # Sites: url, category, subcategory, domain, market (pilot files only have url, category)
    from tldextract import TLDExtract
    extract = TLDExtract(suffix_list_urls=())
    sites = []
    for r in [r for path in args.sites for r in rows(path)]:
        host = re.sub(r"^https?://", "", r["url"].strip()).split("/")[0].lower()
        e = extract(host)
        # fall back to the last two labels for hosts without a public suffix (e.g. *.test in the mock crawl)
        domain = r.get("domain") or getattr(e, "top_domain_under_public_suffix", "") or ".".join(host.split(".")[-2:])
        sites.append({"url": r["url"].strip(), "category": r.get("category", ""), "subcategory": r.get("subcategory", ""),
                      "site_domain": domain, "market": r.get("market", ""),
                      "sample_source": r.get("sample_source") or "crux_top1000"})
    write("sites.csv", ["url", "category", "subcategory", "site_domain", "market", "sample_source"], sites)

    aliases = [{"site_domain": r["site_domain"], "alias_domain": r["alias_domain"]} for r in rows(LISTS / "site_aliases.csv")]
    write("site_aliases.csv", ["site_domain", "alias_domain"], aliases)

    cmp = [{"domain": l.strip()} for l in open(LISTS / "cmp_domains.txt", encoding="utf-8") if l.strip() and not l.startswith("#")]
    write("cmp_domains.csv", ["domain"], cmp)

    # Trackers: custom list first (priority 1), then DuckDuckGo TDS (priority 2)
    tds = json.load(open(LISTS / "ddg-tds.json", encoding="utf-8"))
    trackers = []
    for r in rows(LISTS / "custom_trackers.csv"):
        cats = [r["category"]]
        trackers.append({"domain": r["domain"], "owner": r["owner"], "source": "custom", "priority": 1,
                         "categories": "|".join(cats), **tracker_flags(cats, "", r["owner"])})
    for domain, t in tds["trackers"].items():
        owner = (t.get("owner") or {}).get("ownedBy") or (t.get("owner") or {}).get("name") or ""
        cats = t.get("categories") or []
        trackers.append({"domain": domain, "owner": owner, "source": "ddg_tds", "priority": 2,
                         "categories": "|".join(cats), **tracker_flags(cats, t.get("default", ""), owner)})
    write("trackers.csv", ["domain", "owner", "source", "priority", "categories", "only_non_tracking", "cdn_like",
                           "ad_category", "action_pixel", "ad_owner", "identity", "telemetry"], trackers)

    flags = [{"site_domain": r["site_domain"], "pay_or_okay": r["pay_or_okay"], "note": r.get("note", "")}
             for r in rows(LISTS / "manual_site_flags.csv")]
    write("manual_site_flags.csv", ["site_domain", "pay_or_okay", "note"], flags)

    groups = [{k: r[k] for k in ["site_category", "category_group", "group_label", "group_order"]}
              for r in rows(LISTS / "category_groups.csv")]
    write("category_groups.csv", ["site_category", "category_group", "group_label", "group_order"], groups)

    entities = [{"domain": d, "entity": e} for d, e in tds["domains"].items()]
    write("domain_entities.csv", ["domain", "entity"], entities)


if __name__ == "__main__":
    main()
