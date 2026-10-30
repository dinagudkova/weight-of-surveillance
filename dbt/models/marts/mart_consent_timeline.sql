-- Business question 1, "the first seconds after the click": for each second of the 30-second window, the
-- cumulative number of tracking requests and of companies reached so far (median over sites), and the share
-- of sites where tracking has already started. By consent mode and site group, plus 'All sites'.
-- Same visits as mart_first_tracker (usable, banner, not memory-aborted).
with recursive seconds (s) as (
    select 0
    union all
    select s + 1 from seconds where s < 29
),

v as (
    select visit_id, mode, site_group_label, site_group_order, window_start_ms
    from {{ ref('prep_visits') }}
    where dataset = '{{ var("main_dataset") }}' and is_usable and site_has_banner and not is_lower_bound
      and window_start_ms is not null
),

r as (
    select
        p.visit_id,
        p.owner,
        cast(floor((p.start_ms - v.window_start_ms) / 1000.0) as integer) as sec
    from {{ ref('prep_requests_classified') }} p
    join v on v.visit_id = p.visit_id
    where p.is_tracking and p.phase = 'window'
),

req_per_sec as (
    select visit_id, least(greatest(sec, 0), 29) as sec, count(*) as n
    from r group by 1, 2
),

first_owner as (
    -- the second in which each company is contacted for the first time in a visit
    select visit_id, owner, least(greatest(min(sec), 0), 29) as sec
    from r where owner not like '%(first-party)'
    group by 1, 2
),

new_owners_per_sec as (
    select visit_id, sec, count(*) as n from first_owner group by 1, 2
),

grid as (
    select v.visit_id, v.mode, v.site_group_label, v.site_group_order, seconds.s as second
    from v cross join seconds
),

cumulative as (
    select
        g.*,
        sum(coalesce(q.n, 0)) over (partition by g.visit_id order by g.second rows unbounded preceding) as cum_requests,
        sum(coalesce(o.n, 0)) over (partition by g.visit_id order by g.second rows unbounded preceding) as cum_companies
    from grid g
    left join req_per_sec q on q.visit_id = g.visit_id and q.sec = g.second
    left join new_owners_per_sec o on o.visit_id = g.visit_id and o.sec = g.second
),

by_group as (
    select mode, site_group_label, max(site_group_order) as site_group_order, second,
           count(*) as visits,
           {{ median('cum_requests') }}  as median_cum_tracking_requests,
           {{ median('cum_companies') }} as median_cum_companies,
           avg(case when cum_requests > 0 then 1.0 else 0.0 end) as share_sites_tracking_started
    from cumulative group by mode, site_group_label, second
),

all_sites as (
    select mode, 'All sites' as site_group_label, 0 as site_group_order, second,
           count(*) as visits,
           {{ median('cum_requests') }}  as median_cum_tracking_requests,
           {{ median('cum_companies') }} as median_cum_companies,
           avg(case when cum_requests > 0 then 1.0 else 0.0 end) as share_sites_tracking_started
    from cumulative group by mode, second
)

select * from by_group
union all
select * from all_sites
