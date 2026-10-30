# Follow-up audit — "The Weight of Surveillance"

Scope: verify the fixes made since `docs/audit_claude_code.md` against commits `3c95558` and `764e95a`, check
for regressions, and look for anything new. All data checks ran against `/tmp/audit2.duckdb`, a copy of
`data/warehouse/wos.duckdb` built with `DBT_DUCKDB_PATH=/tmp/audit2.duckdb python3 scripts/dbt.py build`
(51/51 PASS, 0 errors, 0 warnings). No real site was crawled, no connection was made to Postgres/Neon, `.env`
was not read, and no file other than this report was changed. Both temporary artifacts (`/tmp/audit2.duckdb`,
`data/raw/audit2_mock`) were deleted after use.

## Verdict

All five items from the first audit's "5 most important findings" are now fixed and verified against real
data, including the critical one: `tracking_share_bytes` numerator and denominator are now provably scoped to
the same phases (0 mismatches across 2,993 visits), null for every lower-bound visit, and in range. The
first-party-owner artifact is gone from `mart_company_reach` and from `fct_visits`'s company counts, confirmed
exactly on both a lower-bound and a normal sample site. The CMP-name cleanup removed the genuinely bogus
long-tail values without touching real (if niche) CMP products. No regressions turned up in the mart
cross-checks, the impossible-value sweep, the crawler/dbt classification-agreement rate, `pyflakes`, or the
mock crawl. One deliberate design choice (pre+window as the page-weight span) leaves a small, bounded,
documented residual timing variance that is worth knowing about but not worth blocking on. **The pipeline is
ready for the dashboard and write-up** — I found no outstanding critical or major issues; the two new items
below are both informational (note severity).

## Original findings — status

| # | Finding | Status | Evidence |
|---|---|---|---|
| 1 | `tracking_share_bytes` divided window bytes by whole-visit bytes | **Fixed** (deliberately, not as suggested: pre+window / pre+window) | `observed_bytes` recomputed from `phase in ('pre','window')` matches the stored column exactly for all 2,993 visits (0 mismatches); all 107 `is_lower_bound` visits have `tracking_share_bytes is null`; 0 of 2,869 non-null values are outside [0,1]; manual recomputation of the average matches the stored average bit-for-bit (0.274897 = 0.274897). See note A below on a small residual timing-comparability wrinkle in this choice. |
| 2 | First-party host flagged `tracking` with `owner = '<site> (first-party)'`, inflating company counts | **Fixed** | `select * from marts.mart_company_reach where owner like '%(first-party)%'` → 0 rows. The 10 visits I sampled that were previously "artifact-only" (0 real companies, 1 fake one) now show `tracking_companies = 0`. Bytes/requests are still counted in tracking totals as intended (3,455 window-phase requests / 45.8 MB still tagged `is_tracking` with a first-party owner). |
| 3 | `is_telemetry_host` wrongly gated by `not is_first_party`, would misfile a CNAME-cloaked telemetry tracker | **Fixed** (structurally; still 0 live impact) | `prep_requests_classified.sql:67` is now `coalesce(tracker_telemetry, false) as is_telemetry_host` — no first-party gate, matching `classify.mjs`. Currently 0 rows have `is_first_party and is_telemetry` together (same as before: no telemetry-category tracker happens to be CNAME-cloaked in this dataset), and the overall crawler/dbt disagreement rate is unchanged at 0.68%, as expected since this fix had nothing live to change. The latent-bug risk this closed is real for future crawls. |
| 4 | `mart_company_reach` ignored the lower-bound "count all phases" rule, diverging from `fct_visits` | **Fixed** | `is_lower_bound` is now passed through `prep_requests_classified` and the mart filter is `phase = 'window' or is_lower_bound`. Aggregate check: mart total requests (195,392) exactly equals an independent recomputation with the same rule. Per-site spot checks: `fcbinside.de` (a lower-bound site) shows 117 distinct tracking owners both via a direct query and via `mart_company_reach`; `thalia.de` (a normal site) shows 10/10 matching owners. |
| 5 | `mart_cmp_market` long tail full of autoconsent rule IDs / raw domains | **Fixed** for the genuinely bogus values | Distinct `cmp` values dropped from 43 to 29. The new "In-house banner" bucket absorbs 15 sites (`auto_DE_<domain>_<hash>` rule IDs, bare domains like `web.de`/`amazon.com`, and the explicit list `check24`/`coolblue`/`bahn-de`/`stepstone-ccm`/`arbeitsagentur`). `Usercentrics` grew 61→64 via the new `consent_domain` fallback (`usercentrics.eu`), additively — the sum of `sites` across `mart_cmp_market` (413) plus the 56 no-banner sites still reconciles to 469 total sites. See note B: my original framing overstated this finding — see below. |
| 6 | Disabled `mart_dataset_comparison` left a stale 1,128-row table in the warehouse | **Fixed** | `select count(*) from information_schema.tables where table_schema='marts' and table_name='mart_dataset_comparison'` on the live `data/warehouse/wos.duckdb` → `0`. `dbt/README.md` now documents that disabled models leave stale tables and how to drop them. |
| 7 | `dbt/README.md`'s layer table was stale (missing models) | **Fixed** | The marts row now lists `mart_group_summary` and `mart_promise_vs_reality` and notes `mart_dataset_comparison` is disabled; the staging row now lists `stg_tcf_visits`. Matches the 8 built marts + 2 table-materialized prep models dbt actually built (10 table models total, per the build log) plus the one disabled mart. |
| 8 | `load_raw.py --target` defaults to `both`, risking an accidental Neon write | **Intentionally not changed** | Confirmed: default is still `both` (`load/load_raw.py:240`); the dashboard reads from Neon so this is by design. README now notes `--target duckdb` for local-only loads. Not re-flagged. |
| 9 | `sample/sites_real_check.csv` looked like a dead scratch file | **Fixed** | File is now at `sample/archive/sites_real_check.csv`; README's real-browser section now references it explicitly ("Before a crawl, every machine is checked on the same reference sites"). |

## Regression checks

- **Mart cross-consistency:** `mart_category_summary` sums to 469 sites, `mart_group_summary` sums to 469
  sites, `mart_site_consent_effect` has 469 rows — unchanged and consistent. `mart_cmp_market`'s 413
  banner-having sites + `mart_site_consent_effect`'s 56 no-banner sites = 469. ✓
- **`fct_visits` ↔ `mart_company_reach` consistency** for sample sites (one lower-bound, one normal): exact
  match on distinct-owner counts (117/117 and 10/10 respectively, see finding 4 above). ✓
- **Impossible-value sweep on `fct_visits`:** no negative `window_bytes`/`tracking_bytes`/`observed_bytes`/
  `tracking_companies`, no `tracking_share_bytes` outside [0, 1]. One flagged-then-explained case: 39 visits
  have `tracking_requests > window_requests` — all 39 are exactly the `is_lower_bound` visits, where
  `tracking_requests` is deliberately swapped to an all-phase count while `window_requests` stays window-only;
  not a bug. ✓
- **`mart_company_reach` sweep:** no negative bytes/requests, no `sites <= 0`. ✓
- **Classification agreement:** `assert_classification_agrees_with_crawler` still passes; recomputed
  disagreement rate is unchanged at 0.68% (744,996 requests, 5,055 disagreements) — consistent with finding 3
  having 0 current live impact. ✓
- **`dbt build` on the copy:** 7 seeds, 10 table models, 29 data tests, 5 view models — 51/51 PASS, 0 errors,
  0 warnings (including the two warn-severity tests). ✓
- **`pyflakes scripts load sample`:** clean, no output. ✓
- **Mock crawl** (`node crawler/crawl.mjs --mock --out data/raw/audit2_mock --window 10`): completed with
  `Done.`, exit 0, all 27 synthetic visits processed (including the memory-abort/flood and hang fixtures).
  Folder deleted afterwards. ✓

No regressions found anywhere I checked.

## New findings

### A. [Note] The new page-weight span (pre+window) is internally consistent but not perfectly equal-length across visits

**File:** `dbt/models/marts/fct_visits.sql:9-10, 86-87`.

The fix is correct and well-verified (see finding 1 above: numerator and denominator now provably cover the
same phases). The task asked me to comment on the choice itself: the "pre" phase runs from navigation start
to the consent click (`accept`/`reject`) or to the end of the fixed ~4s settle (`none`) — and in practice its
length is not fixed. Measured on `prep_visits.window_start_ms` (= `t0`, i.e. the pre-phase duration), real
dataset, usable visits:

| mode | median | p90 | max |
|---|---|---|---|
| accept | 5.7 s | 24.8 s | 42.4 s |
| none | 5.7 s | 9.5 s | 36.9 s |
| reject | 2.5 s | 7.0 s | 36.5 s |

So two sites in the same mode don't have perfectly equal-length "observed" spans — a site whose banner is slow
to detect/click gets a larger denominator (more time for ordinary page content to load) purely from
crawler/consent-detection timing, not from its own tracking behavior. This is a much smaller and much more
bounded effect than the bug it replaces (previously unbounded by the open-ended "after" phase; here bounded by
roughly `T.consentMax + T.verify` ≈ 17.5 s typical, with a measured tail up to ~42 s against a 30 s window),
and it is an explicit, documented trade-off, not an oversight. No fix is required; flagging only so the
trade-off is visible if the dashboard/write-up ever wants to caveat the "page weight" metric for very
slow-consent-flow outliers.

### B. [Note] My own finding 5 overstated how much of the `mart_cmp_market` tail was "noise"

Re-reviewing the pre-fix list of 43 `cmp` values against what the fix actually changed: only about 13 of the
29 non-top-9 values were genuine noise (`auto_` rule IDs or raw site domains like `web.de`, `amazon.com`). The
remaining ~16 single-site values (`cookieyes`, `cassie`, `axeptio`, `Complianz optin`, `civic-cookie-control`,
`Ensighten`, `piwik-pro`, `fides`, `real-cookie-banner`, `cookieconsent2`/`cookieconsent3`,
`cookie-consent-spice`, `dfactory-cookie-notice`, `eu-cookie-compliance-banner`, `Cookie Information Banner`,
`clinch`) are plausible real (if niche) consent-management products or WordPress cookie-consent plugins, and
the fix correctly left them as their own passthrough names — it even distinguished the site-specific
`stepstone-ccm` (folded into "In-house banner") from the generic product `ccm19` (left alone), which is more
careful than my original finding gave credit for. I did not independently verify every one of those ~16 names
against a vendor list; `clinch` is the one I'm least confident is a real product name rather than an
autoconsent-internal label, but it's a single site and low priority either way — not a finding requiring
action, just a correction to my own prior framing.

No other new issues surfaced in this pass.
