-- One row per site: tracking in the three consent modes (median over repeats, usable visits only),
-- and how free the choice is. Main table for business questions 1, 3, 4 and 7.
with usable as (
    select * from {{ ref('fct_visits') }} where is_usable and dataset = '{{ var("main_dataset") }}'
),

per_site as (
    select
        site,
        max(site_domain)    as site_domain,
        max(site_category)  as site_category,
        max(site_category_group) as site_category_group,
        max(site_group_label) as site_group_label,
        max(site_group_order) as site_group_order,
        max(site_subcategory) as site_subcategory,
        max(site_sample_source) as site_sample_source,
        coalesce(max(case when cmp <> 'Unknown (generic banner)' then cmp end), max(cmp)) as cmp,
        {{ median("case when mode = 'none' then tracking_requests end") }}   as none_tracking_requests,
        {{ median("case when mode = 'reject' then tracking_requests end") }} as reject_tracking_requests,
        {{ median("case when mode = 'accept' then tracking_requests end") }} as accept_tracking_requests,
        {{ median("case when mode = 'none' then tracking_bytes end") }}      as none_tracking_bytes,
        {{ median("case when mode = 'reject' then tracking_bytes end") }}    as reject_tracking_bytes,
        {{ median("case when mode = 'accept' then tracking_bytes end") }}    as accept_tracking_bytes,
        {{ median("case when mode = 'accept' then tracking_share_bytes end") }} as accept_tracking_share_bytes,
        {{ median("case when mode = 'accept' then tracking_companies end") }} as accept_tracking_companies,
        {{ median("case when mode = 'accept' then identity_requests end") }}  as accept_identity_requests,
        {{ median("case when mode = 'reject' then identity_requests end") }}  as reject_identity_requests,
        {{ median("case when mode = 'reject' then analytics_requests end") }} as reject_analytics_requests,
        {{ median("case when mode = 'none' then script_ms end") }}            as none_script_ms,
        {{ median("case when mode = 'accept' then script_ms end") }}          as accept_script_ms,
        count(distinct mode) as modes_measured,
        bool_or(mode = 'accept' and is_lower_bound) as accept_is_lower_bound
    from usable
    group by site
),

choice as (
    select
        site,
        bool_or(site_has_banner)      as has_banner,
        bool_or(site_pay_or_okay)     as pay_or_okay,
        bool_or(mode = 'reject' and is_usable and consent_verified) as reject_verified
    from {{ ref('fct_visits') }}
    where is_measured and dataset = '{{ var("main_dataset") }}'
    group by site
)

select
    p.*,
    c.has_banner,
    c.pay_or_okay,
    case
        when not c.has_banner then 'no banner'
        when not c.pay_or_okay and c.reject_verified then 'reject on first layer'
        when c.pay_or_okay and c.reject_verified then 'reject only in settings'
        when c.pay_or_okay then 'no reject without subscription'
        else 'reject not verified'
    end as reject_option,
    case when p.none_tracking_requests > 0
         then 1.0 * p.accept_tracking_requests / p.none_tracking_requests end as accept_vs_none_ratio,
    (p.accept_tracking_requests >= 10 * greatest(p.none_tracking_requests, 1)) as accept_tenfold
from per_site p
join choice c on c.site = p.site
