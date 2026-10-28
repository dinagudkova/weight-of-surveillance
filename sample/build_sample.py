"""Build the site sample for the full study from the Chrome UX Report (CrUX) top list for Germany.

Steps:
  1. Download (or read) the CrUX country list and keep the chosen rank bucket (default: top 1,000).
  2. Group origins by registrable domain (m.bild.de + www.bild.de -> bild.de) and pick one URL per domain.
  3. Mark exclusions: adult content, login/app/payment subdomains, gambling (optional), raw IPs.
  4. Draft a category per domain: known-domain overrides first, then keyword rules; unmatched = "other".
  5. Optionally fetch each home page title (one request per site) to help the manual review.
  6. Write sample/candidates.csv (everything, for review) and, with --sample N, a stratified random
     sample in crawler format.

Usage:
  python sample/build_sample.py                          # latest month, top 1,000
  python sample/build_sample.py --month 202609 --titles  # with page titles for review
  python sample/build_sample.py --from-reviewed sample/candidates.csv --sample 500 --seed 42

After the first run, review sample/candidates.csv by hand (fix `category`, set `keep` to 0 or 1),
then build the final list with --from-reviewed.
"""
import argparse
import csv
import gzip
import io
import random
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from pathlib import Path

import tldextract

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "sample"
CRUX_URL = "https://raw.githubusercontent.com/zakird/crux-top-lists/main/data/country/{cc}/{month}.csv.gz"

# Offline public suffix list (bundled snapshot), so no network is needed for domain parsing.
extract = tldextract.TLDExtract(suffix_list_urls=())

# --- exclusion rules -------------------------------------------------------------------------
ADULT_RE = re.compile(
    r"(porn|xxx|xvideo|xnxx|xhamster|xhopen|hentai|eporner|erome|youporn|you-porn|redtube|stripchat|chaturbate|"
    r"camwhores|onlyfans|fapello|rule34|escort|sadomaso|fetlife|swinger|erotik|eroprofile|eronity|mydirtyhobby|"
    r"pornoaffe|intim|sexcam|sex-|-sex|sextube|nude|nudes|celebgate|pimpbunny|punishworld|hdtube|tube8|spankbang|"
    r"desitales|hitomi\.la|noodlemagazine|ixxx|bookmark\.xxx|botinok|pictoa|fabswingers|camsoda|bongacams|huren|sex|\.sex$|"
    r"ladies\.de|asialadies|boundhub|boyfriendtv|cam4|e621|elitebabes|f95zone|faphouse|fremdgehen|fuq\.com|hotxv|imagefap|joyclub|"
    r"kaufmich|leakgallery|lobstertube|mat6tube|maturetube|melonstube|missav|nudogram|poppen\.de|porzo|pussy|shahvani|simpcity|"
    r"sxyprn|thisvid|thothd|xgroovy|xhaccess|xvv1deos|youjizz|travesta|darkero|theblowers|txnhh|taktube)",
    re.I,
)
# Subdomains that point to logged-in apps, mail, payment or account pages rather than a public home page.
APP_SUB_RE = re.compile(
    r"^(login|logon|signin|sso|auth|id|account|accounts|konto|mein|meine|my|secure|pay|payment|checkout|order|"
    r"mail|email|webmail|app|apps|portal|meet|one|drive|docs|console|admin|dashboard|kunden|kundenportal|"
    r"banking|online-banking|filiale|eltern|schulportal|lernen|moodle|campus)(\.|$)",
    re.I,
)
GAMBLING_RE = re.compile(r"(bet365|betano|tipico|bwin|novoline|casino|poker|lotto|slots|spielbank|sportwetten|gameduell|interwetten|merkurbets)", re.I)
IP_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")

# --- category rules (checked in order, on the registrable domain and host) -------------------
RULES = [
    ("government_public", "federal", r"(\.bund\.de$|^bund\.de$|bundesregierung|bundestag|bundesrat|zoll\.de|arbeitsagentur|elster|rentenversicherung|bafoeg|bamf|destatis|polizei|justiz|finanzamt)"),
    ("government_public", "state_city", r"(\.(nrw|bayern|berlin|hamburg|sachsen|hessen|niedersachsen|brandenburg|thueringen|saarland|bremen)\.de$|^(berlin|hamburg|muenchen|koeln|frankfurt|stuttgart|duesseldorf|leipzig|dresden)\.de$|service-bw|stadt-|landkreis|\.gov$|\.gov\.)"),
    ("health", "insurance", r"(^aok\.|barmer|^dak\.|ikk|bkk|krankenkasse|^tk\.de$|hkk)"),
    ("health", "pharmacy", r"(apotheke|apotheken|medikament|docmorris|medpex)"),
    ("health", "information", r"(gesundheit|netdoktor|doctolib|jameda|klinik|praxis|arzt|aerzte|onmeda|medizin)"),
    ("finance_insurance", "bank", r"(sparkasse|volksbank|raiffeisen|commerzbank|deutsche-bank|postbank|comdirect|consorsbank|^ing\.de$|^dkb\.de$|n26|targobank|hypovereinsbank|bank)"),
    ("finance_insurance", "insurance", r"(versicherung|allianz|huk|ergo\.de|axa|debeka|signal-iduna)"),
    ("finance_insurance", "markets", r"(finanzen|boerse|börse|onvista|wallstreet|aktie|trading|tradingview|scalable|trade-republic|traderepublic|coinbase|binance|bitpanda)"),
    ("news_media", "regional", r"(zeitung|nachrichten|kurier|anzeiger|allgemeine|rundschau|tagblatt|tageblatt|presse|morgenpost|abendblatt|volksstimme|echo|bote|express|post\.de$|online\.de$)"),
    ("news_media", "general", r"(news|magazin|journal|tagesspiegel|handelsblatt)"),
    ("services", "weather", r"(wetter|weather)"),
    ("services", "recipes", r"(chefkoch|rezept|kochen|koch|backen|essen|lecker)"),
    ("services", "telecom", r"(telekom|vodafone|o2online|congstar|1und1|blau\.de|aldi-talk|fraenk|winsim|freenet)"),
    ("services", "utilities", r"(stadtwerke|energie|strom|gas|eon\.de|vattenfall|enbw|rwe)"),
    ("services", "logistics", r"(dhl|dpd|hermes|gls-|ups\.com|deutschepost)"),
    ("travel_mobility", "travel", r"(booking|holiday|urlaub|reise|ferien|flug|airline|lufthansa|eurowings|ryanair|condor|tui|expedia|trivago|airbnb|hotel|bahn|db\.de|flixbus|adac|kayak|skyscanner)"),
    ("classifieds_jobs", "jobs", r"(stepstone|indeed|jobs|karriere|xing|monster)"),
    ("classifieds_jobs", "classifieds", r"(kleinanzeigen|immobilien|immowelt|immonet|autoscout|^mobile\.de$|^markt\.de$|wg-gesucht|quoka)"),
    ("entertainment_gaming", "video", r"(youtube|twitch|netflix|disney|prime|joyn|rtlplus|dailymotion|vimeo|crunchyroll|kino|cinema|cinestar|filmstarts|serien|stream)"),
    ("entertainment_gaming", "games", r"(game|spiele|gaming|roblox|minecraft|steam|playstation|xbox|nintendo|ea\.com|wowhead|ogame|hltv|fut\.gg|epicgames)"),
    ("social_community", "social", r"(facebook|instagram|tiktok|twitter|^x\.com$|threads|linkedin|pinterest|snapchat|reddit|vk\.|ok\.ru|discord|telegram|whatsapp|tumblr|quora|gutefrage|forum|community|chat)"),
    ("services", "reference", r"(wikipedia|wiki|duden|dict|leo\.org|linguee|deepl|translate|wörterbuch|woerterbuch)"),
    ("ecommerce", "general", r"(shop|store|kaufen|versand|outlet|markt|discount|deal|gutschein|amazon|ebay|otto|zalando|temu|shein|aliexpress|allegro)"),
]
RULES = [(c, s, re.compile(p, re.I)) for c, s, p in RULES]


def latest_month(cc):
    """Probe the last 12 months, newest first (CrUX lists appear with a delay of a few weeks)."""
    from datetime import date
    y, m = date.today().year, date.today().month
    for _ in range(12):
        month = f"{y}{m:02d}"
        req = urllib.request.Request(CRUX_URL.format(cc=cc, month=month), method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=20):
                return month
        except Exception:  # noqa: BLE001 - not published yet
            pass
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    sys.exit(f"No CrUX list found for country {cc} in the last 12 months")


def load_crux(args):
    if args.input:
        raw = Path(args.input).read_bytes()
        month = args.month or Path(args.input).name[:6]
    else:
        month = args.month or latest_month(args.country)
        url = CRUX_URL.format(cc=args.country, month=month)
        print(f"Downloading {url}")
        with urllib.request.urlopen(url, timeout=60) as r:
            raw = r.read()
    text = gzip.decompress(raw).decode() if raw[:2] == b"\x1f\x8b" else raw.decode()
    rows = list(csv.DictReader(io.StringIO(text)))
    return month, [r for r in rows if int(r["rank"]) <= args.bucket]


def host_of(origin):
    return re.sub(r"^https?://", "", origin).split("/")[0].lower()


def registrable(host):
    e = extract(host)
    rd = getattr(e, "top_domain_under_public_suffix", None) or e.registered_domain
    return rd or host, e.subdomain, e.suffix


def pick_url(origins, domain):
    """Prefer https://www.<domain>, then https://<domain>, then any non-mobile, non-app origin."""
    hosts = {host_of(o): o for o in origins}
    for h in (f"www.{domain}", domain):
        if h in hosts:
            return hosts[h]
    rest = [o for o in origins if not re.match(r"^(m|mobile)\.", host_of(o)) and not APP_SUB_RE.match(host_of(o))]
    pool = rest or origins
    return sorted(pool, key=lambda o: len(host_of(o)))[0]


def load_overrides():
    path = ROOT / "lists" / "category_overrides.csv"
    out = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(line for line in f if not line.startswith("#")):
            out[row["domain"].strip()] = (row["category"].strip(), row["subcategory"].strip())
    return out


def load_excludes():
    path = ROOT / "lists" / "exclude_domains.csv"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return {r["domain"].strip(): (r.get("reason") or "manual").strip()
                for r in csv.DictReader(line for line in f if not line.startswith("#"))}


def categorize(domain, host, overrides):
    if domain in overrides:
        return (*overrides[domain], "override")
    if GAMBLING_RE.search(domain):
        return "gambling", "", "rule"
    for cat, sub, rx in RULES:
        if rx.search(domain) or rx.search(host):
            return cat, sub, "rule"
    return "other", "", "none"


def market_of(suffix):
    return "de" if suffix in ("de", "at", "ch") else "intl"


def fetch_title(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
    })
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            body = r.read(300_000).decode(r.headers.get_content_charset() or "utf-8", "replace")
            m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
            return r.status, unescape(re.sub(r"\s+", " ", m.group(1))).strip()[:150] if m else ""
    except Exception as e:  # noqa: BLE001 - we only record what happened
        return getattr(e, "code", None) or "error", ""


def build(args):
    month, rows = load_crux(args)
    overrides = load_overrides()
    excludes = load_excludes()
    groups = defaultdict(list)
    for r in rows:
        host = host_of(r["origin"])
        domain, _, _ = registrable(host)
        groups[domain].append(r["origin"])

    out = []
    for domain, origins in groups.items():
        url = pick_url(origins, domain)
        host = host_of(url)
        _, sub, suffix = registrable(host)
        cat, subcat, source = categorize(domain, host, overrides)
        reason = ""
        if domain in excludes:
            reason = f"manual: {excludes[domain]}"
        elif IP_RE.match(host):
            reason = "ip_address"
        elif ADULT_RE.search(domain) or ADULT_RE.search(host):
            reason = "adult"
        elif all(APP_SUB_RE.match(host_of(o)) for o in origins):
            reason = "login_or_app_only"
        elif args.exclude_gambling and GAMBLING_RE.search(domain):
            reason = "gambling"
        out.append({
            "url": url, "domain": domain, "category": cat, "subcategory": subcat, "category_source": source,
            "market": market_of(suffix), "keep": 0 if reason else 1, "exclude_reason": reason,
            "crux_month": month, "crux_bucket": args.bucket, "origins_merged": " ".join(sorted(origins)),
            "status": "", "title": "",
        })

    if args.titles:
        todo = [o for o in out if o["keep"]]
        print(f"Fetching titles for {len(todo)} sites (one request each)...")
        with ThreadPoolExecutor(max_workers=6) as ex:
            for o, (status, title) in zip(todo, ex.map(lambda o: fetch_title(o["url"]), todo)):
                o["status"], o["title"] = status, title

    out.sort(key=lambda o: (o["keep"] == 0, o["category"], o["domain"]))
    OUT_DIR.mkdir(exist_ok=True)
    path = Path(args.candidates_out)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    kept = [o for o in out if o["keep"]]
    print(f"\nCrUX {args.country.upper()} {month}, top {args.bucket}: {len(rows)} origins -> {len(groups)} domains")
    print("Excluded:", dict(Counter(o["exclude_reason"] for o in out if not o["keep"])))
    print(f"Kept: {len(kept)}  (market de: {sum(o['market'] == 'de' for o in kept)}, intl: {sum(o['market'] == 'intl' for o in kept)})")
    print("Draft categories (kept):")
    for cat, n in Counter(o["category"] for o in kept).most_common():
        print(f"  {cat:<22} {n}")
    print("Category source (kept):", dict(Counter(o["category_source"] for o in kept)))
    print(f"\nWritten: {path}\nNext: review it by hand (category, keep), then run with --from-reviewed {path} --sample N")


def sample_from_reviewed(args):
    with open(args.from_reviewed, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if str(r.get("keep", "1")).strip() == "1"]
    if args.market != "all":
        rows = [r for r in rows if r["market"] == args.market]
    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)
    rng = random.Random(args.seed)
    n = min(args.sample or len(rows), len(rows))
    # Proportional allocation with a minimum per category (small categories are kept whole).
    alloc = {c: min(len(v), max(args.min_per_category, round(n * len(v) / len(rows)))) for c, v in by_cat.items()}
    while sum(alloc.values()) > n:
        c = max(alloc, key=lambda k: alloc[k] - args.min_per_category)
        alloc[c] -= 1
    chosen = []
    for c, v in by_cat.items():
        chosen += rng.sample(v, alloc[c])
    chosen.sort(key=lambda r: (r["category"], r["domain"]))
    path = Path(args.out)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["url", "category", "subcategory", "domain", "market"])
        for r in chosen:
            w.writerow([r["url"], r["category"], r["subcategory"], r["domain"], r["market"]])
    print(f"Sample of {len(chosen)} sites (seed {args.seed}) -> {path}")
    for c in sorted(alloc, key=lambda k: -alloc[k]):
        print(f"  {c:<22} {alloc[c]:>4} of {len(by_cat[c])}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--country", default="de")
    p.add_argument("--month", help="YYYYMM; default: latest available")
    p.add_argument("--input", help="local CrUX csv or csv.gz instead of downloading")
    p.add_argument("--bucket", type=int, default=1000, help="CrUX rank bucket: 1000, 5000, 10000, ...")
    p.add_argument("--titles", action="store_true", help="fetch each home page title for the manual review")
    p.add_argument("--exclude-gambling", action="store_true")
    p.add_argument("--from-reviewed", help="build the final sample from a reviewed candidates.csv")
    p.add_argument("--sample", type=int, help="sample size (stratified by category)")
    p.add_argument("--min-per-category", type=int, default=10)
    p.add_argument("--market", choices=["all", "de", "intl"], default="all")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default=str(ROOT / "sites_study.csv"))
    p.add_argument("--candidates-out", default=str(OUT_DIR / "candidates.csv"),
                   help="where to write the candidate list (use another file for the top-5000 boost)")
    args = p.parse_args()
    if args.from_reviewed:
        sample_from_reviewed(args)
    else:
        build(args)


if __name__ == "__main__":
    main()
