# Results: the numbers

Single source for every number used in the README, the dashboard captions and the presentation. Each table
names the mart it comes from. To re-check all of them after a rebuild:

```bash
python scripts/dbt.py build
python scripts/results_numbers.py
```

Dataset: real-browser crawl (`main_dataset: real`), DuckDB warehouse, same results in PostgreSQL on Neon.
Medians are medians over sites; accept/reject medians only use sites with a consent banner.

Status of each section: **checked** = compared against the marts on 2026-11-02; **to check** = from an
earlier summary, confirm with `scripts/results_numbers.py` before publishing.

## Sample (checked)

| | Sites | Source |
|---|---|---|
| Sample (CrUX top 1,000 DE + top-5,000 boost for public sector, health, finance) | 525 | `seeds.sites` |
| Sites with data | 507 | `mart_site_consent_effect` |
| Sites with a consent banner | 449 | `mart_group_summary.sites_with_banner` |
| Sites outside Germany (`site_country`): 20min.ch, blick.ch, nzz.ch, watson.ch (CH), kurier.at, asfinag.at (AT) | 6 | `mart_site_consent_effect.site_country` |

The CrUX list for Germany ranks sites popular with users in Germany, so it includes a few Swiss and Austrian
sites. They stay in the sample and are flagged with `site_country`; five of the six are media sites.

## Consent effect by group (checked)

Source: `mart_group_summary`. Tracking requests in the 30-second window, median per site.

| Group | Sites | With banner | No choice | Reject | Accept | Companies after Accept | Accept lower bound |
|---|---|---|---|---|---|---|---|
| Media | 185 | 165 | 0 | 4 | 1,069 | 100 | 60 |
| Shopping | 124 | 118 | 0 | 3 | 81 | 11.5 | 0 |
| Services & entertainment | 105 | 96 | 0 | 2 | 91 | 9 | 11 |
| Finance & health | 52 | 48 | 0 | 0 | 28 | 4 | 2 |
| Public sector & education | 29 | 10 | 0 | 0 | 0.5 | 0 | 0 |
| Gambling | 12 | 12 | 0 | 2 | 37 | 5 | 0 |

"Accept lower bound": the browser ran out of memory after Accept; these sites enter with the requests counted
until the stop, so the true medians are higher (most of all for media).

## Consent platforms (checked)

Source: `mart_cmp_market`. 449 sites with a banner, one platform per site.

| Platform | Sites | With a paid option |
|---|---|---|
| Sourcepoint | 104 | 78 |
| Usercentrics | 76 | 5 |
| consentmanager | 72 | 38 |
| Unidentified (generic banner 47, no platform detected 15) | 62 | 2 |
| OneTrust | 39 | 1 |
| opencmp (Ippen) | 25 | 20 |
| In-house banner | 17 | 1 |
| Cookiebot | 15 | 0 |
| Didomi | 13 | 2 |

## Paid option in the banner (checked)

Source: `fct_visits.site_pay_or_okay` (sites with a banner). The flag means the banner offers a paid,
tracking-free subscription. It does not by itself mean there is no free reject: kleinanzeigen.de, for example,
offers both (checked by hand). markt.de offers only "Accept all" or a subscription (checked by hand).

| Group | Sites with a paid option |
|---|---|
| Media | 113 |
| Services & entertainment | 26 |
| Finance & health | 7 |
| Shopping | 2 |
| Public sector & education, Gambling | 0 |
| **Total** | **148** |

Outside media these are mostly ad-funded content sites: recipes, gaming, health and finance portals.

**To check:** media sites without a free reject: 63 (`mart_group_summary.sites_no_free_reject`).

## The first seconds after the choice (checked)

Source: `mart_consent_timeline`. Usable visits on sites with a banner, memory-aborted visits excluded
(312 Accept, 301 Reject, 446 No-choice visits). Companies contacted by the end of each second, median.

| By the end of second | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Accept, all sites | 6 | 8 | 10 | 10 | 10.5 | 11.5 |
| Share of sites where tracking had started: Reject | 41% | 47% | 49% | 50% | 52% | 52% |
| Share of sites where tracking had started: No choice | 16% | 21% | 23% | 25% | 27% | 28% |

The median tracking after Reject is close to zero, but on about half of the sites at least one tracking request
starts within five seconds of the click.

**To check:** media, Accept: ~12 companies by the end of second 1 and ~42 by the end of second 5; first tracking
request ~70 ms after the Accept click (`mart_first_tracker`).

## Promise vs reality (checked)

Source: `mart_promise_vs_reality`. Sites with an IAB TCF banner. Promised: vendors in the TCF consent after
"Accept all" plus Google Additional Consent vendors. Seen: distinct tracking companies after Accept.

| Group | TCF sites | Promised (median) | Seen (median) | Seen is a lower bound |
|---|---|---|---|---|
| Media | 101 | 210 | 101 | 31 |
| Shopping | 17 | 102 | 12 | 0 |
| Services & entertainment | 36 | 221 | 36 | 4 |
| Finance & health | 5 | 146 | 90 | 0 |
| Public sector & education | 1 | 198 | 28 | 0 |
| Gambling | 0 | – | – | – |

Finance & health and public sector are too small to compare and are left out of the dashboard. 7 sites ask
consent for the entire IAB vendor list (900+ vendors). One company can run several TCF vendors, so the
comparison is approximate.

On TCF sites more companies are seen than on all sites of the same group (services: 36 vs 9): the TCF banner is
used mostly by ad-funded content sites.

## To check before publishing

These come from earlier summaries and have not yet been re-run against the current marts:

- Share of tracking in the page weight after Accept (pre + window): media 55%, other groups 13–24%.
- ID syncing before any choice on ~29 sites (core: the Ippen network, confirmed by hand on mannheim24.de) and after
  Reject on ~18 sites (confirmed by hand on vevor.de, frankenpost.de; partners claim "legitimate interest").
  Indicators, not proof of a violation. A dedicated ID-sync mart is planned.
- Bot-blocked sites: 48 in the first crawl, 38 re-measured from a home connection; 11 sites (~2%) could not be
  measured. 48 − 38 = 10, so one of these counts needs checking; 525 − 507 = 18 sites have no data at all.
