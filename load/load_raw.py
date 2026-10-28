"""Load crawl results (visits.jsonl, requests.jsonl) into raw tables in DuckDB and/or PostgreSQL (Neon).

Usage:
  python load/load_raw.py data/raw/study_merged                       # both targets
  python load/load_raw.py data/raw/study_merged --target duckdb
  python load/load_raw.py data/raw/study_merged --target postgres     # needs NEON_URL in .env

The raw tables are replaced on every run (full reload). DuckDB reads the JSONL files directly and flattens
them; the same flat rows are then copied into PostgreSQL. To fit the Neon free plan (0.5 GB), the Postgres
copy of the requests table drops query strings and keeps a shortened URL path.

Timings are appended to data/warehouse/load_log.csv for the DuckDB vs PostgreSQL comparison.
"""
import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
WAREHOUSE = ROOT / "data" / "warehouse"

# Cookie sync / ID matching, recognised by URL. Kept in sync with SYNC_RE in crawler/classify.mjs.
SYNC_PATTERN = (r"(//cm\.|usersync|user\.sync|user-sync|cookie[-_]?sync|cookiematch|cookie-match|/sync(\?|/|$)|/psync|"
                r"/cm(\?|/|$)|/match(\?|/|$)|\bmatch\.|/getuid|/setuid|piggyback|/rid\?|adscalematch|/tpui)")

VISITS_SQL = """
SELECT
    -- crash placeholder rows from older crawler versions have no visitId: derive a stable one
    COALESCE(visitId, 'crash-' || md5(concat_ws('|', site, mode, CAST(rep AS VARCHAR), date))) AS visit_id,
    site,
    category                                  AS crawl_category,
    mode,
    CAST(rep AS INTEGER)                      AS rep,
    CAST(date AS TIMESTAMP)                   AS visited_at,
    machine, shard, cpu, CAST(cores AS INTEGER) AS cores, platform, browserVersion AS browser_version,
    navError                                  AS nav_error,
    CAST(loadTimeout AS BOOLEAN)              AS load_timeout,
    CAST(mainStatus AS INTEGER)               AS main_status,
    finalUrl                                  AS final_url,
    CAST(botBlocked AS BOOLEAN)               AS bot_blocked,
    CAST(bannerPre AS BOOLEAN)                AS banner_pre,
    bannerText                                AS banner_text,
    CAST(payOrOkay AS BOOLEAN)                AS pay_or_okay,
    CAST(bannerEnd AS BOOLEAN)                AS banner_end,
    cmp,
    CAST(autoconsentDone AS BOOLEAN)          AS autoconsent_done,
    CAST(clicks AS INTEGER)                   AS clicks,
    CAST(consentAttempted AS BOOLEAN)         AS consent_attempted,
    consentMethod                             AS consent_method,
    fallbackLabel                             AS fallback_label,
    CAST(consentVerified AS BOOLEAN)          AS consent_verified,
    CAST(consentAt AS INTEGER)                AS consent_at_ms,
    CAST(t0 AS INTEGER)                       AS window_start_ms,
    CAST(windowMs AS INTEGER)                 AS window_ms,
    CAST(scriptMs AS INTEGER)                 AS script_ms,
    CAST(taskMs AS INTEGER)                   AS task_ms,
    CAST(cookiesPre.total AS INTEGER)         AS cookies_pre_total,
    CAST(cookiesPre.thirdParty AS INTEGER)    AS cookies_pre_third_party,
    CAST(cookiesPre.tracker AS INTEGER)       AS cookies_pre_tracker,
    array_to_string(cookiesPre.trackerOwners, ', ') AS cookies_pre_tracker_owners,
    CAST(cookiesEnd.total AS INTEGER)         AS cookies_end_total,
    CAST(cookiesEnd.thirdParty AS INTEGER)    AS cookies_end_third_party,
    CAST(cookiesEnd.tracker AS INTEGER)       AS cookies_end_tracker,
    array_to_string(cookiesEnd.trackerOwners, ', ') AS cookies_end_tracker_owners,
    CAST(requests AS INTEGER)                 AS request_count,
    CAST(COALESCE(requestsDropped, 0) AS INTEGER) AS requests_dropped,
    COALESCE(memoryAbort, false)              AS memory_abort
FROM read_json('{path}', format = 'newline_delimited', union_by_name = true, sample_size = -1, columns = {columns})
"""

# Explicit JSON schema: robust against older files where some keys are missing.
VISIT_COLUMNS = {
    "visitId": "VARCHAR", "site": "VARCHAR", "category": "VARCHAR", "mode": "VARCHAR", "rep": "BIGINT", "date": "VARCHAR",
    "machine": "VARCHAR", "shard": "VARCHAR", "cpu": "VARCHAR", "cores": "BIGINT", "platform": "VARCHAR",
    "browserVersion": "VARCHAR", "navError": "VARCHAR", "loadTimeout": "BOOLEAN", "mainStatus": "BIGINT",
    "finalUrl": "VARCHAR", "botBlocked": "BOOLEAN", "bannerPre": "BOOLEAN", "bannerText": "VARCHAR",
    "payOrOkay": "BOOLEAN", "bannerEnd": "BOOLEAN", "cmp": "VARCHAR", "autoconsentDone": "BOOLEAN", "clicks": "BIGINT",
    "consentAttempted": "BOOLEAN", "consentMethod": "VARCHAR", "fallbackLabel": "VARCHAR", "consentVerified": "BOOLEAN",
    "consentAt": "BIGINT", "t0": "BIGINT", "windowMs": "BIGINT", "scriptMs": "BIGINT", "taskMs": "BIGINT",
    "cookiesPre": "STRUCT(total BIGINT, thirdParty BIGINT, tracker BIGINT, trackerOwners VARCHAR[])",
    "cookiesEnd": "STRUCT(total BIGINT, thirdParty BIGINT, tracker BIGINT, trackerOwners VARCHAR[])",
    "requests": "BIGINT", "requestsDropped": "BIGINT", "memoryAbort": "BOOLEAN",
}
REQUEST_COLUMNS = {
    "visitId": "VARCHAR", "ts": "BIGINT", "phase": "VARCHAR", "url": "VARCHAR", "type": "VARCHAR", "status": "BIGINT",
    "mime": "VARCHAR", "failed": "BOOLEAN", "bytes": "BIGINT", "bodyBytes": "BIGINT", "upBytes": "BIGINT",
    "host": "VARCHAR", "regDomain": "VARCHAR", "category": "VARCHAR", "trackingType": "VARCHAR", "isTracking": "BOOLEAN",
    "viaCname": "BOOLEAN", "viaEasyPrivacy": "BOOLEAN", "viaEasyList": "BOOLEAN", "cname": "VARCHAR",
}

REQUESTS_SQL = """
SELECT
    visitId                                   AS visit_id,
    CAST(ts AS INTEGER)                       AS start_ms,
    phase,
    {url_expr}                                AS url,
    type                                      AS resource_type,
    CAST(status AS INTEGER)                   AS status,
    mime,
    COALESCE(failed, false)                   AS failed,
    CAST(COALESCE(bytes, 0) AS BIGINT)        AS bytes,
    CAST(COALESCE(bodyBytes, 0) AS BIGINT)    AS body_bytes,
    CAST(COALESCE(upBytes, 0) AS BIGINT)      AS upload_bytes,
    lower(host)                               AS host,
    lower(regDomain)                          AS reg_domain,
    COALESCE(viaEasyPrivacy, false)           AS via_easyprivacy,
    COALESCE(viaEasyList, false)              AS via_easylist,
    COALESCE(viaCname, false)                 AS via_cname,
    cname                                     AS cname_target,
    COALESCE(regexp_matches(url, '{sync}', 'i'), false) AS url_is_sync,
    category                                  AS crawler_category,
    trackingType                              AS crawler_tracking_type,
    COALESCE(isTracking, false)               AS crawler_is_tracking
FROM read_json('{path}', format = 'newline_delimited', union_by_name = true, sample_size = -1, columns = {columns})
"""

PG_TYPES = {"VARCHAR": "text", "INTEGER": "integer", "BIGINT": "bigint", "BOOLEAN": "boolean",
            "TIMESTAMP": "timestamp", "TIMESTAMP WITH TIME ZONE": "timestamptz", "DOUBLE": "double precision"}


def duck_columns(d):
    return "{" + ", ".join(f"'{k}': '{v}'" for k, v in d.items()) + "}"


def build_frames(con, folder, url_expr):
    visits = folder / "visits.jsonl"
    requests = folder / "requests.jsonl"
    if not visits.exists() or not requests.exists():
        sys.exit(f"{folder} must contain visits.jsonl and requests.jsonl")
    con.execute(f"CREATE OR REPLACE TEMP VIEW v_visits AS {VISITS_SQL.format(path=visits, columns=duck_columns(VISIT_COLUMNS))}")
    con.execute(f"CREATE OR REPLACE TEMP VIEW v_requests AS "
                f"{REQUESTS_SQL.format(path=requests, columns=duck_columns(REQUEST_COLUMNS), url_expr=url_expr, sync=SYNC_PATTERN)}")


def log(target, table, rows, seconds, folder):
    WAREHOUSE.mkdir(exist_ok=True)
    path = WAREHOUSE / "load_log.csv"
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["loaded_at", "target", "table", "rows", "seconds", "source"])
        w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), target, table, rows, round(seconds, 2), folder])


def load_duckdb(folder, db_path):
    WAREHOUSE.mkdir(exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    build_frames(con, folder, "url")
    for table in ["visits", "requests"]:
        t = time.perf_counter()
        con.execute(f"CREATE OR REPLACE TABLE raw.{table} AS SELECT * FROM v_{table}")
        n = con.execute(f"SELECT count(*) FROM raw.{table}").fetchone()[0]
        secs = time.perf_counter() - t
        log("duckdb", table, n, secs, folder)
        print(f"duckdb   raw.{table:<9} {n:>9} rows  {secs:6.1f} s")
    con.close()


def neon_url():
    url = os.environ.get("NEON_URL")
    env = ROOT / ".env"
    if not url and env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("NEON_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not url:
        sys.exit("NEON_URL is not set (add it to .env)")
    return url


def load_postgres(folder, url):
    import psycopg

    con = duckdb.connect()
    # Shorter URLs in Postgres: no query string, path cut to 200 characters (Neon free plan storage).
    build_frames(con, folder, "left(split_part(url, '?', 1), 200)")
    with psycopg.connect(url, autocommit=False) as pg:
        pg.execute("CREATE SCHEMA IF NOT EXISTS raw")
        for table in ["visits", "requests"]:
            t = time.perf_counter()
            desc = con.execute(f"DESCRIBE v_{table}").fetchall()
            cols = [(name, PG_TYPES.get(dtype, "text")) for name, dtype, *_ in desc]
            pg.execute(f"DROP TABLE IF EXISTS raw.{table} CASCADE")
            pg.execute(f"CREATE TABLE raw.{table} ({', '.join(f'{c} {t}' for c, t in cols)})")
            rel = con.execute(f"SELECT * FROM v_{table}")
            n = 0
            with pg.cursor().copy(f"COPY raw.{table} ({', '.join(c for c, _ in cols)}) FROM STDIN") as cp:
                while True:
                    batch = rel.fetchmany(10_000)
                    if not batch:
                        break
                    for row in batch:
                        cp.write_row(row)
                    n += len(batch)
            if table == "requests":
                pg.execute("CREATE INDEX ON raw.requests (visit_id)")
                pg.execute("CREATE INDEX ON raw.requests (host)")
            pg.commit()
            secs = time.perf_counter() - t
            log("postgres", table, n, secs, folder)
            print(f"postgres raw.{table:<9} {n:>9} rows  {secs:6.1f} s")
        size = pg.execute("SELECT pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]
        print(f"postgres database size: {size}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("folder", help="crawl results folder with visits.jsonl and requests.jsonl")
    p.add_argument("--target", choices=["duckdb", "postgres", "both"], default="both")
    p.add_argument("--duckdb-path", default=str(WAREHOUSE / "wos.duckdb"))
    args = p.parse_args()
    folder = Path(args.folder).resolve()
    if args.target in ("duckdb", "both"):
        load_duckdb(folder, args.duckdb_path)
    if args.target in ("postgres", "both"):
        load_postgres(folder, neon_url())


if __name__ == "__main__":
    main()
