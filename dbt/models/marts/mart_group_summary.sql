-- Business question 4 at the level of the dashboard: tracking load by category group
-- (see seeds/category_groups). Same rules as mart_category_summary: accept/reject medians only use
-- sites with a consent banner; memory-aborted accept visits enter as lower bounds.
select
    site_category_group                                                          as category_group,
    max(site_group_label)                                                        as group_label,
    max(site_group_order)                                                        as group_order,
    count(*)                                                                     as sites,
    count(*) filter (where has_banner)                                           as sites_with_banner,
    {{ median('none_tracking_requests') }}                                       as median_none_tracking_requests,
    {{ median("case when has_banner then accept_tracking_requests end") }}       as median_accept_tracking_requests,
    {{ median("case when has_banner then reject_tracking_requests end") }}       as median_reject_tracking_requests,
    {{ median("case when has_banner then accept_tracking_companies end") }}      as median_accept_tracking_companies,
    {{ median("case when has_banner then accept_tracking_bytes end") }}          as median_accept_tracking_bytes,
    {{ median("case when has_banner then accept_identity_requests end") }}       as median_accept_identity_requests,
    count(*) filter (where has_banner and accept_tenfold)                        as sites_accept_tenfold,
    count(*) filter (where pay_or_okay)                                          as sites_pay_or_okay,
    count(*) filter (where reject_option = 'no reject without subscription')     as sites_no_free_reject,
    count(*) filter (where accept_is_lower_bound)                                as sites_accept_lower_bound
from {{ ref('mart_site_consent_effect') }}
group by site_category_group
