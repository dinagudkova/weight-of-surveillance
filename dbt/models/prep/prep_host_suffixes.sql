-- Every host with all its domain suffixes: a.b.example.com -> a.b.example.com, b.example.com, example.com.
-- Used to match hosts against domain lists (trackers, owners, consent platforms) with plain equality joins.
-- strpos/substr and recursive CTEs work the same in DuckDB and PostgreSQL.
with recursive hosts as (
    select host from {{ ref('stg_requests') }}
    union
    -- CNAME targets too, so a cloaked tracker can be attributed to its real owner
    select lower(cname_target) from {{ ref('stg_requests') }} where cname_target is not null
),

suffixes (host, suffix, lvl) as (
    select host, host, 0 from hosts
    union all
    select host, substr(suffix, strpos(suffix, '.') + 1), lvl + 1
    from suffixes
    where strpos(suffix, '.') > 0
)

select host, suffix, lvl
from suffixes
where strpos(suffix, '.') > 0
