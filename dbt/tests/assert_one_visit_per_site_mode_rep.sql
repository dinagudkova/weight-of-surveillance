-- prep_visits must keep exactly one (latest) visit per site, mode and repeat.
select dataset, site, mode, rep, count(*) as n
from {{ ref('prep_visits') }}
group by dataset, site, mode, rep
having count(*) > 1
