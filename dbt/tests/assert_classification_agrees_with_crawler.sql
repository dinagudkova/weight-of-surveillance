{{ config(severity='warn') }}
-- dbt and the crawler (classify.mjs) apply the same rules. Large disagreement means the seeds and the
-- lists used during the crawl differ (expected after list updates) or one implementation has a bug.
with cmp as (
    select
        count(*) as requests,
        count(*) filter (where is_tracking <> crawler_is_tracking) as disagree
    from {{ ref('prep_requests_classified') }}
)
select requests, disagree, 1.0 * disagree / requests as share
from cmp
where requests > 0 and 1.0 * disagree / requests > 0.02
