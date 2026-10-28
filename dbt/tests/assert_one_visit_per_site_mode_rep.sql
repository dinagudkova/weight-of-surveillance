-- prep_visits must keep exactly one (latest) visit per site, mode and repeat.
select site, mode, rep, count(*) as n
from {{ ref('prep_visits') }}
group by site, mode, rep
having count(*) > 1
