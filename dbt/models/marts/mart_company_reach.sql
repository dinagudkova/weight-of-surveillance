-- Business questions 2 and 5: which companies receive data, on how many sites, and how much.
select
    owner,
    mode,
    tracking_type,
    count(distinct site)  as sites,
    count(*)              as requests,
    sum(bytes)            as bytes
from {{ ref('prep_requests_classified') }}
where is_usable and phase = 'window' and is_tracking and dataset = '{{ var("main_dataset") }}'
group by owner, mode, tracking_type
