-- Latest visit per site, mode and repeat, enriched with the site sample, plus validity flags:
--   is_measured: the page loaded, was not a bot-protection page and was not aborted for memory
--   is_usable:   measured, and for accept/reject the banner was verifiably closed
--                (sites without any banner count as usable in every mode)
with ranked as (
    select
        v.*,
        row_number() over (partition by v.site, v.mode, v.rep order by v.visited_at desc, v.visit_id desc) as rn
    from {{ ref('stg_visits') }} v
),

latest as (
    select
        r.*,
        coalesce(s.category, r.crawl_category) as site_category,
        s.subcategory                         as site_subcategory,
        s.site_domain,
        s.market
    from ranked r
    left join {{ ref('sites') }} s on s.url = r.site
    where r.rn = 1
),

measured as (
    select
        *,
        (nav_error is null and not bot_blocked and not memory_abort and request_count > 1) as is_measured
    from latest
),

site_flags as (
    select
        site,
        bool_or(banner_pre or cmp is not null)          as site_has_banner,
        bool_or(pay_or_okay)                            as site_pay_or_okay,
        bool_or(mode = 'reject' and consent_verified)   as site_reject_verified
    from measured
    where is_measured
    group by site
)

select
    m.*,
    coalesce(f.site_has_banner, false)      as site_has_banner,
    coalesce(f.site_pay_or_okay, false)     as site_pay_or_okay,
    coalesce(f.site_reject_verified, false) as site_reject_verified,
    (
        m.is_measured
        and (m.mode = 'none' or coalesce(m.consent_verified, false) or not coalesce(f.site_has_banner, false))
    ) as is_usable
from measured m
left join site_flags f on f.site = m.site
