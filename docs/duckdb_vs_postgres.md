# DuckDB vs PostgreSQL

The pipeline runs on two engines with the same dbt project: **DuckDB** (a local file) for development and
analysis, **PostgreSQL** on **Neon** (managed cloud database, free plan, region `eu-central-1`) for the
Tableau dashboard. This page compares them on the final data of the study.

## How it was measured

`scripts/benchmark.py` runs the same steps on each target, on the same data (automated crawl, real-browser
crawl, TCF crawl; about 745,000 request rows):

1. load the raw tables from JSONL (`load/load_raw.py`),
2. full dbt build (`dbt build --full-refresh`: seeds, 5 views, 10 tables, 29 tests), three times,
3. four typical queries, each three times after one warm-up run,
4. storage size.

To separate the **engine** from the **network**, PostgreSQL was measured twice: on a local server
(PostgreSQL on the same MacBook) and on Neon (over a home internet connection). Values are medians of the
repeated runs, 2 November 2026.

## Results (seconds)

| Step | DuckDB (local) | PostgreSQL (local) | PostgreSQL (Neon) |
|---|---|---|---|
| Load real-browser crawl | 1.01 | 1.85 | 22.68 |
| Load automated crawl | 0.79 | 1.76 | 17.54 |
| Load TCF crawl | 0.03 | 0.05 | 0.83 |
| dbt build --full-refresh | 3.70 | 8.06 | 21.54 |
| Query: consent timeline (small mart) | <0.001 | <0.001 | 0.033 |
| Query: group medians (`fct_visits`) | 0.001 | 0.002 | 0.027 |
| Query: requests per host (scan of the raw request table) | 0.002 | 0.041 | 0.127 |
| Query: top companies (request level) | 0.006 | 0.584 | 0.689 |
| Storage | 316 MB (file) | 255 MB | 255 MB |

## What the numbers say

**Engine (DuckDB vs local PostgreSQL).** DuckDB loads and builds about twice as fast. On analytical queries
over many rows the gap is much larger: the raw scan is about 20× faster. DuckDB is a columnar engine that
reads only the columns a query needs and processes them in batches; PostgreSQL stores rows and is built for
many small transactions. On small marts both answer instantly.

**Network (local PostgreSQL vs Neon).** Loading is about 10× slower on Neon because every row travels over
the internet. The dbt build is about 2.7× slower: it sends many separate statements, and each one pays the
round trip. Small queries take 25–35 ms on Neon instead of under 2 ms — almost all of it network latency.
The heaviest query is close on both (0.58 vs 0.69 s), so there the database itself does the work.

**Caveats.**
- The "top companies" query reads `prep_requests_classified`, which is a **table in DuckDB but a view in
  PostgreSQL** (to save Neon storage). In PostgreSQL the whole classification runs inside the query, so most of
  its 100× gap comes from this design choice, not from the engine. The raw-scan query (a table in both) is the
  fair engine comparison.
- Storage is not like for like either: DuckDB keeps full URLs and the materialised classification table;
  the PostgreSQL copy keeps shortened URLs and builds the classification as a view.
- One machine, one network, three repeats: the numbers show orders of magnitude, not precise ratios.

## Beyond speed

| | DuckDB | PostgreSQL / Neon |
|---|---|---|
| Setup | a file, nothing to run | a server; Neon removes the administration |
| Loading JSONL | `read_json` reads the files directly | needs a loader (rows copied with `COPY` from Python) |
| Concurrency | one writer at a time; the file is locked while dbt builds | many users and tools at once |
| Tableau | no native connector | native connector, extracts for Tableau Public |
| Limits | disk space | Neon free plan: 0.5 GB storage (255 MB used), compute that suspends when idle (first query after a pause is slower) |
| Fit in this project | development, exploration, notebooks | serving the dashboard, sharing |

**SQL differences that had to be handled** (the dbt models are shared, so these are the places where the
dialects differ):
- median: `median(x)` in DuckDB, `percentile_cont(0.5) within group (order by x)` in PostgreSQL — solved
  with a dispatched macro (`dbt/macros/median.sql`);
- untyped string literals in a `union all` (dataset labels) need an explicit `cast(... as varchar)` in
  PostgreSQL;
- integer division: `/` is integer division in PostgreSQL but float division in DuckDB — written as
  `/ 1000.0` where it matters;
- boolean logic with NULLs behaves the same, but needed explicit `coalesce` in a few places to stay correct
  on both;
- optional raw tables are detected at run time with `adapter.get_relation`, which works on both adapters.

## Conclusion

For an analytical pipeline of this size, DuckDB is the faster and simpler engine: it reads the crawl files
directly, builds the whole project in seconds and answers analytical queries one to two orders of magnitude
faster than PostgreSQL. PostgreSQL earns its place at the end of the pipeline: it is the database the
dashboard tool connects to, it is shared and always on, and Neon makes that possible without running a
server. Most of Neon's extra time is the network, which matters for loading and building but not for a
Tableau extract. Using both — DuckDB to develop and analyse, PostgreSQL to serve — fits the project better
than either alone.
