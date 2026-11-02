-- Business question 2: which companies reach the most sites, per consent mode.
-- One row per company and mode with distinct sites across all tracking types (mart_company_reach splits a
-- company by tracking type, so its site counts cannot be added up per company).
-- Same requests as mart_company_reach (window phase, plus all phases of memory-aborted Accept visits; self-hosted
-- tracking '<site> (first-party)' is not a company), but only on sites with a consent banner, like all other
-- accept/reject results: on a site without a banner an "Accept" visit is just a page load without a click.
with reach as (
    select
        p.owner,
        p.mode,
        count(distinct p.site)                                             as sites,
        count(*)                                                           as requests,
        sum(p.bytes)                                                       as bytes,
        string_agg(distinct p.tracking_type, ', ' order by p.tracking_type) as tracking_types
    from {{ ref('prep_requests_classified') }} p
    join {{ ref('fct_visits') }} v on v.visit_id = p.visit_id
    where p.is_usable and p.is_tracking and (p.phase = 'window' or p.is_lower_bound)
      and p.owner not like '%(first-party)' and v.site_has_banner
      and p.dataset = '{{ var("main_dataset") }}'
    group by p.owner, p.mode
),

measured as (
    select mode, count(distinct site) as sites_measured
    from {{ ref('fct_visits') }}
    where is_usable and site_has_banner and dataset = '{{ var("main_dataset") }}'
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
