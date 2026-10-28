-- Business question 4: which types of websites carry the heaviest tracking load.
-- Accept/reject medians only use sites with a consent banner: on sites without one, "accept" and
-- "reject" are the same page as "none" and would pull the medians towards zero.
select
    site_category,
    count(*)                                                                     as sites,
    count(*) filter (where site_sample_source = 'crux_top5000_boost')            as sites_boost,
    count(*) filter (where has_banner)                                           as sites_with_banner,
    {{ median('none_tracking_requests') }}                                       as median_none_tracking_requests,
    {{ median("case when has_banner then accept_tracking_requests end") }}       as median_accept_tracking_requests,
    {{ median("case when has_banner then accept_tracking_bytes end") }}          as median_accept_tracking_bytes,
    {{ median("case when has_banner then accept_tracking_share_bytes end") }}    as median_accept_tracking_share_bytes,
    {{ median("case when has_banner then reject_tracking_requests end") }}       as median_reject_tracking_requests,
    {{ median("case when has_banner then accept_tracking_companies end") }}      as median_accept_tracking_companies,
    count(*) filter (where has_banner and accept_tenfold)                        as sites_accept_tenfold,
    count(*) filter (where pay_or_okay)                                          as sites_pay_or_okay,
    count(*) filter (where accept_is_lower_bound)                                as sites_accept_lower_bound
from {{ ref('mart_site_consent_effect') }}
group by site_category
