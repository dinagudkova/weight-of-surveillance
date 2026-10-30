{{ config(enabled=false) }}
-- DISABLED: three of four machines of the automated crawl ran behind a DNS ad/tracker blocker (Proton VPN
-- NetShield), so its tracking numbers are not comparable with the real-browser crawl. Kept for reference only.
-- Automated crawl vs real-browser crawl, per site and consent mode (usable visits, medians over repeats).
-- Ad systems often skip ad auctions for browsers that report automation; this mart shows how much tracking
-- the automated crawl misses. Empty until the real-browser crawl is loaded (load_raw.py --dataset real).
with visit_extra as (
    select
        visit_id,
        count(distinct case when is_third_party then reg_domain end) as third_party_domains,
        bool_or(url like '%/gampad/%')                              as gam_auction
    from {{ ref('prep_requests_classified') }}
    group by visit_id
),

per_dataset as (
    select
        v.dataset,
        v.site,
        v.mode,
        max(v.site_category_group)                     as site_category_group,
        max(v.site_group_label)                        as site_group_label,
        max(v.site_group_order)                        as site_group_order,
        {{ median('v.tracking_requests') }}            as tracking_requests,
        {{ median('v.tracking_companies') }}           as tracking_companies,
        {{ median('v.tracking_bytes') }}               as tracking_bytes,
        {{ median('e.third_party_domains') }}          as third_party_domains,
        bool_or(coalesce(e.gam_auction, false))        as gam_auction,
        bool_or(v.is_lower_bound)                      as is_lower_bound
    from {{ ref('fct_visits') }} v
    left join visit_extra e on e.visit_id = v.visit_id
    where v.is_usable
    group by v.dataset, v.site, v.mode
)

select
    a.site,
    a.mode,
    a.site_category_group,
    a.site_group_label,
    a.site_group_order,
    a.tracking_requests     as automated_tracking_requests,
    r.tracking_requests     as real_tracking_requests,
    a.tracking_companies    as automated_tracking_companies,
    r.tracking_companies    as real_tracking_companies,
    a.tracking_bytes        as automated_tracking_bytes,
    r.tracking_bytes        as real_tracking_bytes,
    a.third_party_domains   as automated_third_party_domains,
    r.third_party_domains   as real_third_party_domains,
    a.gam_auction           as automated_gam_auction,
    r.gam_auction           as real_gam_auction,
    a.is_lower_bound        as automated_is_lower_bound,
    r.is_lower_bound        as real_is_lower_bound,
    case when a.tracking_requests > 0 then 1.0 * r.tracking_requests / a.tracking_requests end as tracking_requests_ratio,
    case when a.tracking_companies > 0 then 1.0 * r.tracking_companies / a.tracking_companies end as tracking_companies_ratio
from per_dataset a
join per_dataset r on r.site = a.site and r.mode = a.mode
where a.dataset = 'automated' and r.dataset = 'real'
