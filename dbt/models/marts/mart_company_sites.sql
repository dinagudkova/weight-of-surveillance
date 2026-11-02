-- Business question 2: which companies reach the most sites, per consent mode.
-- One row per company and mode with distinct sites across all tracking types (mart_company_reach splits a
-- company by tracking type, so its site counts cannot be added up per company).
-- Same requests as mart_company_reach: window phase, plus all phases of memory-aborted Accept visits;
-- self-hosted tracking ('<site> (first-party)') is not a company and is left out.
with reach as (
    select
        owner,
        mode,
        count(distinct site)                                           as sites,
        count(*)                                                       as requests,
        sum(bytes)                                                     as bytes,
        string_agg(distinct tracking_type, ', ' order by tracking_type) as tracking_types
    from {{ ref('prep_requests_classified') }}
    where is_usable and is_tracking and (phase = 'window' or is_lower_bound) and owner not like '%(first-party)'
      and dataset = '{{ var("main_dataset") }}'
    group by owner, mode
),

measured as (
    select mode, count(distinct site) as sites_measured
    from {{ ref('fct_visits') }}
    where is_usable and dataset = '{{ var("main_dataset") }}'
    group by mode
)

select
    r.owner,
    r.mode,
    r.sites,
    m.sites_measured,
    1.0 * r.sites / m.sites_measured                                         as share_of_sites,
    r.requests,
    r.bytes,
    r.tracking_types,
    row_number() over (partition by r.mode order by r.sites desc, r.requests desc, r.owner) as rank_in_mode
from reach r
join measured m on m.mode = r.mode
