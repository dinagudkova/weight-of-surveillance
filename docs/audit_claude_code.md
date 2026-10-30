# Independent audit — "The Weight of Surveillance"

Scope: crawler logic, classification (crawler vs dbt), dbt models, data checks on the local DuckDB warehouse
(read-only copy), loader/scripts, documentation vs code, repository hygiene. No real sites were crawled, no
connection was made to Postgres/Neon, and `.env` was not read or printed. All data queries ran against
`/tmp/audit.duckdb`, a copy of `data/warehouse/wos.duckdb`; the original file was not modified.

## Summary — 5 most important findings

1. **(Critical)** `fct_visits.tracking_share_bytes` divides window-scoped tracking bytes by **whole-visit**
   bytes (pre+window+after) instead of window bytes. Measured on the real-browser dataset this understates the
   headline "share of tracking in page weight" by roughly 2–9× depending on category, and **reorders** the
   category ranking that Business Question 4 calls "the central comparison of the study" (gambling and
   services/entertainment move from the bottom to the top of the ranking once corrected).
2. **(Major)** Self-hosted (first-party) scripts that happen to match a generic EasyPrivacy/CNAME rule are
   labelled `request_category = 'tracking'` while their `owner` literally reads `"<site>.de (first-party)"`.
   This turns a site's own domain into a fake "tracking company" in `mart_company_reach` and inflates
   `accept_tracking_companies` on 348 visits (306 of 452 sites with any tracking); on 43 visits it is the
   *only* "company" counted, i.e. a site with zero real third-party trackers is reported as having at least one.
3. **(Minor, currently 0 impact)** `prep_requests_classified.is_telemetry_host` is gated by `not is_first_party`,
   but CNAME-cloaked trackers are first-party by domain by construction — so a CNAME-cloaked *telemetry*
   tracker would be mis-filed as `tracking` in dbt while `crawler/classify.mjs` correctly files it as
   `telemetry`. No current row is affected (all 273 `via_cname` rows in the warehouse are Adobe/Permutive/
   Webtrekk analytics, not telemetry), but the logic is a latent, unverified-by-the-crawler-agreement-test bug.
4. **(Minor)** `mart_company_reach` filters strictly on `phase = 'window'`, so it does not apply the
   "count all phases as a lower bound" rule that `fct_visits`/`mart_site_consent_effect` apply to the 71
   memory-aborted accept visits — 7,612 tracking requests on those visits are counted at the site level but
   silently dropped at the company level.
5. **(Minor)** `mart_cmp_market`'s long tail is mostly noise: 29 of its 43 distinct `cmp` values (each 1 site)
   are autoconsent-internal rule IDs (`auto_DE_<domain>_<hash>`) or the site's own domain name, not real CMP
   products. `normalize_cmp()` does not catch them, so Business Question 6's "which consent platforms dominate"
   table looks far noisier/more fragmented than it is (the actual top-5 ranking — Sourcepoint, consentmanager,
   Usercentrics, OneTrust, opencmp — is correct).

## Checked and found correct

- Consent click/verify flow in `crawler/crawl.mjs` (autoconsent + text-fallback, `sawBanner`/`consentVerified`
  derivation, pay-or-okay handling) — sound, matches the documented timeline.
- Observation window and phase assignment (`pre`/`window`/`after` by request start vs. `t0`/`tEnd`) — correct,
  matches README and `fct_visits.sql`'s own comment.
- Memory guard, `--shard`, and resume/`--retry-failed` logic — correct, by design.
- Real-browser launch options (`channel: 'chrome'`, `ignoreDefaultArgs: ['--enable-automation']`,
  `--disable-blink-features=AutomationControlled`) match the README's claim; verified empirically:
  `navigator.webdriver` is `False` for 1,599 of 1,627 real-browser visits (the remainder are nav-error/crash rows
  with no reading taken).
- `SYNC_RE` (`crawler/classify.mjs`) and `SYNC_PATTERN` (`load/load_raw.py`) — byte-identical regex.
- `assert_classification_agrees_with_crawler`: real disagreement rate is **0.68%**, well under the 2% warn
  threshold; disagreement among `via_cname` rows specifically is **0%** (this is what let me rule out finding 3
  as a currently-live bug rather than a latent one).
- The ~83k-row gap between `stg_requests` (542,060, real dataset) and `prep_requests_classified` (458,775) is
  **exactly** explained by requests belonging to superseded (non-latest) re-crawled visits — confirmed by
  reproducing `prep_visits`' `row_number()` dedup manually. Not a join bug.
- Cross-mart site counts agree: `mart_category_summary`, `mart_group_summary` and `mart_site_consent_effect`
  all report 469 sites.
- No impossible values in `fct_visits`: no negative bytes/requests, no `tracking_share_bytes` outside [0, 1].
- `mart_company_reach`'s top reach ranking (Google LLC, Microsoft, Criteo, PubMatic, Adobe, Smartadserver,
  Improve Digital, Adform, Yahoo, OpenX, IPONWEB, TripleLift, The Trade Desk, Ströer, Semasio) is sane once the
  first-party artifact (finding 2) is excluded.
- `assert_sites_in_sample` returns 0 rows.
- `python3 -m pyflakes scripts load sample` — clean, no warnings.
- `node crawler/crawl.mjs --mock --window 10` completes with `Done.` across all 9 synthetic fixtures, including
  the memory-abort/flood and bot-block cases.
- `python3 scripts/dbt.py build` against the warehouse copy: 51/51 PASS, 0 errors, 0 warnings.
- No secrets committed; `.env`, `*.duckdb`, `data/` are correctly gitignored. The `NEON_URL=postgresql://user:…`
  line in README.md is a placeholder template, not a real credential.
- `mart_dataset_comparison` is correctly disabled (`config(enabled=false)`) per the stated decision — the model
  itself does not rebuild (see finding 6 for the leftover table this leaves behind).

---

## Findings

### 1. [Critical] `tracking_share_bytes` divides by whole-visit bytes, not window bytes

**File:** `dbt/models/marts/fct_visits.sql:86-87` (definition), consumed by
`dbt/models/marts/mart_category_summary.sql:12`, `mart_group_summary.sql:15` as
`median_accept_tracking_share_bytes`.

```sql
case when v.is_lower_bound then null  -- share is undefined for an aborted window
     when coalesce(r.visit_bytes, 0) > 0 then 1.0 * r.tracking_bytes / r.visit_bytes end as tracking_share_bytes
```

`r.tracking_bytes` (and `r.window_bytes`) are scoped to `phase = 'window'` (see `req` CTE, lines 7-11), but
`r.visit_bytes` is `coalesce(sum(bytes), 0)` **across all phases** (line 9) — pre + window + after, with no
upper bound on how long "after" runs before `context.close()`. This directly contradicts the project's own
stated principle, repeated in `crawler/crawl.mjs:8`, this same file's header comment, and the README: "main
metrics only use requests that start inside this window, so all modes are observed equally long." Padding the
denominator with a variable-length "after" phase breaks exactly the equal-length comparison the window was
designed to guarantee.

**Evidence** (query against the warehouse copy, real dataset, accept mode, usable, not lower-bound, n=307):

| metric | value |
|---|---|
| avg `window_bytes` | 3.34 MB |
| avg `visit_bytes` | 7.12 MB |
| avg reported `tracking_share_bytes` (current code) | **0.228** |
| avg corrected share (`tracking_bytes / window_bytes`) | **0.536** |
| median extra bytes as % of `visit_bytes` | 66% |

Per category (median), reported vs. corrected, sorted by corrected value:

| category_group | n | reported median | corrected median |
|---|---|---|---|
| gambling | 10 | 0.094 | **0.836** |
| media | 102 | 0.339 | 0.806 |
| services_entertainment | 75 | 0.139 | **0.786** |
| finance_health | 37 | 0.089 | 0.493 |
| shopping | 90 | 0.131 | 0.384 |
| public_education | 25 | 0.000 | 0.000 |

With the current code, the apparent ranking is media > services_entertainment ≈ shopping > finance_health ≈
gambling. Corrected, it is gambling > media > services_entertainment > finance_health > shopping — gambling and
services_entertainment move from bottom to top. Since Business Question 4 is explicitly framed as "the central
comparison of the study," this is a published-conclusion-level bug, not a cosmetic one.

**Suggested fix:** change the denominator to `r.window_bytes` (falling back to `visit_bytes` only if
`window_bytes` is 0, or treating that case as null/undefined like the lower-bound case already does). Re-check
whether `all_tracking_bytes`/`all_tracking_requests` (used for `is_lower_bound` visits) need an analogous
"all-phases visit weight" denominator for consistency, or whether lower-bound visits should keep `share = null`
as they do today.

---

### 2. [Major] First-party hosts matched by EasyPrivacy/CNAME rules are labelled as "tracking" with a self-referential owner

**Files:** `crawler/classify.mjs:102-138` and `dbt/models/prep/prep_requests_classified.sql:46-120`.

In both the crawler and dbt, the EasyPrivacy match (`via_easyprivacy`) is **not** gated on third-party status
(unlike the EasyList match, which is: `via_easylist_third_party = via_easylist and not is_first_party`,
`prep_requests_classified.sql:56`; crawler equivalent `classify.mjs:116`). This is intentional and documented
("EasyPrivacy (any party)" in README's classification table), but its interaction with the `owner` fallback is
not: when a first-party host (or a CNAME-cloaked, first-party-looking subdomain that is itself classified
first-party by domain equality) is nonetheless flagged `tracking` via EasyPrivacy, the `owner` column falls
through to the first-party branch:

```sql
-- prep_requests_classified.sql:115-120
case
    when via_cname and cname_tracker_owner is not null then cname_tracker_owner
    when is_third_party and tracker_domain is not null then tracker_owner
    when is_third_party then coalesce(host_entity, reg_domain)
    else site_domain || ' (first-party)'
end as owner
```
```js
// classify.mjs:138
owner: t?.owner || (thirdParty ? lookup(tds.domains, host) || regDomain : `${getDomain(siteUrl)} (first-party)`),
```

So a request can simultaneously be `request_category = 'tracking'` and `owner = '<site>.de (first-party)'` —
self-contradictory, and directly consumed by `mart_company_reach` (which groups by `owner`, no first-party
filter) as if the site itself were a tracking company reaching one site.

**Evidence:**
```sql
select owner, request_category, tracking_type, count(*) n
from prep.prep_requests_classified
where owner like '%(first-party)%' and request_category='tracking'
group by 1,2,3 order by n desc limit 5;
--                   owner | request_category | tracking_type | n
-- baur.de (first-party)   | tracking          | analytics      | 340
-- airbnb.de (first-party) | tracking          | analytics      | 261
-- zelesta.de (first-party)| tracking          | analytics      | 206
-- hobbii.de (first-party) | tracking          | analytics      | 193
-- web.de (first-party)    | tracking          | analytics      | 156
-- ... also telekom.de, amazon.de, google.de, otto.de, audible.de, and 296 more sites
```
306 of 452 sites with any tracking (68%) have at least one such row; 6,798 of 339,545 tracking requests (real
dataset) carry a `(first-party)` owner. Effect on company counts:
```sql
-- per-visit distinct tracking owners, with vs. without the artifact (real dataset, window phase):
-- visits where the count changes:               348
-- visits where the artifact is the ONLY company counted (i.e. would otherwise show 0): 43
```
On 43 visits a site with **zero** real third-party trackers is reported as reaching at least one "company" —
directly relevant to Business Question 2 ("how many companies receive data... after accepting").

**Suggested fix:** when `is_first_party` (or `not is_third_party`), either exclude the row from
`is_tracking`/`request_category='tracking'` entirely (treat first-party-domain EasyPrivacy matches as
`first-party`, not `tracking`), or at minimum exclude `owner like '%(first-party)%'` rows from
`mart_company_reach` and from the `count(distinct owner)` in `fct_visits`. Decide and document which: either
EasyPrivacy stops applying to first-party-by-domain hosts, or first-party-owned "tracking" rows are kept as
`tracking` (e.g. for byte/request totals) but never counted as a distinct company.

---

### 3. [Minor, 0 current impact] `is_telemetry_host` gated by `not is_first_party` breaks for CNAME-cloaked telemetry trackers

**File:** `dbt/models/prep/prep_requests_classified.sql:67`:
```sql
(not is_first_party and tracker_telemetry) as is_telemetry_host
```
vs. `crawler/classify.mjs:122`:
```js
const isTelemetry = cats.includes('Telemetry');
```
The crawler's `isTelemetry` has no first-party gate. `is_third_party`/`is_first_party` is computed by domain
equality (`reg_domain = site_domain`, `prep_requests_classified.sql:33`), and CNAME cloaking by construction
only happens on hosts whose `reg_domain` already equals the site's domain (that's what makes it "cloaking" —
see `crawler/classify.mjs:69-74`, `cnameLookup` requires `getDomain(host) === siteDomain`). So any CNAME-cloaked
tracker is first-party by this domain test, and `not is_first_party` will be `false` for it — meaning a
CNAME-cloaked **telemetry**-category tracker (e.g. a New Relic/Sentry/Akamai mPulse deployment cloaked behind
a first-party subdomain, all of which exist in `dbt/seeds/trackers.csv`/`lists/ddg-tds.json` with
`tracker_telemetry = true`) would be classified `request_category = 'tracking'` in dbt while
`crawler/classify.mjs` correctly calls it `telemetry`.

**Evidence that this is currently dormant, not live:** all 273 `via_cname` rows in the warehouse resolve to
Adobe Analytics / Permutive / Webtrekk, none of which carry the DDG `Telemetry` category, so
`is_tracking = matches_tracking_rule and not is_telemetry_host` happens to agree with the crawler for every
current row (confirmed: 0% disagreement among `via_cname` rows, vs. 0.68% overall). But telemetry tools *are*
commonly cloaked in practice (`c.go-mpulse.net`, `*.sentry.io`, `*.kameleoon.*`, `*.newrelic.com` all appear as
plain third-party hosts with `tracker_telemetry = true` in the current `prep_host_lookup`), so this will
misfire the moment one of them is seen cloaked.

**Suggested fix:** drop the `not is_first_party` gate from `is_telemetry_host` (telemetry should be derived from
`tracker_telemetry` alone, exactly like `tracker_identity`/`tracker_ad_owner`/`tracker_action_pixel` already
are, with no such gate) — or, if the gate is deliberate, apply the same gate consistently to the other
tracking-type flags and document why telemetry is special.

---

### 4. [Minor] `mart_company_reach` ignores the lower-bound "count all phases" rule, inconsistent with `fct_visits`

**Files:** `dbt/models/marts/mart_company_reach.sql:10` vs. `dbt/models/marts/fct_visits.sql:70-71,74,82`.

`fct_visits` deliberately counts **all phases** (not just `window`) for memory-aborted accept visits
(`is_lower_bound`), on the stated rationale that the flood starts mid-window and truncates it:
```sql
case when v.is_lower_bound then coalesce(r.all_tracking_requests, 0) else coalesce(r.tracking_requests, 0) end as tracking_requests
```
`mart_company_reach` does not apply this exception; it filters strictly:
```sql
where is_usable and phase = 'window' and is_tracking and dataset = '{{ var("main_dataset") }}'
```
**Evidence:**
```sql
-- 71 memory-aborted accept visits (real dataset):
--   tracking requests outside the 'window' phase on those visits: 7,612
--   tracking requests inside the 'window' phase on those visits:  80,460
```
So a company that only shows up in the `pre`/`after` phase of one of these 71 visits is counted toward that
site's `tracking_companies`/`tracking_requests` in `mart_site_consent_effect` (via `fct_visits`), but is
invisible in `mart_company_reach`'s per-company reach and byte totals — a reader cross-referencing the two
marts for one of these 71 sites will see numbers that don't reconcile.

**Suggested fix:** either give `mart_company_reach` the same lower-bound exception (drop the `phase = 'window'`
filter for `is_lower_bound` visits), or explicitly document that `mart_company_reach` is window-only and
therefore undercounts lower-bound visits by design.

---

### 5. [Minor] `mart_cmp_market`'s long tail is mostly autoconsent rule IDs / raw domains, not CMP names

**Files:** `dbt/macros/normalize_cmp.sql`, `dbt/models/marts/mart_cmp_market.sql`.

`normalize_cmp()` maps known substrings (sourcepoint, onetrust, usercentrics, consentmanager, didomi, cookiebot,
tealium, trustarc, quantcast, `heuristic%`) to clean platform names, `else {{ col }}` otherwise. The crawler's
`cmp` field, however, can also hold autoconsent's internal rule identifiers for sites with no known CMP
(pattern `auto_<market>_<domain>_<hash>`) or, apparently, the bare site domain for some custom/in-house banners.

**Evidence** (full `mart_cmp_market` output, real dataset): of 43 distinct `cmp` values, 29 have exactly 1 site
each and are clearly not CMP products, e.g. `auto_DE_ernstings-family.de_xqf`, `auto_DE_fcbinside.de_0d6`,
`auto_CH_sparkasse.de_lwr`, and bare domains `web.de`, `vodafone.de`, `strato.de`, `bahn-de`, `amazon.com`,
`google.com`, `check24`, `coolblue`. The top of the table (Sourcepoint 103, consentmanager 71, Usercentrics 61,
"Unknown (generic banner)" 41, OneTrust 36, opencmp (Ippen) 24, "not detected" 14, Cookiebot 11, Didomi 11) is
unaffected and correct, but a reader scrolling the full table — the dashboard artifact for Business Question 6
— would see ~29 spurious "platforms" suggesting a far more fragmented market than actually exists.

**Suggested fix:** extend `normalize_cmp()` (or a pre-step) to fold the `auto_<market>_<domain>_<hash>` pattern
and any value that is itself a domain name into `'Unknown (generic banner)'`, consistent with how the
`heuristic%` case is already handled.

---

### 6. [Note] Disabled `mart_dataset_comparison` still has a stale materialized table

**File:** `dbt/models/marts/mart_dataset_comparison.sql:1` (`{{ config(enabled=false) }}`).

dbt's `enabled=false` only skips rebuilding a model; it does not drop a table that was already built by an
earlier run (before the comparison was disabled). Evidence: `select count(*) from marts.mart_dataset_comparison`
on the current warehouse returns **1,128 rows**, even though the model is disabled and `dbt build` (51/51 PASS)
did not touch it. Anyone connecting to the DuckDB file or the Neon database directly (bypassing dbt, e.g. the
Tableau dashboard if it is pointed at the schema rather than a dbt-managed export) could still find and chart
this table, which the model's own comment says is "not comparable" because three of four automated-crawl
machines ran behind a DNS ad blocker.

**Suggested fix:** `DROP TABLE IF EXISTS marts.mart_dataset_comparison;` once, and/or note in
`dbt/README.md` that disabled models can leave stale tables behind and should be dropped manually after
disabling.

---

### 7. [Note] `dbt/README.md`'s layer table is out of date

**File:** `dbt/README.md:13` (marts row), `:11` (staging row).

```
| staging | `stg_visits`, `stg_requests` | view |
| marts | `fct_visits`, `mart_site_consent_effect`, `mart_category_summary`, `mart_company_reach`, `mart_cmp_market`, `mart_pre_consent` | table |
```
Actual models present: staging also has `stg_tcf_visits` (`dbt/models/staging/stg_tcf_visits.sql`); marts also
has `mart_group_summary`, `mart_promise_vs_reality`, and the disabled `mart_dataset_comparison`
(`dbt/models/marts/*.sql`). The "Tests" list at the bottom is otherwise accurate and matches
`dbt/tests/*.sql` exactly.

**Suggested fix:** update both rows to list the current models (and note that `mart_dataset_comparison` is
present but disabled).

---

### 8. [Note] `load_raw.py --target` defaults to `both`, so a plain run attempts a Neon connection

**File:** `load/load_raw.py:240` — `p.add_argument("--target", choices=["duckdb", "postgres", "both"], default="both")`.

Every example in README.md and this file's own docstring happens to omit `--target`
(`python load/load_raw.py data/raw/study_merged`), relying on the default. That default is `both`, so a bare
invocation — e.g. someone reloading just the local DuckDB file for a quick check — will also try to read
`NEON_URL` from `.env`/the environment and open a Postgres connection, `sys.exit`-ing if it's absent
(`load_raw.py:197-198`) or, if present, writing to the shared Neon database. This audit avoided running
`load_raw.py` entirely for this reason, per the task's instructions; flagging it here as a footgun for future
local-only runs.

**Suggested fix:** default `--target` to `duckdb` (the safe, local, idempotent choice), and require
`--target postgres`/`both` to be explicit — or at least call this out prominently in the README next to the
example command.

---

### 9. [Note] `sample/sites_real_check.csv` looks like a dead scratch file

**File:** `sample/sites_real_check.csv` (296 bytes).

No script in `scripts/`, `sample/`, or `crawler/` reads or writes this file, and it is not mentioned in
`README.md`, `sample/README.md`, or `dbt/README.md` (unlike `sites_memory.csv`/`sites_rerun_consent.csv`,
which `scripts/make_rerun_lists.py` generates, or `sites_real_browser.csv`, which
`scripts/make_real_browser_list.py` generates). It appears to be a small manual/ad-hoc list from one
interactive check during the real-browser rollout.

**Suggested fix:** if it's no longer needed, delete it (or move it to `sample/archive/` alongside the other
one-off lists already parked there).
