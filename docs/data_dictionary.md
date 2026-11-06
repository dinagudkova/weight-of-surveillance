# Data dictionary

Tables used by the dashboard, the statistics notebook and `scripts/results_numbers.py`. All marts live in schema
`marts` (DuckDB `data/warehouse/wos.duckdb` and PostgreSQL on Neon, same content) and are built by dbt from the
raw crawl. How the data was collected: [methodology.md](methodology.md).

## Conventions

- **Main dataset only.** Every mart uses `dataset = 'real'` (dbt var `main_dataset`).
- **Modes:** `none` (no choice, banner left alone), `accept` (Accept all), `reject` (Reject all).
- **Window:** the 30 seconds after the consent click (`none`: after the 4-second page load). Counts named
  `*_tracking_requests`, `*_tracking_bytes`, `*_companies` refer to the window unless the name starts with `pre_`.
- **Lower bound:** an Accept visit where the browser ran out of memory; its counts include every request until the
  stop and are too low (`is_lower_bound`, `accept_is_lower_bound`).
- **Usable:** measured, and for Accept/Reject the click was verified. Per-site values are medians over the site's
  usable visits.
- **Company:** owner of a tracking domain in the DuckDuckGo entity list; self-hosted tracking
  (`<site> (first-party)`) is tracking but not a company.
- Bytes are transferred bytes; times in milliseconds.

## Site attributes (shared by several marts)

| Column | Type | Meaning |
|---|---|---|
| `site` | text | site origin, e.g. `https://www.spiegel.de`; key for joins |
| `site_domain` | text | registrable domain, e.g. `spiegel.de` |
| `site_category` | text | fine category from the sample review (e.g. `news_media`, `ecommerce`) |
| `site_category_group` | text | group key (`media`, `shopping`, `services_entertainment`, `finance_health`, `public_education`, `gambling`) |
| `site_group_label` | text | group name for display (Media, Shopping, Services & entertainment, Finance & health, Public sector & education, Gambling) |
| `site_group_order` | integer | display order of the groups (1 = Media) |
| `site_subcategory` | text | finer label where one exists |
| `site_sample_source` | text | `crux_top1000` or `crux_top5000_boost` (public sector, health, finance added from the top 5,000) |
| `site_country` | text | country by top-level domain: `DE`, `AT`, `CH`, `other` |
| `cmp` | text | consent platform detected (Sourcepoint, Usercentrics, …; `Unknown (generic banner)` when a banner was seen but no known platform; autoconsent's heuristic mode is stored this way) |

## mart_site_consent_effect

One row per site with at least one usable visit (507). Used by: Freedom of choice, The weight, Before you click,
Check a site; the notebook.

| Column | Type | Meaning |
|---|---|---|
| site attributes | | see above |
| `none_tracking_requests` | double | tracking requests in the window, no choice (median per site) |
| `reject_tracking_requests` | double | same after Reject; null where no usable Reject visit |
| `accept_tracking_requests` | double | same after Accept; a lower bound where `accept_is_lower_bound` |
| `none_tracking_bytes`, `reject_tracking_bytes`, `accept_tracking_bytes` | double | bytes of those requests |
| `accept_tracking_share_bytes` | double | share of tracking in all bytes of phases pre + window after Accept (0–1); null for lower-bound visits |
| `accept_tracking_companies` | double | distinct tracking companies after Accept |
| `accept_identity_requests`, `reject_identity_requests` | double | identity requests (ID syncing, cookie matching, telco identifiers) in the window |
| `reject_analytics_requests` | double | analytics requests after Reject |
| `none_script_ms`, `accept_script_ms` | double | JavaScript run time of the page by the end of the visit |
| `modes_measured` | bigint | number of modes with a usable visit (1–3) |
| `accept_is_lower_bound` | boolean | the Accept visit was stopped by a memory overflow |
| `has_banner` | boolean | a consent banner was seen on the site in any visit |
| `pay_or_okay` | boolean | the banner offers a paid, tracking-free subscription (does not by itself mean no free reject) |
| `reject_option` | text | `reject on first layer` (no paid option, reject worked), `reject only in settings` (paid option, a free reject worked anyway), `no reject without subscription` (paid option, no free reject found), `reject not verified` (no paid option, reject not verified), `no banner` |
| `accept_vs_none_ratio` | double | Accept ÷ no-choice tracking requests (null when no-choice is 0) |
| `accept_tenfold` | boolean | Accept ≥ 10 × max(no choice, 1) tracking requests |

## mart_group_summary

One row per group (6). Used by: Consent effect by group; About the data (counts).

| Column | Type | Meaning |
|---|---|---|
| `category_group`, `group_label`, `group_order` | text, text, integer | group key, display name, order |
| `sites` | bigint | sites with data in the group |
| `sites_boost` | bigint | of them from the top-5,000 boost |
| `sites_with_banner` | bigint | sites with a consent banner |
| `sites_outside_de` | bigint | sites with `site_country` ≠ `DE` |
| `median_none_tracking_requests`, `median_reject_tracking_requests`, `median_accept_tracking_requests` | double | medians over banner sites |
| `median_accept_tracking_companies` | double | median companies after Accept, banner sites |
| `median_accept_tracking_bytes`, `median_accept_identity_requests` | double | medians after Accept, banner sites |
| `sites_accept_tenfold` | bigint | banner sites with `accept_tenfold` |
| `sites_pay_or_okay` | bigint | sites with a paid option |
| `sites_no_free_reject` | bigint | sites with `reject_option = 'no reject without subscription'` |
| `sites_accept_lower_bound` | bigint | sites whose Accept value is a lower bound |

## mart_pre_consent

One row per site with a usable no-choice visit (503). Page load (phase `pre`) of the no-choice visit, before the
banner could be answered. Used by: Before you click, Check a site.

| Column | Type | Meaning |
|---|---|---|
| `site`, `site_domain`, `site_country`, `site_category` | text | see site attributes |
| `pre_tracking_requests` | double | tracking requests during page load |
| `pre_advertising_requests` | double | advertising requests during page load |
| `pre_identity_requests` | double | identity requests during page load |
| `tracker_cookies_before_choice` | integer | tracker cookies set before any choice |
| `tracker_cookie_owners` | text | companies behind those cookies |

## mart_consent_timeline

One row per mode × group × second (0–29), plus group `All sites`. Usable visits on banner sites, lower-bound visits
excluded. Used by: First seconds.

| Column | Type | Meaning |
|---|---|---|
| `mode` | text | none, reject, accept |
| `site_group_label`, `site_group_order` | text, integer | group (`All sites` = 0) |
| `second` | integer | second of the window; `0` covers 0–1 s, so the value is "by the end of second `second + 1`" |
| `visits` | bigint | visits in the cell |
| `median_cum_tracking_requests` | double | tracking requests since the window start, median per visit |
| `median_cum_companies` | double | companies reached since the window start, median per visit |
| `share_sites_tracking_started` | double | share of visits with at least one tracking request so far (0–1) |

## mart_first_tracker

One row per usable visit on a banner site (lower bounds excluded). Used by: the notebook, results.

| Column | Type | Meaning |
|---|---|---|
| `visit_id`, `site`, site attributes, `mode` | | visit key and site |
| `window_start_ms` | integer | window start in ms after navigation (the click for Accept/Reject) |
| `ms_to_first_tracking`, `ms_to_first_advertising`, `ms_to_first_identity_sync` | integer | ms from the window start to the first request of that kind |
| `tracking_requests_1s`, `tracking_requests_5s` | bigint | tracking requests within the first 1 and 5 seconds |
| `companies_1s`, `companies_5s`, `companies_30s` | bigint | companies reached within 1, 5 and 30 seconds |

## mart_company_sites

One row per company × mode, on sites with a banner. Used by: Companies.

| Column | Type | Meaning |
|---|---|---|
| `owner` | text | company |
| `mode` | text | none, reject, accept |
| `sites` | bigint | banner sites on which the company receives tracking requests in the window |
| `sites_measured` | bigint | banner sites with a usable visit in that mode (Accept 385, Reject 301) |
| `share_of_sites` | double | `sites ÷ sites_measured` (0–1) |
| `requests`, `bytes` | bigint | tracking requests and bytes to the company |
| `tracking_types` | text | advertising, analytics, identity (comma-separated) |
| `rank_in_mode` | bigint | rank by sites within the mode (1 = most sites) |

(`mart_company_reach` has the same data split by tracking type; its site counts cannot be added up per company.)

## mart_cmp_market

One row per consent platform, sites with a banner (449 in total). Used by: Consent platforms.

| Column | Type | Meaning |
|---|---|---|
| `cmp` | text | consent platform (`not detected`: banner seen, no platform recognised) |
| `sites` | bigint | sites using it |
| `sites_pay_or_okay` | bigint | of them with a paid option |
| `median_consent_bytes` | double | bytes of the banner itself; only measured for known platform domains (0 = not measured) |

## mart_promise_vs_reality

One row per site with data (507). Used by: Promise vs reality, Check a site.

| Column | Type | Meaning |
|---|---|---|
| site attributes, `cmp`, `pay_or_okay`, `has_banner` | | as above |
| `tcf_accept_verified` | boolean | the Accept click in the TCF crawl was verified |
| `tcf_available` | boolean | the page exposes the IAB TCF API (`__tcfapi`) |
| `tcf_event_status` | text | TCF event status after the click (`useractioncomplete`, `tcloaded`, …) |
| `tcf_valid` | boolean | TCF data usable: API present, click verified, status complete |
| `promised_iab_vendors` | integer | IAB vendors consented to after Accept all (when `tcf_valid`) |
| `promised_other_vendors` | integer | Google Additional Consent vendors (when `tcf_valid`) |
| `promised_vendors_total` | integer | sum of the two; null without a valid TCF banner |
| `asks_full_gvl` | boolean | consent asked for (almost) the whole IAB vendor list |
| `declared_partners_text` | integer | number of partners stated in the banner text, where readable |
| `observed_companies` | double | tracking companies seen after Accept (main crawl) |
| `observed_is_lower_bound` | boolean | the Accept visit was a lower bound |
| `promised_per_observed` | double | `promised_vendors_total ÷ observed_companies` |

## fct_visits

One row per visit, all datasets (filter `dataset = 'real'`). Basis of all marts; used directly by the notebook and
the check scripts. Main columns:

| Column | Type | Meaning |
|---|---|---|
| `dataset`, `visit_id`, `site`, `mode`, `rep` | | visit key |
| `visited_at`, `machine` | timestamp, text | when and on which crawl machine |
| `is_measured`, `is_usable`, `is_lower_bound` | boolean | see conventions |
| `bot_blocked`, `nav_error` | boolean, text | bot-protection page; navigation error |
| `banner_pre` | boolean | banner visible in the pre snapshot (weak signal: autoconsent often finds banners the snapshot misses) |
| `consent_method`, `consent_verified` | text, boolean | `autoconsent`, `text-fallback`, both; whether the banner was verifiably closed |
| `site_has_banner`, `site_pay_or_okay`, `site_reject_verified` | boolean | site-level flags copied to every visit |
| `window_ms`, `script_ms` | integer | window length; JavaScript run time |
| `tracking_requests`, `tracking_bytes`, `tracking_companies` | | window counts (all phases for lower-bound visits) |
| `advertising_requests`, `analytics_requests`, `identity_requests`, `telemetry_requests` | bigint | window counts by type |
| `pre_tracking_requests`, `pre_advertising_requests`, `pre_identity_requests` | bigint | page-load counts |
| `cookies_pre_tracker`, `cookies_end_tracker` | integer | tracker cookies before the choice and at the end |
| `visit_bytes`, `observed_bytes`, `tracking_share_bytes` | | all bytes; bytes of phases pre + window; tracking share of the latter |

## docs/funnel.csv

Five rows for the "About the data" sheet; fixed numbers from [results_numbers.md](results_numbers.md).

| Column | Type | Meaning |
|---|---|---|
| `stage` | text | Sample, With data, With a consent banner, Verified Accept, Verified Reject |
| `sites` | integer | 525, 507, 449, 385, 301 |
| `order` | integer | display order |
