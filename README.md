# The Weight of Surveillance

**How much of the German web is tracking, and what changes when you click "Accept" or "Reject"?**

This project measures how much of a web page's weight (requests, bytes, script time) comes from third-party tracking on popular German websites. Every site is visited in three states:

- `none`: no interaction with the cookie banner
- `accept`: "Accept all" clicked
- `reject`: "Reject all" clicked

Business questions are listed in [docs/business_questions.md](docs/business_questions.md).

> Status: pilot finished (25 sites, 3 repeats). Full study in progress.

## Pipeline

```
CrUX top list ──► sample + categories (Python) ──► crawler (Node.js + Playwright)
                                                       │
                                                       ▼
                                           raw JSONL + screenshots (local)
                                                       │
                                        loader (Python) ▼
                                       DuckDB (local)  /  PostgreSQL (Neon)
                                                       │
                                                  dbt  ▼
                                    staging ─► classification ─► marts + tests
                                                       │
                                                       ▼
                                        analysis (Python) + Tableau dashboard
```

## How a visit works

1. Load the page in a fresh browser profile, wait 4 seconds.
2. **Pre snapshot:** is a consent banner visible, is the page a bot-protection page, is the banner "pay or okay", which cookies are already set.
3. **Consent action** (`accept` / `reject` only): first [DuckDuckGo autoconsent](https://github.com/duckduckgo/autoconsent), then a fallback click on typical button labels (also inside shadow DOM and consent iframes). The crawler then **verifies** that the banner is gone.
4. **Observation window** of fixed length (30 s by default), starting at the consent click (or, in `none`, right after the pre snapshot). The main metrics only use requests that start inside this window, so all states are observed equally long.
5. **End snapshot:** cookies, script time, screenshots (before the click, after the click, end of window).

## Request classification

| Category | Meaning | Source |
|---|---|---|
| `consent` | the consent banner itself | `lists/cmp_domains.txt` |
| `tracking` | advertising, analytics or identity syncing | DuckDuckGo Tracker Data Set (with categories), EasyPrivacy, EasyList (third party only), `lists/custom_trackers.csv` (German ad-tech), CNAME cloaking via DNS |
| `telemetry` | error monitoring, performance monitoring, A/B testing (not counted as tracking) | `lists/custom_trackers.csv` |
| `first-party` | the site and domains owned by the same company | DuckDuckGo entities, `lists/site_aliases.csv` |
| `other` | other third parties: CDNs, fonts, video, payment | everything else |

Tracking is further split into `advertising`, `analytics` and `identity` (ID syncing, cookie matching, telco identifiers). Tracker cookies are detected by domain and by name (`_ga`, `_fbp`, ..., see `lists/tracker_cookie_names.txt`).

## Quick start

Requirements: Node.js 18+, Python 3.10+.

```bash
npm install
npx playwright install chromium
pip install -r requirements.txt
bash update_lists.sh          # download third-party tracker lists

node crawl.mjs --mock --out results_mock --window 10      # offline self-test (~2 min)
node crawl.mjs --sites sites_pilot.csv --out results --workers 2
node reclassify.mjs results   # re-apply classification after list changes, no new crawl
python3 analyze.py results    # writes results/pilot_report.md
```

Useful crawler options:

| Option | Effect |
|---|---|
| `--repeats 3` | visit every site and state several times |
| `--modes accept` | only selected states |
| `--retry-failed` | re-run visits with errors or bot protection |
| `--fresh` | re-run visits that already exist (the analysis keeps the latest) |
| `--headed` | visible browser |
| `--window 30` | observation window in seconds |
| `--restart-every 6` | restart the browser every N visits (limits memory) |
| `--pause 3` | pause between visits, in seconds |

A run can be stopped and restarted: finished visits are skipped.

## Output files

| File | Content |
|---|---|
| `visits.jsonl` | one row per visit: banner, consent method and verification, flags, cookies, script time |
| `requests.jsonl` | one row per request: start time, phase (`pre` / `window` / `after`), size, category, owner |
| `summary_by_visit.csv` | metrics per visit |
| `review_domains.csv` | third-party domains classified as `other`, for manual review |
| `review_tracking.csv` | top domains classified as tracking, to catch false positives |
| `screens/` | screenshots per visit |
| `pilot_report.md` | report |

Raw data and screenshots are not part of this repository.

## Measurement setup

- Crawled from Germany through a German VPN exit, desktop viewport 1366×900, locale `de-DE`.
- Gentle crawling: random order, pause between visits, two parallel browsers.
- Only home pages, no login.

## Limitations

- About 16% of the pilot sites block automated browsers and cannot be measured.
- Server-side tracking (e.g. on Amazon) is not visible from the browser.
- International tracker lists miss part of the German ad-tech market; the custom lists are reviewed manually.
- The number of clicks to reject cannot be measured for consent platforms controlled through an API (e.g. Sourcepoint).
- Requests sent before consent are indicators, not proof of a legal violation.

## Data sources and licences

- Site sample: [Chrome UX Report top lists](https://github.com/zakird/crux-top-lists)
- [DuckDuckGo Tracker Blocklists](https://github.com/duckduckgo/tracker-blocklists) and [autoconsent](https://github.com/duckduckgo/autoconsent)
- [EasyList / EasyPrivacy / EasyList Germany](https://easylist.to/)

Third-party lists keep their own licences.
