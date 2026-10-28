-- Consent-vendor crawl ("promise vs reality"). Until that crawl is loaded, raw.tcf_visits does not exist:
-- the model then returns an empty result with the same columns, so the rest of the project still builds.
{% set rel = adapter.get_relation(database=target.database, schema='raw', identifier='tcf_visits') %}
{% if rel is not none %}
select
    visit_id,
    site,
    mode,
    rep,
    visited_at,
    nav_error,
    coalesce(bot_blocked, false)   as bot_blocked,
    coalesce(memory_abort, false)  as memory_abort,
    consent_verified,
    consent_method,
    {{ normalize_cmp('cmp') }}     as cmp,
    declared_partners,
    declared_partners_snippet,
    tcf_available,
    tcf_ok,
    tcf_cmp_id,
    tcf_event_status,
    tcf_vendor_consents,
    tcf_vendor_legitimate_interests,
    tcf_purpose_consents,
    tcf_ac_vendors
from {{ source('raw', 'tcf_visits') }}
{% else %}
select
    cast(null as varchar) as visit_id, cast(null as varchar) as site, cast(null as varchar) as mode,
    cast(null as integer) as rep, cast(null as timestamp) as visited_at, cast(null as varchar) as nav_error,
    cast(null as boolean) as bot_blocked, cast(null as boolean) as memory_abort, cast(null as boolean) as consent_verified,
    cast(null as varchar) as consent_method, cast(null as varchar) as cmp, cast(null as integer) as declared_partners,
    cast(null as varchar) as declared_partners_snippet, cast(null as boolean) as tcf_available, cast(null as boolean) as tcf_ok,
    cast(null as integer) as tcf_cmp_id, cast(null as varchar) as tcf_event_status, cast(null as integer) as tcf_vendor_consents,
    cast(null as integer) as tcf_vendor_legitimate_interests, cast(null as integer) as tcf_purpose_consents,
    cast(null as integer) as tcf_ac_vendors
where 1 = 0
{% endif %}
