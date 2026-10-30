-- Union of the automated crawl, the real-browser crawl and manual HAR imports (when loaded):
-- The dataset column tells them apart; marts use var('main_dataset').
{% set parts = [(source('raw', 'visits'), 'automated')] %}
{% for prefix, ds in [('real_', 'real'), ('manual_', 'manual')] %}
{% if adapter.get_relation(database=target.database, schema='raw', identifier=prefix ~ 'visits') is not none %}
{% do parts.append((source('raw', prefix ~ 'visits'), ds)) %}
{% endif %}
{% endfor %}
{% for rel, ds in parts %}
select
    cast('{{ ds }}' as varchar) as dataset,
    visit_id,
    site,
    crawl_category,
    mode,
    rep,
    visited_at,
    machine,
    shard,
    cpu,
    cores,
    platform,
    browser_version,
    nav_error,
    coalesce(load_timeout, false)   as load_timeout,
    main_status,
    final_url,
    coalesce(bot_blocked, false)    as bot_blocked,
    coalesce(banner_pre, false)     as banner_pre,
    banner_text,
    coalesce(pay_or_okay, false)    as pay_or_okay,
    banner_end,
    cmp                             as cmp_rule,
    {{ normalize_cmp('cmp') }}      as cmp,
    autoconsent_done,
    clicks,
    coalesce(consent_attempted, false) as consent_attempted,
    consent_method,
    fallback_label,
    consent_verified,
    consent_at_ms,
    window_start_ms,
    window_ms,
    script_ms,
    task_ms,
    cookies_pre_total,
    cookies_pre_third_party,
    cookies_pre_tracker,
    cookies_pre_tracker_owners,
    cookies_end_total,
    cookies_end_third_party,
    cookies_end_tracker,
    cookies_end_tracker_owners,
    coalesce(request_count, 0)      as request_count,
    coalesce(requests_dropped, 0)   as requests_dropped,
    coalesce(memory_abort, false)   as memory_abort
from {{ rel }}
{% if not loop.last %}union all{% endif %}
{% endfor %}
