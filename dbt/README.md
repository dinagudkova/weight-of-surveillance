# dbt project

One dbt project, two targets: **DuckDB** (local file `warehouse/wos.duckdb`) and **PostgreSQL** on Neon.
The models are the same for both; the only engine-specific SQL is the `median()` macro.

## Layers

| Layer | Models | Materialization |
|---|---|---|
| seeds | `sites`, `site_aliases`, `trackers`, `domain_entities`, `cmp_domains` (built by `scripts/build_seeds.py` from `lists/`) | table |
| staging | `stg_visits`, `stg_requests` | view |
| prep | `prep_visits` (latest visit per site/mode/repeat, validity flags), `prep_host_suffixes`, `prep_host_lookup` (tracker, owner, consent platform per host), `prep_requests_classified` | view; `prep_host_lookup` table; `prep_requests_classified` table in DuckDB, view in PostgreSQL (storage) |
| marts | `fct_visits`, `mart_site_consent_effect`, `mart_category_summary`, `mart_company_reach`, `mart_cmp_market`, `mart_pre_consent` | table |

Schemas: `raw` (loader), `seeds`, `staging`, `prep`, `marts`.

## Classification

`prep_requests_classified` applies the same rules as `classify.mjs`, driven by the seeds. Changing a list in `lists/` and running `build_seeds.py` + `dbt build` re-classifies all requests without crawling again.

Two inputs cannot be evaluated in SQL and come from the crawler as flags: matches against the EasyPrivacy/EasyList rule syntax, and DNS CNAME chains.

Domain lists are matched by expanding every host into its suffixes (`a.b.example.com` → `b.example.com` → `example.com`) with a recursive CTE, so all joins are plain equality joins that work in both engines.

## Tests

- generic: not null, unique, accepted values, relationships between requests and visits;
- `assert_one_visit_per_site_mode_rep`: only the latest visit per site, mode and repeat is used;
- `assert_usable_consent_visits_are_verified`: accept/reject visits only count if the banner was verifiably closed;
- `assert_single_window_length`: all usable visits have the same observation window;
- `assert_sites_in_sample` (warn): every crawled site is in the site sample;
- `assert_classification_agrees_with_crawler` (warn): dbt and the crawler disagree on less than 2% of requests.
