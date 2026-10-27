{{ config(materialized='table') }}
-- One row per host: the most specific matching tracker (custom list before DuckDuckGo TDS),
-- the owning entity and whether the host belongs to a consent platform.
with hosts as (
    select distinct host from {{ ref('prep_host_suffixes') }}
),

tracker_match as (
    select
        s.host,
        t.domain   as tracker_domain,
        t.owner    as tracker_owner,
        t.source   as tracker_source,
        t.categories as tracker_categories,
        t.only_non_tracking, t.cdn_like, t.ad_category, t.action_pixel, t.ad_owner, t.identity, t.telemetry,
        row_number() over (partition by s.host order by t.priority, s.lvl) as rn
    from {{ ref('prep_host_suffixes') }} s
    join {{ ref('trackers') }} t on t.domain = s.suffix
),

entity_match as (
    select s.host, e.entity, row_number() over (partition by s.host order by s.lvl) as rn
    from {{ ref('prep_host_suffixes') }} s
    join {{ ref('domain_entities') }} e on e.domain = s.suffix
),

cmp_match as (
    select distinct s.host
    from {{ ref('prep_host_suffixes') }} s
    join {{ ref('cmp_domains') }} c on c.domain = s.suffix
)

select
    h.host,
    t.tracker_domain,
    t.tracker_owner,
    t.tracker_source,
    t.tracker_categories,
    coalesce(t.only_non_tracking, false) as tracker_only_non_tracking,
    coalesce(t.cdn_like, false)          as tracker_cdn_like,
    coalesce(t.ad_category, false)       as tracker_ad_category,
    coalesce(t.action_pixel, false)      as tracker_action_pixel,
    coalesce(t.ad_owner, false)          as tracker_ad_owner,
    coalesce(t.identity, false)          as tracker_identity,
    coalesce(t.telemetry, false)         as tracker_telemetry,
    e.entity                             as host_entity,
    (c.host is not null)                 as is_cmp_host
from hosts h
left join tracker_match t on t.host = h.host and t.rn = 1
left join entity_match e on e.host = h.host and e.rn = 1
left join cmp_match c on c.host = h.host
