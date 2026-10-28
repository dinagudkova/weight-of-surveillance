-- Latest visit per site, mode and repeat, enriched with the site sample, plus validity flags:
--   is_measured:    the page loaded and was not a bot-protection page. Accept visits aborted for memory
--                   (request floods) count as measured, but only as a lower bound (is_lower_bound).
--   is_usable:      measured, and for accept/reject the banner was verifiably closed (sites without any
--                   banner count as usable in every mode). Memory-aborted accept visits are usable as
--                   lower bounds: the flood only starts after consent, while none/reject stay small.
--   site_pay_or_okay: crawler flag on any visit of the site, or confirmed manually (seeds/manual_site_flags).
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
        coalesce(g.category_group, 'other')    as site_category_group,
        coalesce(g.group_label, 'Other')       as site_group_label,
        coalesce(g.group_order, 99)            as site_group_order,
        s.subcategory                         as site_subcategory,
        s.site_domain,
        s.market
    from ranked r
    left join {{ ref('sites') }} s on s.url = r.site
    left join {{ ref('category_groups') }} g on g.site_category = coalesce(s.category, r.crawl_category)
    where r.rn = 1
),

measured as (
    select
        *,
        (
            nav_error is null and not bot_blocked and request_count > 1
            and (not memory_abort or mode = 'accept')
        ) as is_measured,
        (memory_abort and mode = 'accept') as is_lower_bound
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
    coalesce(f.site_has_banner, false)                                   as site_has_banner,
    (coalesce(f.site_pay_or_okay, false) or coalesce(mf.pay_or_okay, false)) as site_pay_or_okay,
    (mf.pay_or_okay is not null)                                         as site_pay_or_okay_manual,
    coalesce(f.site_reject_verified, false)                              as site_reject_verified,
    (
        m.is_measured
        and (
            m.mode = 'none'
            or coalesce(m.consent_verified, false)
            or m.is_lower_bound
            or not coalesce(f.site_has_banner, false)
        )
    ) as is_usable
from measured m
left join site_flags f on f.site = m.site
left join {{ ref('manual_site_flags') }} mf on mf.site_domain = m.site_domain
