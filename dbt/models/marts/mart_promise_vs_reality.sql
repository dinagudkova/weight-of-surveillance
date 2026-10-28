-- "Promise vs reality": how many partners does the consent banner ask consent for, and how many tracking
-- companies did we actually see after "Accept all"?
--   promised (IAB TCF): vendors with consent after a verified "Accept all" (tcf_vendor_consents),
--                       plus non-IAB vendors from Google's Additional Consent string (tcf_ac_vendors)
--   promised (text):    the number of partners stated in the banner text, as a cross-check
--   observed:           tracking companies after "Accept all" in the main study (median over repeats)
-- Observed companies are a lower bound of who receives data: server-side sharing is not visible.
with tcf as (
    select
        *,
        row_number() over (partition by site order by visited_at desc, visit_id desc) as rn
    from {{ ref('stg_tcf_visits') }}
    where mode = 'accept' and nav_error is null and not bot_blocked
),

declared as (
    -- partners stated in the banner text (read before the click, any mode of the consent-vendor crawl)
    select site, max(declared_partners) as declared_partners_text
    from {{ ref('stg_tcf_visits') }}
    group by site
)

select
    s.site,
    s.site_domain,
    s.site_category,
    s.site_category_group,
    s.site_group_label,
    s.site_group_order,
    s.site_sample_source,
    s.cmp,
    s.pay_or_okay,
    s.has_banner,
    t.consent_verified                                           as tcf_accept_verified,
    coalesce(t.tcf_available, false)                             as tcf_available,
    case when t.tcf_ok and t.consent_verified then t.tcf_vendor_consents end as promised_iab_vendors,
    case when t.tcf_ok and t.consent_verified then t.tcf_ac_vendors end      as promised_other_vendors,
    case when t.tcf_ok and t.consent_verified
         then coalesce(t.tcf_vendor_consents, 0) + coalesce(t.tcf_ac_vendors, 0) end as promised_vendors_total,
    d.declared_partners_text,
    s.accept_tracking_companies                                  as observed_companies,
    s.accept_is_lower_bound                                      as observed_is_lower_bound,
    case when t.tcf_ok and t.consent_verified and s.accept_tracking_companies > 0
         then 1.0 * (coalesce(t.tcf_vendor_consents, 0) + coalesce(t.tcf_ac_vendors, 0)) / s.accept_tracking_companies
    end                                                          as promised_per_observed
from {{ ref('mart_site_consent_effect') }} s
left join tcf t on t.site = s.site and t.rn = 1
left join declared d on d.site = s.site
