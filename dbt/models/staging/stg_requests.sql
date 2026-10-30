-- Union of the automated crawl, the real-browser crawl and manual HAR imports (when loaded):
-- The dataset column tells them apart; marts use var('main_dataset').
{% set parts = [(source('raw', 'requests'), 'automated')] %}
{% for prefix, ds in [('real_', 'real'), ('manual_', 'manual')] %}
{% if adapter.get_relation(database=target.database, schema='raw', identifier=prefix ~ 'requests') is not none %}
{% do parts.append((source('raw', prefix ~ 'requests'), ds)) %}
{% endif %}
{% endfor %}
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
