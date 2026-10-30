-- Business question 1, "the first seconds after the click": per visit, how soon after the consent click the
-- first tracking request, the first advertising request and the first ID sync start, and how many companies
-- receive a request within the first second and the first five seconds.
-- Time 0 is the click (accept/reject) or, for "none", the end of the settle phase (no click: a baseline).
-- Usable visits of the main dataset on sites with a banner; memory-aborted visits are left out (their window
-- ends early). Self-hosted tracking ('<site> (first-party)') is not counted as a company.
with v as (
    select visit_id, site, site_domain, site_category, site_category_group, site_group_label, site_group_order,
           mode, window_start_ms
    from {{ ref('prep_visits') }}
    where dataset = '{{ var("main_dataset") }}' and is_usable and site_has_banner and not is_lower_bound
      and window_start_ms is not null
),

r as (
    select
        p.visit_id,
        p.owner,
        p.tracking_type,
        p.start_ms - v.window_start_ms as ms_after_t0
    from {{ ref('prep_requests_classified') }} p
    join v on v.visit_id = p.visit_id
    where p.is_tracking and p.phase = 'window'
),

per_visit as (
    select
        visit_id,
        min(ms_after_t0)                                                            as ms_to_first_tracking,
        min(ms_after_t0) filter (where tracking_type = 'advertising')               as ms_to_first_advertising,
        min(ms_after_t0) filter (where tracking_type = 'identity')                  as ms_to_first_identity_sync,
        count(*) filter (where ms_after_t0 < 1000)                                  as tracking_requests_1s,
        count(*) filter (where ms_after_t0 < 5000)                                  as tracking_requests_5s,
        count(distinct owner) filter (where ms_after_t0 < 1000 and owner not like '%(first-party)') as companies_1s,
        count(distinct owner) filter (where ms_after_t0 < 5000 and owner not like '%(first-party)') as companies_5s,
        count(distinct owner) filter (where owner not like '%(first-party)')        as companies_30s
    from r
    group by visit_id
)

select
    v.*,
    p.ms_to_first_tracking,
    p.ms_to_first_advertising,
    p.ms_to_first_identity_sync,
    coalesce(p.tracking_requests_1s, 0) as tracking_requests_1s,
    coalesce(p.tracking_requests_5s, 0) as tracking_requests_5s,
    coalesce(p.companies_1s, 0)         as companies_1s,
    coalesce(p.companies_5s, 0)         as companies_5s,
    coalesce(p.companies_30s, 0)        as companies_30s
from v
left join per_visit p on p.visit_id = v.visit_id
