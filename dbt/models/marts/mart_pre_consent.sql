-- Business question 8: tracking before the user makes any choice (mode "none", load + settle phase).
-- Indicators for manual verification, not proof of a violation.
select
    site,
    site_domain,
    site_category,
    {{ median('pre_tracking_requests') }}     as pre_tracking_requests,
    {{ median('pre_advertising_requests') }}  as pre_advertising_requests,
    {{ median('pre_identity_requests') }}     as pre_identity_requests,
    max(cookies_pre_tracker)                  as tracker_cookies_before_choice,
    max(cookies_pre_tracker_owners)           as tracker_cookie_owners
from {{ ref('fct_visits') }}
where is_usable and mode = 'none'
group by site, site_domain, site_category
