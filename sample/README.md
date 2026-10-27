# Site sample

`build_sample.py` builds the list of sites for the full study from the Chrome UX Report (CrUX) top list for Germany.

## Steps

1. **Candidates.** Download the latest CrUX list, keep the top 1,000 origins, merge origins of the same domain (`m.bild.de` + `www.bild.de` → `bild.de`), mark exclusions and draft a category per domain:

   ```bash
   python sample/build_sample.py            # optional: --titles, --month 202609, --bucket 5000
   ```

   Output: `sample/candidates.csv`.

2. **Manual review** of `sample/candidates.csv`, especially rows with `category_source` = `rule` or `none`.
   Record decisions in the lists, not in `candidates.csv` (it is overwritten on every run):
   - categories: add `domain,category,subcategory` to `lists/category_overrides.csv`;
   - exclusions: add `domain,reason` to `lists/exclude_domains.csv` (e.g. `crm.onoffice.de` → `onoffice.de,login only`).

   Then run step 1 again.

3. **Final sample**, stratified by category:

   ```bash
   python sample/build_sample.py --from-reviewed sample/candidates.csv --sample 500 --market de
   ```

   Output: `sites_study.csv` in crawler format (`url,category,...`).

## Rules

| Column | Meaning |
|---|---|
| `category_source` | `override` (known domain, `lists/category_overrides.csv`), `rule` (keyword rule), `none` (needs review) |
| `market` | `de` for .de/.at/.ch domains, `intl` otherwise |
| `exclude_reason` | `manual: ...` (from `lists/exclude_domains.csv`), `adult`, `login_or_app_only`, `ip_address`, `gambling` (only with `--exclude-gambling`) |
| `status`, `title` | home page HTTP status and title, only with `--titles` (one request per site) |

Categories: `news_media`, `portal_email`, `ecommerce`, `classifieds_jobs`, `travel_mobility`, `finance_insurance`, `government_public`, `health`, `education`, `entertainment_gaming`, `social_community`, `services`, `brand`, `gambling`, `other`.
