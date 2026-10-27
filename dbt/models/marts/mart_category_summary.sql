-- Business question 4: which types of websites carry the heaviest tracking load.
select
    site_category,
    count(*)                                                         as sites,
    {{ median('accept_tracking_requests') }}                         as median_accept_tracking_requests,
    {{ median('accept_tracking_bytes') }}                            as median_accept_tracking_bytes,
    {{ median('accept_tracking_share_bytes') }}                      as median_accept_tracking_share_bytes,
    {{ median('reject_tracking_requests') }}                         as median_reject_tracking_requests,
    {{ median('none_tracking_requests') }}                           as median_none_tracking_requests,
    {{ median('accept_tracking_companies') }}                        as median_accept_tracking_companies,
    count(*) filter (where accept_tenfold)                           as sites_accept_tenfold,
    count(*) filter (where pay_or_okay)                              as sites_pay_or_okay
from {{ ref('mart_site_consent_effect') }}
group by site_category
