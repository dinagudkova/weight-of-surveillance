"""DuckDB vs PostgreSQL: the same pipeline on the same data, timed.

Usage:
  python scripts/benchmark.py                       # all targets found in .env: duckdb, local_pg, neon
  python scripts/benchmark.py --targets duckdb local_pg --repeats 3

Targets
  duckdb    a separate file data/warehouse/benchmark.duckdb (the main warehouse is not touched)
  local_pg  LOCAL_PG_URL in .env, e.g. postgresql://user@localhost:5432/wos_bench (an empty database)
  neon      NEON_URL in .env (reloads the same final data that is already there)

For every target the script (1) loads the raw tables (automated crawl, real-browser crawl, TCF crawl),
(2) runs a full dbt build, and (3) times a set of typical analytical queries, each `--repeats` times,
and records the storage size. Local PostgreSQL separates the engine difference (DuckDB vs PostgreSQL)
from the network difference (local vs cloud).

Results: data/warehouse/benchmark.csv (one row per measurement) and a summary printed at the end.
"""
import argparse
import csv
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "load"))
import load_raw  # noqa: E402

WAREHOUSE = ROOT / "data" / "warehouse"
BENCH_DUCKDB = WAREHOUSE / "benchmark.duckdb"
DATASETS = [  # (folder, dataset name in load_raw.py)
    ("data/raw/study_merged", "study"),
    ("data/raw/real_final", "real"),
    ("data/raw/tcf_merged", "tcf"),
]

QUERIES = {
    "group medians (fct_visits)": """
        select site_group_label, mode, count(*) as visits,
               percentile_cont(0.5) within group (order by tracking_requests) as median_tracking
        from marts.fct_visits where is_usable and dataset = 'real'
        group by 1, 2 order by 1, 2""",
    "top companies (request level)": """
        select owner, count(distinct site) as sites, count(*) as requests
        from prep.prep_requests_classified
        where dataset = 'real' and is_usable and is_tracking and mode = 'accept' and phase = 'window'
        group by owner order by sites desc limit 20""",
    "requests per host (raw scan)": """
        select host, count(*) as n, sum(bytes) as bytes
        from raw.real_requests group by host order by n desc limit 50""",
    "consent timeline (mart)": """
        select mode, second, median_cum_companies from marts.mart_consent_timeline
        where site_group_label = 'All sites' order by mode, second""",
}


def env_value(name):
    if os.environ.get(name):
        return os.environ[name]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def record(rows, target, step, seconds, extra=""):
    rows.append({"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "target": target,
                 "step": step, "seconds": round(seconds, 3), "extra": extra})
    print(f"  {target:<9} {step:<34} {seconds:8.2f} s {extra}")


def dbt_env(target, url):
    env = os.environ.copy()
    env["DBT_DUCKDB_PATH"] = str(BENCH_DUCKDB)
    if url:
        u = urlparse(url)
        env.update({"DBT_PG_HOST": u.hostname or "localhost", "DBT_PG_PORT": str(u.port or 5432),
                    "DBT_PG_USER": unquote(u.username or ""), "DBT_PG_PASSWORD": unquote(u.password or ""),
                    "DBT_PG_DBNAME": u.path.lstrip("/") or "postgres",
                    # sslmode from the URL if given, otherwise none for a local server and required for Neon
                    "DBT_PG_SSLMODE": dict(q.split("=", 1) for q in (u.query or "").split("&") if "=" in q).get(
                        "sslmode", "disable" if target == "local_pg" else "require")})
    return env


def run_target(target, url, repeats, rows):
    print(f"\n=== {target} ===")
    if target == "duckdb" and BENCH_DUCKDB.exists():
        BENCH_DUCKDB.unlink()

    # 1. load
    for folder, dataset in DATASETS:
        if not (ROOT / folder / "visits.jsonl").exists():
            print(f"  (skip {folder}: not found)")
            continue
        t = time.perf_counter()
        if target == "duckdb":
            load_raw.load_duckdb((ROOT / folder).resolve(), str(BENCH_DUCKDB), dataset)
        else:
            load_raw.load_postgres((ROOT / folder).resolve(), url, dataset)
        record(rows, target, f"load {dataset}", time.perf_counter() - t)

    # 2. dbt build (full refresh), repeated
    dbt_target = "duckdb" if target == "duckdb" else "neon"
    for i in range(repeats):
        t = time.perf_counter()
        code = subprocess.call(["dbt", "build", "--target", dbt_target, "--full-refresh", "--quiet"],
                               cwd=ROOT / "dbt", env={**dbt_env(target, url), "DBT_PROFILES_DIR": str(ROOT / "dbt")})
        record(rows, target, "dbt build --full-refresh", time.perf_counter() - t, f"run {i + 1}, exit {code}")
        if code != 0:
            print("  dbt build failed, stopping this target")
            return

    # 3. queries, repeated
    if target == "duckdb":
        con = duckdb.connect(str(BENCH_DUCKDB), read_only=True)
        run = lambda sql: con.execute(sql).fetchall()  # noqa: E731
        size = f"{BENCH_DUCKDB.stat().st_size / 1e6:.0f} MB file"
    else:
        import psycopg
        con = psycopg.connect(url)
        run = lambda sql: con.execute(sql).fetchall()  # noqa: E731
        size = con.execute("select pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]
    for name, sql in QUERIES.items():
        run(sql)  # warm-up, not recorded
        for i in range(repeats):
            t = time.perf_counter()
            run(sql)
            record(rows, target, f"query: {name}", time.perf_counter() - t, f"run {i + 1}")
    con.close()
    record(rows, target, "storage size", 0, size)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--targets", nargs="+", default=["duckdb", "local_pg", "neon"])
    p.add_argument("--repeats", type=int, default=3)
    args = p.parse_args()

    urls = {"duckdb": None, "local_pg": env_value("LOCAL_PG_URL"), "neon": env_value("NEON_URL")}
    rows = []
    for target in args.targets:
        if target != "duckdb" and not urls[target]:
            print(f"\n(skip {target}: {'LOCAL_PG_URL' if target == 'local_pg' else 'NEON_URL'} not set in .env)")
            continue
        run_target(target, urls[target], args.repeats, rows)

    WAREHOUSE.mkdir(parents=True, exist_ok=True)
    out = WAREHOUSE / "benchmark.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["run_at", "target", "step", "seconds", "extra"])
        w.writeheader()
        w.writerows(rows)

    print("\n=== summary: median seconds per step ===")
    steps = sorted({r["step"] for r in rows if r["step"] != "storage size"}, key=lambda s: (not s.startswith("load"), s))
    targets = [t for t in args.targets if any(r["target"] == t for r in rows)]
    print(f"{'step':<36}" + "".join(f"{t:>12}" for t in targets))
    for s in steps:
        cells = []
        for t in targets:
            v = [r["seconds"] for r in rows if r["target"] == t and r["step"] == s]
            cells.append(f"{statistics.median(v):12.3f}" if v else f"{'-':>12}")
        print(f"{s:<36}" + "".join(cells))
    for t in targets:
        size = next((r["extra"] for r in rows if r["target"] == t and r["step"] == "storage size"), "")
        print(f"storage {t}: {size}")
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
