{{ config(severity='warn') }}
-- Visits of sites that are not in the site sample (seeds/sites.csv) have no category or site domain.
select distinct site
from {{ ref('prep_visits') }}
where site_domain is null
