-- One row per visit with the tracking metrics of its observation window.
-- Window metrics only count requests that started inside the fixed window after the consent click
-- (or after the pre snapshot in mode "none"), so all modes are observed equally long.
with req as (
    select
        visit_id,
        count(*) filter (where phase = 'window')                                       as window_requests,
        coalesce(sum(bytes) filter (where phase = 'window'), 0)                        as window_bytes,
        count(*) filter (where phase = 'window' and is_tracking)                       as tracking_requests,
        coalesce(sum(bytes) filter (where phase = 'window' and is_tracking), 0)        as tracking_bytes,
        count(*) filter (where phase = 'window' and tracking_type = 'advertising')     as advertising_requests,
        count(*) filter (where phase = 'window' and tracking_type = 'analytics')       as analytics_requests,
        count(*) filter (where phase = 'window' and tracking_type = 'identity')        as identity_requests,
        coalesce(sum(bytes) filter (where phase = 'window' and tracking_type = 'advertising'), 0) as advertising_bytes,
        coalesce(sum(bytes) filter (where phase = 'window' and tracking_type = 'analytics'), 0)   as analytics_bytes,
        coalesce(sum(bytes) filter (where phase = 'window' and tracking_type = 'identity'), 0)    as identity_bytes,
        count(*) filter (where phase = 'window' and is_telemetry)                      as telemetry_requests,
        coalesce(sum(bytes) filter (where phase = 'window' and is_consent), 0)         as consent_bytes,
        count(distinct owner) filter (where phase = 'window' and is_tracking)          as tracking_companies,
        count(*) filter (where phase = 'pre' and is_tracking)                          as pre_tracking_requests,
        count(*) filter (where phase = 'pre' and tracking_type = 'advertising')        as pre_advertising_requests,
        count(*) filter (where phase = 'pre' and tracking_type = 'identity')           as pre_identity_requests
    from {{ ref('prep_requests_classified') }}
    group by visit_id
)

select
    v.visit_id,
    v.site,
    v.site_domain,
    v.site_category,
    v.site_subcategory,
    v.mode,
    v.rep,
    v.visited_at,
    v.machine,
    v.is_measured,
    v.is_usable,
    v.bot_blocked,
    v.nav_error,
    v.cmp,
    v.banner_pre,
    v.pay_or_okay,
    v.consent_method,
    v.consent_verified,
    v.site_has_banner,
    v.site_pay_or_okay,
    v.site_reject_verified,
    v.window_ms,
    v.script_ms,
    v.cookies_pre_tracker,
    v.cookies_pre_tracker_owners,
    v.cookies_end_tracker,
    coalesce(r.window_requests, 0)        as window_requests,
    coalesce(r.window_bytes, 0)           as window_bytes,
    coalesce(r.tracking_requests, 0)      as tracking_requests,
    coalesce(r.tracking_bytes, 0)         as tracking_bytes,
    coalesce(r.advertising_requests, 0)   as advertising_requests,
    coalesce(r.analytics_requests, 0)     as analytics_requests,
    coalesce(r.identity_requests, 0)      as identity_requests,
    coalesce(r.advertising_bytes, 0)      as advertising_bytes,
    coalesce(r.analytics_bytes, 0)        as analytics_bytes,
    coalesce(r.identity_bytes, 0)         as identity_bytes,
    coalesce(r.telemetry_requests, 0)     as telemetry_requests,
    coalesce(r.consent_bytes, 0)          as consent_bytes,
    coalesce(r.tracking_companies, 0)     as tracking_companies,
    coalesce(r.pre_tracking_requests, 0)  as pre_tracking_requests,
    coalesce(r.pre_advertising_requests, 0) as pre_advertising_requests,
    coalesce(r.pre_identity_requests, 0)  as pre_identity_requests,
    case when coalesce(r.window_bytes, 0) > 0 then 1.0 * r.tracking_bytes / r.window_bytes end as tracking_share_bytes
from {{ ref('prep_visits') }} v
left join req r on r.visit_id = v.visit_id
