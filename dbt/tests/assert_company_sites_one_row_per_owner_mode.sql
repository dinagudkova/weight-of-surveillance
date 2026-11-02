-- mart_company_sites has exactly one row per company and consent mode.
select owner, mode, count(*) as rows_
from {{ ref('mart_company_sites') }}
group by owner, mode
having count(*) > 1
