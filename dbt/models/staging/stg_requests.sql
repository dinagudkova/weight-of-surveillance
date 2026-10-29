-- Union of the automated crawl (raw.requests) and, once loaded, the real-browser crawl (raw.real_requests).
-- The dataset column tells them apart; marts use var('main_dataset') and mart_dataset_comparison compares both.
{% set real = adapter.get_relation(database=target.database, schema='raw', identifier='real_requests') %}
{% set parts = [(source('raw', 'requests'), 'automated')] %}
{% if real is not none %}{% do parts.append((source('raw', 'real_requests'), 'real')) %}{% endif %}
{% for rel, ds in parts %}
select
    cast('{{ ds }}' as varchar) as dataset,
    visit_id,
    start_ms,
    phase,
    url,
    resource_type,
    status,
    mime,
    failed,
    bytes,
    body_bytes,
    upload_bytes,
    host,
    reg_domain,
    via_easyprivacy,
    via_easylist,
    via_cname,
    cname_target,
    url_is_sync,
    crawler_category,
    crawler_tracking_type,
    crawler_is_tracking
from {{ rel }}
where host is not null and host <> ''
{% if not loop.last %}union all{% endif %}
{% endfor %}
