git add -A
git commit -m "Reject options: describe what the categories measure"
git push# Results: the numbers

Single source for every number used in the README, the dashboard captions and the presentation. Each table
names the mart it comes from. To re-check all of them after a rebuild:

```bash
python scripts/dbt.py build
python scripts/results_numbers.py
```

Dataset: real-browser crawl (`main_dataset: real`), DuckDB warehouse, same results in PostgreSQL on Neon.
Medians are medians over sites; accept/reject medians only use sites with a consent banner.

All sections were compared against the output of `scripts/results_numbers.py` on 2026-11-02, except the
last one ("Still open").

## Sample

|                                                                                                                  | Sites | Source                                    |
| ---------------------------------------------------------------------------------------------------------------- | ----- | ----------------------------------------- |
| Sample (CrUX top 1,000 DE + top-5,000 boost for public sector, health, finance)                                  | 525   | `seeds.sites`                           |
| Sites with data                                                                                                  | 507   | `mart_site_consent_effect`              |
| Sites with a consent banner                                                                                      | 449   | `mart_group_summary.sites_with_banner`  |
| Sites outside Germany (`site_country`): 20min.ch, blick.ch, nzz.ch, watson.ch (CH), kurier.at, asfinag.at (AT) | 6     | `mart_site_consent_effect.site_country` |

The CrUX list for Germany ranks sites popular with users in Germany, so it includes a few Swiss and Austrian
sites. They stay in the sample and are flagged with `site_country`; five of the six are media sites.

## Consent effect by group

Source: `mart_group_summary`. Tracking requests in the 30-second window, median per site. In mode "No choice"
the window starts after the page has loaded (about 4 s), so tracking during page load is not in this table; see
"Before any choice" below.

| Group                     | Sites | With banner | No choice | Reject | Accept | Companies after Accept | Accept lower bound |
| ------------------------- | ----- | ----------- | --------- | ------ | ------ | ---------------------- | ------------------ |
| Media                     | 185   | 165         | 0         | 4      | 1,069  | 100                    | 60                 |
| Shopping                  | 124   | 118         | 0         | 3      | 81     | 11.5                   | 0                  |
| Services & entertainment  | 105   | 96          | 0         | 2      | 91     | 9                      | 11                 |
| Finance & health          | 52    | 48          | 0         | 0      | 28     | 4                      | 2                  |
| Public sector & education | 29    | 10          | 0         | 0      | 0.5    | 0                      | 0                  |
| Gambling                  | 12    | 12          | 0         | 2      | 37     | 5                      | 0                  |

"Accept lower bound": the browser ran out of memory after Accept; these sites enter with the requests counted
until the stop, so the true medians are higher (most of all for media).

## Consent platforms

Source: `mart_cmp_market`. 449 sites with a banner, one platform per site.

| Platform                                                  | Sites | With a paid option |
| --------------------------------------------------------- | ----- | ------------------ |
| Sourcepoint                                               | 104   | 78                 |
| Usercentrics                                              | 76    | 5                  |
| consentmanager                                            | 72    | 38                 |
| Unidentified (generic banner 47, no platform detected 15) | 62    | 2                  |
| OneTrust                                                  | 39    | 1                  |
| opencmp (Ippen)                                           | 25    | 20                 |
| In-house banner                                           | 17    | 1                  |
| Cookiebot                                                 | 15    | 0                  |
| Didomi                                                    | 13    | 2                  |

## Paid option in the banner

Source: `fct_visits.site_pay_or_okay` (sites with a banner). The flag means the banner offers a paid,
tracking-free subscription. It does not by itself mean there is no free reject: kleinanzeigen.de, for example,
offers both (checked by hand). markt.de offers only "Accept all" or a subscription (checked by hand).

| Group                               | Sites with a paid option |
| ----------------------------------- | ------------------------ |
| Media                               | 113                      |
| Services & entertainment            | 26                       |
| Finance & health                    | 7                        |
| Shopping                            | 2                        |
| Public sector & education, Gambling | 0                        |
| **Total**                     | **148**            |

Outside media these are mostly ad-funded content sites: recipes, gaming, health and finance portals.

### Reject options

Source: `mart_site_consent_effect.reject_option` (sites with a banner). The categories combine two facts: whether
the banner offers a paid subscription (`pay_or_okay`) and whether the crawler managed a working reject
(`consent_verified` in a Reject visit). They do not record where on the banner the reject was found.

| Reject option (value in the mart)  | Meaning                                                                                                                                | All groups    | Media         |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ------------- | ------------- |
| `reject on first layer`          | no paid option, reject worked                                                                                                          | 235           | 33            |
| `reject only in settings`        | paid option, a free reject worked anyway (the first layer offers accept or subscribe, so the reject sits deeper, e.g. in the settings) | 66            | 48            |
| `no reject without subscription` | paid option, the crawler found no free way to reject                                                                                   | 82            | 65            |
| `reject not verified`            | no paid option, reject could not be verified                                                                                           | 66            | 19            |
| **Total**                    |                                                                                                                                        | **449** | **165** |

So every one of the 148 banners with a paid option either hides the free reject below the first layer or, as
far as the crawler could tell, has none. "No free reject found" is the crawler's result, not a proof; markt.de
was checked by hand (only "Accept all" or a subscription), kleinanzeigen.de has a free reject in the settings.

"No free reject found" by group (`mart_group_summary.sites_no_free_reject`): media 65, services &
entertainment 13, shopping 2, finance & health 2.

## The first seconds after the choice

Source: `mart_consent_timeline`. Usable visits on sites with a banner, memory-aborted visits excluded
(312 Accept, 301 Reject, 446 No-choice visits). Companies contacted by the end of each second, median.

| By the end of second                                 | 1   | 2   | 3   | 4   | 5    | 6    |
| ---------------------------------------------------- | --- | --- | --- | --- | ---- | ---- |
| Accept, all sites                                    | 6   | 8   | 10  | 10  | 10.5 | 11.5 |
| Share of sites where tracking had started: Reject    | 41% | 47% | 49% | 50% | 52%  | 52%  |
| Share of sites where tracking had started: No choice | 16% | 21% | 23% | 25% | 27%  | 28%  |

The median tracking after Reject is close to zero, but on about half of the sites at least one tracking request
starts within five seconds of the click.

First tracking request and companies reached after Accept, median per visit (`mart_first_tracker`, same visits):

| Group                     | Visits | First tracking request (ms after the click) | Companies by 1 s | by 5 s | by 30 s |
| ------------------------- | ------ | ------------------------------------------- | ---------------- | ------ | ------- |
| Media                     | 83     | 68                                          | 12               | 42     | 91      |
| Shopping                  | 104    | 28                                          | 7                | 11.5   | 11.5    |
| Services & entertainment  | 71     | 113                                         | 3                | 5      | 5       |
| Finance & health          | 35     | 71                                          | 2                | 3      | 3       |
| Public sector & education | 8      | 16.5                                        | 0                | 0      | 0       |
| Gambling                  | 11     | 14.5                                        | 5                | 5      | 5       |

Media visits here exclude the 60 memory-aborted ones, so the heaviest media sites are missing.

## Companies

Source: `mart_company_sites` (sites with a banner; window phase, plus all phases of the 73 memory-aborted Accept
visits). Share of the sites with a usable visit in that mode on which the company receives tracking requests.
A company is an owner in the tracker lists: Google LLC includes DoubleClick, Google Analytics and Google Ads.

| Rank | After Accept (385 sites) | Sites | Share | After Reject (301 sites) | Sites | Share |
|---|---|---|---|---|---|---|
| 1 | Google | 342 | 89% | Google | 72 | 24% |
| 2 | Microsoft | 285 | 74% | Microsoft | 25 | 8% |
| 3 | Criteo | 229 | 59% | Virtual Minds | 14 | 5% |
| 4 | Adobe | 228 | 59% | Criteo | 14 | 5% |
| 5 | Virtual Minds | 224 | 58% | Adobe | 14 | 5% |
| 6 | PubMatic | 219 | 57% | PubMatic | 12 | 4% |
| 7 | RTB House | 215 | 56% | Amazon | 10 | 3% |
| 8 | Smartadserver | 213 | 55% | The Trade Desk | 10 | 3% |
| 9 | Index Exchange | 213 | 55% | ID5 | 9 | 3% |
| 10 | IPONWEB | 211 | 55% | Outbrain | 8 | 3% |
| 11 | Outbrain | 210 | 55% | Relevant Digital | 8 | 3% |
| 12 | ID5 | 205 | 53% | trustedshops.com | 8 | 3% |
| 13 | Improve Digital | 205 | 53% | Taboola | 7 | 2% |
| 14 | TripleLift | 201 | 52% | CleverPush | 7 | 2% |
| 15 | The Trade Desk | 199 | 52% | Piano Software | 7 | 2% |

After Accept, even the 15th company reaches more than half of the sites: the ad-tech market behind the banners
is wide, not just Google. After Reject, Google is the only company still seen on a large share of sites.

## Promise vs reality

Source: `mart_promise_vs_reality`. Sites with an IAB TCF banner. Promised: vendors in the TCF consent after
"Accept all" plus Google Additional Consent vendors. Seen: distinct tracking companies after Accept.

| Group                     | TCF sites | Promised (median) | Seen (median) | Seen is a lower bound |
| ------------------------- | --------- | ----------------- | ------------- | --------------------- |
| Media                     | 101       | 210               | 101           | 31                    |
| Shopping                  | 17        | 102               | 12            | 0                     |
| Services & entertainment  | 36        | 221               | 36            | 4                     |
| Finance & health          | 5         | 146               | 90            | 0                     |
| Public sector & education | 1         | 198               | 28            | 0                     |
| Gambling                  | 0         | –                | –            | –                    |

Finance & health and public sector are too small to compare and are left out of the dashboard. 7 sites ask
consent for the entire IAB vendor list (900+ vendors). One company can run several TCF vendors, so the
comparison is approximate.

On TCF sites more companies are seen than on all sites of the same group (services: 36 vs 9): the TCF banner is
used mostly by ad-funded content sites.

## Before any choice: tracking during page load

Source: `mart_pre_consent` (mode "No choice", load phase before the pre snapshot, usable visits) joined with
`mart_site_consent_effect.has_banner`; companies from `prep_requests_classified`.

| Group                     | Sites with a banner | Advertising requests before any choice | Identity requests | Tracker cookies |
| ------------------------- | ------------------- | -------------------------------------- | ----------------- | --------------- |
| Media                     | 164                 | 99                                     | 23                | 36              |
| Shopping                  | 117                 | 39                                     | 4                 | 26              |
| Services & entertainment  | 96                  | 42                                     | 7                 | 16              |
| Finance & health          | 48                  | 10                                     | 2                 | 10              |
| Public sector & education | 10                  | 1                                      | 0                 | 1               |
| Gambling                  | 11                  | 4                                      | 1                 | 4               |
| **Total**           | **446**       | **195**                          | **37**      | **93**    |

Over all 503 sites with a usable "No choice" visit (with or without a banner), 406 send at least one tracking
request during page load and 98 set a tracker cookie.

Most frequent companies before any choice on sites with a banner: Google (analytics on 172 sites, advertising
on 106), Adobe (analytics, 39), Amazon (analytics and advertising, 29 each), Microsoft (advertising, 22), Criteo
(advertising, 19), Utiq (identity, 18), The Trade Desk (identity, 11).

How to read this: a request is not the same as data collection with consent-free identifiers. Google's Consent
Mode, for example, sends cookieless pings before a choice by design, and many ad requests only load code. The
next section looks at Google in detail. The table is an indicator for manual checks, not proof of a violation. After the page has loaded, while the banner stays unanswered, almost nothing
more happens (median 0 tracking requests in the 30-second window).

## Google before any choice: consent signals

Source: `scripts/check_google_consent_mode.py` (same visits as above: mode "No choice", page load, sites with a
banner, requests owned by Google). Each Google request is split into **code** (scripts, configuration, Google's
ad-fraud checks: `/pagead/managed`, `/pagead/js`, sodar, `generate_204`, ...) and **hits** (analytics collect,
conversion and Floodlight pixels, cookie matching, remarketing, ad requests), and the consent signal in the hit's
URL is read: `gcs=G1xy` (Google Consent Mode; x = ad_storage, y = analytics_storage), `gdpr_consent=` (IAB TCF),
`npa=1` (non-personalised ads).

| Strongest signal among a site's Google hits before any choice                    | Sites        | With advertising hits |
| -------------------------------------------------------------------------------- | ------------ | --------------------- |
| Consent Mode reports ad_storage**granted**                                 | 6            | 4                     |
| Consent Mode reports analytics_storage granted (ads denied)                      | 1            | 0                     |
| Hits without any denied signal                                                   | 36           | 32                    |
| Only denied, empty or non-personalised signals, or URLs cut before the parameter | 36           | 27                    |
| **Sites with Google hits before any choice**                               | **79** |                       |

Loading Google code before a choice (gtag/GTM on 171 sites, ad libraries on 59) is not counted.

- **Granted before any click (6 sites):** baur.de, xn--schnppchenportal-ynb.de, bwin.de, fr.de, vevor.de,
  op-online.de; analytics only: opodo.de. fr.de and op-online.de belong to the Ippen network, which also syncs IDs
  before a choice; vevor.de also syncs IDs after Reject.
- **Manual check, 2 November 2026** (Chrome profile without extensions, banner left open, nothing clicked):
  bwin.de **confirmed**: about 3 s after load a `pageView` goes to www.google.com with `gcs=G111` (ads and
  analytics granted), plus GA4 hits with `G111` through the site's own domain (`www.bwin.de/dlr/g/collect`,
  server-side tagging), repeated every ~5 s. **Not reproduced** on baur.de (only `gtm.js` from Google; 13 POST
  requests to the site's own collector `te.baur.de/collect`, content not visible) and fr.de (no Google request
  before a choice). Each crawler visit uses a fresh browser context, so a consent from an earlier visit cannot
  carry over; the sites have most likely changed their setup since the crawl.
- **Hits without a denied signal (36 sites)**, most frequent: `ad.doubleclick.net/ccm/s` (12 sites),
  `www3.doubleclick.net` (6), cookie matching `cm.g.doubleclick.net/pixel` (5: novoline.de, stayfriends.de,
  lampenwelt.de, apotheke-adhoc.de, merkur.de), `pagead2.googlesyndication.com/pagead/ping` (4). The consent
  state may also travel in cookies or request bodies, which the crawler does not store; these are cases for
  manual checks.
- Not covered: Google tags routed through the site's own domain (server-side tagging, as on bwin.de) are
  classified as first-party and do not appear in this count.

## Reject visits that look like Accept: manual checks

On 10 of 292 usable Reject visits (sites with a banner) the crawler saw at least half as many tracking companies
after Reject as after Accept (and at least 5 after Accept). Leaving them out hardly changes the Reject results:
any tracking in the window 30% without a choice vs 56% after Reject (299 sites: 32% vs 57%), median after Reject
2 requests either way.

All 10 were checked by hand on 2 November 2026: Chrome profile without extensions, fresh page load, banner
answered with its own reject (on the second layer where the first has none, all optional categories off),
third-party requests recorded for 20 seconds after the click (resource timing through a PerformanceObserver).

| Site | CMP | Reject on the first layer | After the manual reject | Result |
|---|---|---|---|---|
| zelesta.de | Cookiebot | yes ("Deny") | TikTok, Taboola, Microsoft Clarity | confirmed |
| 20min.ch | OneTrust | yes | header-bidding auction: Adform, Smartadserver, Rubicon, OpenX, TripleLift, PubMatic, Criteo, Index Exchange, Teads, Permutive, DoubleClick; Google `G100` | confirmed |
| nzz.ch | consentmanager | no ("Change cookie preferences" / "Accept all") | full-page ad; adnz, Criteo, OpenX, Teads, AppNexus, RTB House, **ID5 and Lotame (identity)** | confirmed |
| apotheke-adhoc.de | Cookiebot | no (only "Akzeptieren"; small "Einstellungen") | The ADEX, Aumago, Bombora, BlueConic (data and targeting platforms), Google Analytics `G100`, Google ads; the same set as before any choice | confirmed |
| vevor.de | own banner | yes | Taboola, Microsoft Clarity, Microsoft UET; on reload with the reject stored also RTB House, DoubleClick | confirmed |
| skechers.de | TrustArc | yes ("Alle verweigern") | Microsoft UET event 97 ms after the click, then the UET conversion script | partly (may be UET's consent signal) |
| novoline.de | Usercentrics | yes ("Deny"; **"Marketing" is pre-ticked**, so "Save Services" would consent) | Microsoft Clarity (session recording) | partly |
| zdfheute.de | own banner | yes | Nielsen audience measurement (AGF) and Piano Analytics; no advertising | analytics only (reach measurement, likely treated as consent-free) |
| sky.de | Sourcepoint | yes ("Nur notwendige Cookies") | Adobe Launch, Akamai mPulse, Salesforce chat, Sourcepoint; no advertising | low tracking either way (7 companies after Accept): the flag comes from the ratio, not from a failed reject |
| joybuy.de | own banner | yes | only the Microsoft conversion script loads | not reproduced after Reject; before any choice Microsoft Ads, Google, Facebook and Pinterest |

So the flag mostly points at real site behaviour, not at crawler errors: 5 sites confirmed, 3 partly (Microsoft
UET, Clarity, reach measurement), 1 artefact of the ratio on a low-tracking site, 1 not reproduced. These visits stay
in the data. Seven of them (zelesta, nzz, apotheke-adhoc, vevor, skechers, novoline, joybuy) also send tracking requests
before any choice; on 20min.ch this could not be seen, because the profile had an earlier consent stored, which was
reset to "reject all" before the check.

traum-ferienwohnungen.de (Google Consent Mode "granted" after Reject in the crawl) is not among the ten. Its Reject
visit was done by autoconsent's heuristic mode (`HEURISTIC-TIER2`, stored as "Unknown (generic banner)") before the
banner was visible; by hand the banner has no first-layer reject, and after saving with all categories off no
request to Google followed. Recorded "granted" signals stay candidates until confirmed (1 of 4 confirmed so far).

## Share of tracking in the page weight after Accept

Source: `mart_site_consent_effect.accept_tracking_share_bytes` (sites with a banner; phases pre + window;
lower-bound visits excluded, so media covers only 83 sites). Secondary metric.

| Group                     | Sites | Median share |
| ------------------------- | ----- | ------------ |
| Media                     | 83    | 54%          |
| Services & entertainment  | 71    | 24%          |
| Shopping                  | 104   | 21%          |
| Finance & health          | 35    | 21%          |
| Gambling                  | 11    | 12%          |
| Public sector & education | 8     | 0%           |

## Identity requests before a choice and after Reject

37 sites with a banner send identity requests (ID syncing, cookie matching, telco identifiers) during page load
before any choice; 19 of 301 sites with a measured Reject send them in the 30 seconds after the click. Earlier
hand-checked cases: the Ippen network before a choice (mannheim24.de), vevor.de and frankenpost.de after Reject
(partners claim "legitimate interest"). Earlier summaries counted ~29 and ~18 sites with a narrower definition
(ID-sync URLs only); a dedicated ID-sync mart is planned.

## Sensitivity: Germany only

Leaving out the six Swiss and Austrian sites hardly changes anything: media 1,075 instead of 1,069 tracking
requests after Accept (99.5 instead of 100 companies), shopping 12 instead of 11.5 companies, all other medians
unchanged.

## Check: no machine of the crawl filtered tracking

The main crawl ran on four machines. A content blocker or filtering network on one of them would show up as a
lower share of visits reaching Google. It does not (usable visits on sites with a banner, lower bounds excluded):

| Machine | Accept visits | Share with Google Analytics / GTM | Share with doubleclick | Median companies after Accept |
| ------- | ------------- | --------------------------------- | ---------------------- | ----------------------------- |
| mac1    | 79            | 76%                               | 80%                    | 8                             |
| mac2    | 70            | 86%                               | 93%                    | 15                            |
| win1    | 100           | 75%                               | 83%                    | 22                            |
| win2    | 63            | 75%                               | 87%                    | 10                            |

The medians differ because each machine crawled a different random quarter of the sites. The crawler runs
installed Chrome with a temporary profile and extensions disabled (Playwright default `--disable-extensions`),
and every visit gets a fresh browser context, so extensions in the user's own Chrome profile cannot affect it.

## Statistics

Source: [notebooks/statistics.ipynb](../notebooks/statistics.ipynb). Sites with a banner, one value per site and
state (median over the site's usable visits). Paired Wilcoxon signed-rank tests (ties kept, `zero_method="pratt"`),
Holm correction over all 42 tests, matched-pairs rank-biserial correlation `r` as effect size; percentile
bootstrap with 10,000 resamples and a fixed seed.

**Group medians with 95% bootstrap intervals** (tracking requests in 30 s; companies after Accept):

| Group | No choice | Reject | Accept | Companies after Accept |
|---|---|---|---|---|
| Media | 0 [0–0] | 4 [1–15] | 1,069 [995–1,139]* | 100 [94–103]* |
| Shopping | 0 [0–1] | 3 [1–4] | 81 [61–95] | 11.5 [8.5–21.5] |
| Services & entertainment | 0 [0–0] | 2 [0–4] | 91 [53–192.5] | 9 [4.5–33.5] |
| Finance & health | 0 [0–0] | 0 [0–0] | 28 [9–54] | 4 [2–8] |
| Public sector & education | 0 [0–0] | 0 [0–0] | 0.5 [0–6] | 0 [0–2] |
| Gambling | 0 [0–7] | 2 [0–8] | 37 [9–47] | 5 [3–9] |
| All sites | 0 [0–0] | 2 [1–3] | 138 [111–211] | 29 [23–37] |

\* Lower bounds included as measured. **Bracket for the true median** (lower-bound sites once as measured, once as
+∞): media, Accept, tracking requests **between 1,069 and 1,347** (95% interval 1,006–1,917); companies **between
100 and 114**. For services & entertainment (11 lower-bound sites), finance & health (2) and all sites together the
two ends coincide: the memory aborts do not change these medians.

**Paired tests.** Accept raises tracking on almost every site:

| All sites | Sites | Higher on | Median difference | r | p (Holm) |
|---|---|---|---|---|---|
| No choice → Accept, requests | 382 | 95% | +135.5 | 1.00 | < 0.001 |
| Reject → Accept, requests | 292 | 90% | +83.5 | 0.99 | < 0.001 |
| No choice → Accept, companies | 382 | 92% | +28 | 1.00 | < 0.001 |
| Reject → Accept, companies | 292 | 87% | +13 | 0.99 | < 0.001 |

By group, both Accept comparisons are significant for media, shopping, services & entertainment, finance & health
and gambling. Public sector & education (8 sites with both values) is not significant in any test: too few sites
with a banner to tell. 34 of 42 tests are significant after Holm correction.

**Reject vs no choice: is there any tracking at all?** (McNemar, exact)

| Group | Sites | Any tracking, no choice | Any tracking, after Reject | Only after Reject | Only without a choice | p (Holm) |
|---|---|---|---|---|---|---|
| Media | 81 | 32% | 68% | 30 | 1 | < 0.001 |
| Shopping | 96 | 50% | 62% | 15 | 3 | 0.03 |
| Services & entertainment | 71 | 21% | 56% | 25 | 0 | < 0.001 |
| Finance & health | 33 | 12% | 30% | 6 | 0 | 0.09 |
| Public sector & education | 8 | 0% | 12% | 1 | 0 | 1 |
| Gambling | 10 | 30% | 50% | 2 | 0 | 1 |
| **All sites** | **299** | **32%** | **57%** | **79** | **4** | **< 0.001** |

A tracking request in the 30-second window is more common after Reject than when the user does nothing. The
medians stay small (2 requests over all sites), and the two windows start differently (no choice: after page load;
Reject: at the click, so scripts reacting to the choice fall into it).

**Consent-update pings and code loads do not explain it** (`check_google_consent_mode.py --mode reject --phase
window`, any tracking request per site, same 299 sites):

| Counted as tracking | No choice | After Reject | Only after Reject | Only without a choice |
|---|---|---|---|---|
| A: every tracking request | 32% | 57% | 79 | 4 |
| B: without Google Consent Mode pings that report everything denied (`gcs=G100`) | 30% | 56% | 82 | 4 |
| C: also without code loads (scripts, stylesheets, fonts; Google configuration and ad-fraud checks) | 29% | 53% | 73 | 3 |

What remains on the 73 sites with tracking only after Reject is mostly **ad delivery**: Google advertising on 19 of
them (ad rendering and measurement: `pagead2.googlesyndication.com/pagead/gen_204`, `tpc.googlesyndication.com`
ad images, SafeFrame), then Virtual Minds and Microsoft (7 each), PubMatic, Nielsen and Outbrain (6 each), Teads and
Criteo (5 each). The reading that fits: without a choice the page holds its ad slots back; after a Reject it starts
loading ads, which the ad-tech companies say are non-personalised or based on "legitimate interest". So a reject
does not mean "no contact with ad tech": on more than half of the sites with a working reject, ad-tech companies
receive requests (with the user's IP address and the page) within 30 seconds of the click.

Hard indicators in the Reject window (Google hits, same check): on 3 sites Consent Mode reports **ad_storage
granted after the user rejected** (traum-ferienwohnungen.de with 18 such hits, wallstreet-online.de,
xn--schnppchenportal-ynb.de), on 2 more analytics granted (boersennews.de, opodo.de); Google cookie matching
(`cm.g.doubleclick.net/pixel`) runs after Reject on 6 sites (20min.ch, tichyseinblick.de, lampenwelt.de,
apotheke-adhoc.de, vevor.de, novoline.de; vevor.de was confirmed by hand earlier).

Manual check, 2 November 2026, traum-ferienwohnungen.de (Chrome profile without extensions, resource timing of
the page): **not reproduced.** Before a choice Google receives only Consent Mode pings with `gcs=G100` (GA4
`first_visit` / `page_view`, `pagead2.googlesyndication.com/ccm/collect`). The banner has no reject on the first
layer ("Alle Cookies zulassen" / "Cookie Einstellungen"); in the settings all optional categories are off by default,
and after "Einstellungen speichern" no request to Google followed in the next 26 seconds. Together with the
pre-choice checks (bwin.de confirmed, baur.de and fr.de not reproduced), "granted" signals recorded by the crawler
are treated as candidates until confirmed by hand: either the sites changed since the crawl, or the crawler's
reject path differed from the manual one (its screenshot after the click shows which).

Coverage: Reject values exist only where a free reject worked. For media that is 81 of 165 sites with a banner (the
others offer no free reject or it could not be verified), so the media Reject median describes the sites that
let you say no.

Germany only: medians unchanged except media Accept (1,075 instead of 1,069 requests, 99.5 instead of 100
companies) and shopping companies (12 instead of 11.5).

## Still open

- Bot-blocked sites: 48 in the first crawl, 38 re-measured from a home connection; 11 sites (~2%) could not be
  measured. 48 − 38 = 10, so one of these counts needs checking; 525 − 507 = 18 sites have no data at all.
