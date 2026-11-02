# Methodology

How the data for "The Weight of Surveillance" was collected, cleaned and analysed, and what it can and cannot
show. Numbers are in [results_numbers.md](results_numbers.md); commands and file layout are in the
[README](../README.md).

## 1. Question and scope

How much does a user's consent decision change what a website loads, and who benefits from it? Every site is
visited in three states: **no choice** (the banner is left alone), **Accept all** and **Reject all**. The study
measures what the browser sends to third parties in each state. It does not measure what happens to the data on
the servers, logged-in use, inner pages, or whether a practice is lawful.

## 2. Sample

- **Source:** the Chrome UX Report (CrUX) top list for Germany, September 2026: the top 1,000 origins, merged per
  domain, reviewed by hand (categories, exclusions of login-only, adult and IP-address entries), plus a boost from
  the top 5,000 for public sector, health and finance, which are rare in the top 1,000. Build steps:
  [sample/README.md](../sample/README.md).
- **Size:** 525 sites. Categories are combined into six groups: media; shopping; services & entertainment;
  finance & health; public sector & education; gambling.
- **Country:** CrUX ranks sites popular with users in Germany, so the sample contains four Swiss and two Austrian
  sites. They are kept and flagged with `site_country` (by top-level domain); leaving them out changes no result
  (see results, "Sensitivity").
- **Without data:** 18 sites (3.4%). 16 blocked the crawler in every visit: de258.die-staemme.de, ancestry.de,
  boerse.de, christ.de, decathlon.de, douglas.de, fussballdaten.de, kaufland.de, manualslib.de, onvista.de,
  pcgameshardware.de, reisereporter.de, rezeptwelt.de, saechsische.de, tripadvisor.de, zeit.de. Two more
  (schule-infoportal.de, carwow.de) never gave a usable visit. 507 sites remain.

## 3. Crawl protocol

**Browser.** Installed Google Chrome, started by Playwright in a visible window without the automation flag
(`--real-browser`), desktop viewport 1366×900, locale `de-DE`. Every visit gets a new, empty browser context: no
cookies, no stored consent. Extensions are disabled (Playwright's default `--disable-extensions`), so content
blockers in anyone's personal Chrome cannot affect the crawl.

**Network.** Home connections in Germany or a German VPN exit, both without ad or tracker filtering. An earlier
crawl ran partly through a VPN with a DNS-level blocker (Proton VPN NetShield); it saw only a fraction of the
tracking and is not used. Sites that blocked the VPN's IP addresses were re-measured from a home connection. Four
machines (mac1, mac2, win1, win2) each crawled a random quarter of the sites; before the crawl every machine was
checked on the same reference sites.

**One visit, step by step** ([crawler/crawl.mjs](../crawler/crawl.mjs)):

1. Load the home page and wait 4 seconds.
2. **Pre snapshot:** is a consent banner visible, is the page a bot-protection page, does the banner offer a paid
   subscription ("pay or okay"), which cookies are already set. Screenshot.
3. **Consent action** (Accept and Reject only): [DuckDuckGo autoconsent](https://github.com/duckduckgo/autoconsent)
   with its rules for known consent platforms and its heuristic mode for unknown banners. If that does nothing or
   the banner is still visible, a fallback clicks a button whose label matches a fixed list of accept or reject
   wordings (also inside shadow DOM and consent iframes). Then the crawler **verifies** that the banner is gone.
   Screenshot.
4. **Observation window** of 30 seconds, starting at the consent click (no choice: right after the pre snapshot).
   All three states are observed equally long.
5. **End snapshot:** cookies, script time, screenshot.

Every request is stored with its start time and phase: `pre` (before the window), `window`, `after`. Order of
sites and states is random, with pauses between visits and two parallel browsers per machine. One visit per site
and state; in the pilot the repeat variance of the tracking count was about 8%.

## 4. Which visits count

Definitions in [dbt/models/prep/prep_visits.sql](../dbt/models/prep/prep_visits.sql):

- **Measured** (`is_measured`): the page loaded and was not a bot-protection page.
- **Usable** (`is_usable`): measured, and for Accept or Reject the banner was verifiably closed by the click.
  Visits where the click could not be verified are excluded, so the Accept and Reject results never contain a
  visit where the choice may not have happened.
- **Lower bound** (`is_lower_bound`): after Accept some pages fire so many requests that the browser runs out of
  memory and the visit is stopped. These visits count, with the requests seen until the stop, so their numbers
  are too low. 73 of the 385 usable Accept visits on banner sites are lower bounds (60 media, 11 services &
  entertainment, 2 finance & health).
- **Banner sites.** Accept and Reject results use only the 449 sites where a banner was seen; on a site without a
  banner an "Accept" visit is just a page load.

Coverage on the 449 banner sites: no choice 446, Accept 385 (86%), Reject 301 (67%). Reject has the lowest
coverage because a free reject does not always exist or work: on 82 banners with a paid option the crawler found
no free way to reject, and on 66 sites without a paid option the reject could not be verified. The Reject results
therefore describe the sites that let you say no (media: 81 of 165).

## 5. Classifying requests

Applied in the crawler and again in dbt
([dbt/models/prep/prep_requests_classified.sql](../dbt/models/prep/prep_requests_classified.sql)):

| Category | Meaning | Source |
|---|---|---|
| tracking | advertising, analytics, identity (ID syncing, cookie matching, telco identifiers) | DuckDuckGo Tracker Data Set with its categories, EasyPrivacy, EasyList (third party only), [lists/custom_trackers.csv](../lists/custom_trackers.csv) for German ad-tech, CNAME cloaking via DNS |
| telemetry | error and performance monitoring, A/B testing; not counted as tracking | custom list |
| consent | the consent banner itself | [lists/cmp_domains.txt](../lists/cmp_domains.txt) |
| first-party | the site and domains of the same owner | DuckDuckGo entities, [lists/site_aliases.csv](../lists/site_aliases.csv) |
| other | CDNs, fonts, video, payment, everything else | |

A **company** is the owner of a tracking domain in the DuckDuckGo entity list (Google LLC covers DoubleClick,
Google Analytics, Google Ads). Self-hosted tracking (`<site> (first-party)`) counts as tracking requests and bytes
but not as a company. A test checks that dbt and the crawler agree on every request's category.

## 6. Metrics

- **Tracking requests and companies** in the 30-second window, per visit; per site the median over its usable
  visits; per group the median over sites.
- **Page load before any choice:** tracking, advertising and identity requests and tracker cookies in phase `pre`
  of the no-choice visit (`mart_pre_consent`). The no-choice window starts after this phase, so the "no choice"
  medians do not include it.
- **First seconds:** time from the Accept click to the first tracking request and companies reached by the end of
  each second (`mart_first_tracker`, `mart_consent_timeline`; lower-bound visits excluded).
- **Share of tracking in page weight** after Accept (`pre` + `window` bytes; secondary metric).
- **Consent platform** per site (`mart_cmp_market`), **paid option** in the banner (`site_pay_or_okay`: a paid,
  tracking-free subscription is offered; it does not by itself mean there is no free reject) and the **reject
  option** (paid option × reject verified; it does not record where on the banner the reject was).
- **Promise vs reality:** after a verified Accept the crawler reads the page's IAB TCF API (`getTCData`) and
  Google's Additional Consent string in a separate crawl; the number of vendors consented to is compared with the
  tracking companies seen (`mart_promise_vs_reality`). Vendors are not companies, so the comparison is approximate.
- **Company reach:** share of banner sites on which a company receives tracking requests after Accept or Reject
  (`mart_company_sites`).

## 7. Statistics

[notebooks/statistics.ipynb](../notebooks/statistics.ipynb):

- **Paired tests.** Every site is measured in all three states, so states are compared site by site with the
  Wilcoxon signed-rank test (ties kept, `zero_method="pratt"`), effect size as matched-pairs rank-biserial
  correlation, Holm correction over all 42 tests.
- **Bootstrap.** Percentile intervals for group medians, 10,000 resamples, fixed seed.
- **Lower bounds.** The true median after Accept is bracketed: lower-bound sites once as measured (lower end) and
  once as +∞ (upper end).
- **Any tracking, Reject vs no choice:** exact McNemar test on the share of sites with at least one tracking
  request in the window.
- **Sensitivity:** Germany only; the 10 Reject visits that look like Accept left out.

## 8. Consent signals in Google requests

[scripts/check_google_consent_mode.py](../scripts/check_google_consent_mode.py) reads the consent state that
Google requests carry in their URL: `gcs=G1xy` (Consent Mode; x = ad storage, y = analytics storage), `gdpr_consent=`
(IAB TCF string), `npa=1` (non-personalised ads). Requests are split into code (scripts, configuration, ad-fraud
checks) and hits (collection, conversion, cookie matching, remarketing, ad requests). Used for two checks: Google
hits during page load before any choice, and whether the difference "any tracking after Reject vs no choice"
survives once Consent Mode "denied" pings and code loads are removed (it does: 53% vs 29% of sites). URLs are
stored cut at 500 characters, so some signals are unknown.

## 9. Manual checks

Done in a Chrome profile without extensions, banner answered by hand with the site's own button, requests read
from the page (resource timing). Dates and results are in [results_numbers.md](results_numbers.md).

| What | Sites | Result |
|---|---|---|
| Paid option and free reject | markt.de, kleinanzeigen.de | markt.de: only "Accept all" or subscription; kleinanzeigen.de: free reject in the settings |
| Consent Mode "granted" before any choice | bwin.de, baur.de, fr.de | bwin.de confirmed; baur.de, fr.de not reproduced |
| Consent Mode "granted" after Reject | traum-ferienwohnungen.de | not reproduced; the crawl's reject used autoconsent's heuristic mode before the banner was visible |
| Reject visits that look like Accept | 10 sites | 5 confirmed, 3 partly, 1 artefact of the ratio, 1 not reproduced |
| ID syncing (earlier) | mannheim24.de (before a choice), vevor.de, frankenpost.de (after Reject) | confirmed |

Signals the crawler recorded but that were not reproduced by hand are reported as candidates, not as findings.

## 10. Pipeline and reproducibility

Raw JSONL → `load/load_raw.py` → DuckDB (local) and PostgreSQL (Neon) → dbt (staging → prep → marts, 64 tests,
identical results on both engines) → Tableau (Neon, schema `marts`). `scripts/results_numbers.py` prints every
headline number from the marts. Raw data and screenshots are not in the repository.

## 11. What is visible from the browser (business question 9)

- **Blocked:** 16 of 525 sites (3%) blocked the crawler in every visit, mostly large shops and publishers (list in
  section 2); ten well-known blocked sites were measured by hand separately and are never pooled with the crawl.
- **Server side:** server-to-server ad auctions and data sharing are invisible from the browser, so the observed
  companies are a lower bound of who receives data.
- **Routed through the site's own domain:** some sites send analytics and tracking to collectors on their own
  domain (by hand: www.bwin.de/dlr/g/collect with Google Consent Mode parameters, te.baur.de/collect). Such requests
  are classified as first-party unless a list knows the collector, so they are counted as tracking only partly.

Bytes and script time per state (business question 1) are collected (`*_tracking_bytes`, `*_script_ms` in
`mart_site_consent_effect`) but only the share of tracking in page weight is reported.

## 12. Limitations

See the README section "Limitations". The most important for reading the results: Accept counts on the heaviest
media sites are lower bounds; Reject results cover only sites where a free reject worked; requests before a choice
or after a reject are indicators, not proof of a violation (partners may claim "legitimate interest", and some
measurement is treated as consent-free); one visit per site and state.
