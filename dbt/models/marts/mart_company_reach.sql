-- Business questions 2 and 5: which companies receive data, on how many sites, and how much.
-- Window phase only, except memory-aborted accept visits (lower bounds), which count all phases as in fct_visits.
-- Self-hosted tracking ('<site> (first-party)') is not a company and is left out.
select
    owner,
    mode,
    tracking_type,
    count(distinct site)  as sites,
    count(*)              as requests,
    sum(bytes)            as bytes
from {{ ref('prep_requests_classified') }}
where is_usable and is_tracking and (phase = 'window' or is_lower_bound) and owner not like '%(first-party)'
  and dataset = '{{ var("main_dataset") }}'
group by owner, mode, tracking_type
