select
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
from {{ source('raw', 'requests') }}
where host is not null and host <> ''
