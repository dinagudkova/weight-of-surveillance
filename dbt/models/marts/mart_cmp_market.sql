-- Business question 6: consent platforms in the sample and the weight of the banner itself.
with site_cmp as (
    select
        site,
        max(cmp)                       as cmp,
        bool_or(site_pay_or_okay)      as pay_or_okay,
        {{ median('consent_bytes') }}  as consent_bytes
    from {{ ref('fct_visits') }}
    where is_measured and site_has_banner and dataset = '{{ var("main_dataset") }}'
    group by site
)

select
    coalesce(cmp, 'not detected')        as cmp,
    count(*)                             as sites,
    count(*) filter (where pay_or_okay)  as sites_pay_or_okay,
    {{ median('consent_bytes') }}        as median_consent_bytes
from site_cmp
group by coalesce(cmp, 'not detected')
