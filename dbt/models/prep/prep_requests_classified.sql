{{ config(materialized=('table' if target.type == 'duckdb' else 'view')) }}
-- Request classification, same rules as classify.mjs, but driven by the dbt seeds,
-- so changing a list and running `dbt build` re-classifies everything without crawling again.
-- Rule-list matches (EasyPrivacy, EasyList) and DNS CNAME chains cannot be evaluated in SQL;
-- they come from the crawler as flags.
-- In PostgreSQL (Neon) this model is a view to save storage.
with base as (
    select
        r.*,
        v.site,
        v.mode,
        v.rep,
        v.site_category,
        v.site_domain,
        v.is_measured,
        v.is_usable,
        h.tracker_domain,
        h.tracker_owner,
        h.tracker_only_non_tracking,
        h.tracker_cdn_like,
        -- type flags come from the CNAME target's tracker if the host is a cloaked tracker (as in classify.mjs)
        case when r.via_cname and hc.tracker_domain is not null then hc.tracker_ad_category else h.tracker_ad_category end as tracker_ad_category,
        case when r.via_cname and hc.tracker_domain is not null then hc.tracker_action_pixel else h.tracker_action_pixel end as tracker_action_pixel,
        case when r.via_cname and hc.tracker_domain is not null then hc.tracker_ad_owner else h.tracker_ad_owner end as tracker_ad_owner,
        case when r.via_cname and hc.tracker_domain is not null then hc.tracker_identity else h.tracker_identity end as tracker_identity,
        case when r.via_cname and hc.tracker_domain is not null then hc.tracker_telemetry else h.tracker_telemetry end as tracker_telemetry,
        h.host_entity,
        h.is_cmp_host,
        hc.tracker_owner as cname_tracker_owner,
        -- coalesce: a missing entity on either side must mean "not the same owner", not NULL
        coalesce(
            r.reg_domain = v.site_domain
            or a.alias_domain is not null
            or (h.host_entity is not null and se.entity is not null and h.host_entity = se.entity),
            false
        ) as is_first_party
    from {{ ref('stg_requests') }} r
    join {{ ref('prep_visits') }} v on v.visit_id = r.visit_id
    left join {{ ref('prep_host_lookup') }} h on h.host = r.host
    left join {{ ref('prep_host_lookup') }} hc on hc.host = lower(r.cname_target)
    left join {{ ref('site_aliases') }} a on a.site_domain = v.site_domain and a.alias_domain = r.reg_domain
    left join {{ ref('domain_entities') }} se on se.domain = v.site_domain
),

flags as (
    select
        *,
        not is_first_party as is_third_party,
        (
            not is_first_party
            and tracker_domain is not null
            and not tracker_only_non_tracking
            and (not tracker_cdn_like or via_easyprivacy)
        ) as via_tracker_list,
        (via_easylist and not is_first_party) as via_easylist_third_party
    from base
),

tracking as (
    select
        *,
        (
            not is_cmp_host
            and (via_tracker_list or via_cname or via_easyprivacy or via_easylist_third_party)
        ) as matches_tracking_rule,
        (not is_first_party and tracker_telemetry) as is_telemetry_host
    from flags
)

select
    visit_id,
    site,
    mode,
    rep,
    site_category,
    site_domain,
    is_measured,
    is_usable,
    start_ms,
    phase,
    url,
    resource_type,
    status,
    failed,
    bytes,
    host,
    reg_domain,
    is_first_party,
    is_third_party,
    via_tracker_list,
    via_easyprivacy,
    via_easylist_third_party,
    via_cname,
    is_cmp_host                                         as is_consent,
    (matches_tracking_rule and is_telemetry_host)       as is_telemetry,
    (matches_tracking_rule and not is_telemetry_host)   as is_tracking,
    case
        when is_cmp_host then 'consent'
        when matches_tracking_rule and is_telemetry_host then 'telemetry'
        when matches_tracking_rule then 'tracking'
        when is_first_party then 'first-party'
        else 'other'
    end as request_category,
    case
        when not matches_tracking_rule or is_telemetry_host then null
        when tracker_identity or url_is_sync then 'identity'
        when via_easylist_third_party then 'advertising'
        when tracker_action_pixel then 'advertising'
        when tracker_ad_owner then 'advertising'
        when tracker_ad_category then 'advertising'
        else 'analytics'
    end as tracking_type,
    case
        when via_cname and cname_tracker_owner is not null then cname_tracker_owner
        when is_third_party and tracker_domain is not null then tracker_owner
        when is_third_party then coalesce(host_entity, reg_domain)
        else site_domain || ' (first-party)'
    end as owner,
    crawler_category,
    crawler_is_tracking
from tracking
