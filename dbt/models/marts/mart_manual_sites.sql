-- Sites that block automated browsers, measured by hand in a normal Chrome (HAR files, crawler/har_import.mjs).
-- Same classification as the crawler, but a different procedure (manual click and timing), so these sites are
-- shown separately and never pooled into the group medians. For orientation, the group medians of the main
-- dataset (sites with a banner) are attached.
with manual as (
    select site, site_domain, site_category, site_category_group, site_group_label, site_group_order, mode,
           tracking_requests, tracking_companies, tracking_bytes, identity_requests, tracking_share_bytes
    from {{ ref('fct_visits') }}
    where dataset = 'manual' and is_usable
)

select
    m.*,
    case m.mode when 'accept' then g.median_accept_tracking_requests
                when 'reject' then g.median_reject_tracking_requests
                else g.median_none_tracking_requests end      as group_median_tracking_requests,
    case when m.mode = 'accept' then g.median_accept_tracking_companies end as group_median_accept_companies
from manual m
left join {{ ref('mart_group_summary') }} g on g.category_group = m.site_category_group
