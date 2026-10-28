"""Run dbt with the project's profile and connection settings.

Usage:
  python scripts/dbt.py build                    # DuckDB (data/warehouse/wos.duckdb)
  python scripts/dbt.py build --target neon      # PostgreSQL on Neon, NEON_URL from .env
  python scripts/dbt.py docs generate

Reads NEON_URL from .env (or the environment) and passes host, user, password and database to dbt
as DBT_PG_* variables, so the password never has to be written into profiles.yml.
Timings of build/run/seed/test are appended to data/warehouse/dbt_log.csv for the DuckDB vs PostgreSQL comparison.
"""
import csv
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent


def read_env():
    env = ROOT / ".env"
    values = {}
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def main():
    args = sys.argv[1:]
    env = os.environ.copy()
    env.setdefault("DBT_PROFILES_DIR", str(ROOT / "dbt"))
    env.setdefault("DBT_DUCKDB_PATH", str(ROOT / "data" / "warehouse" / "wos.duckdb"))
    (ROOT / "data" / "warehouse").mkdir(parents=True, exist_ok=True)
    url = env.get("NEON_URL") or read_env().get("NEON_URL")
    if url:
        u = urlparse(url)
        env.setdefault("DBT_PG_HOST", u.hostname or "")
        env.setdefault("DBT_PG_PORT", str(u.port or 5432))
        env.setdefault("DBT_PG_USER", unquote(u.username or ""))
        env.setdefault("DBT_PG_PASSWORD", unquote(u.password or ""))
        env.setdefault("DBT_PG_DBNAME", u.path.lstrip("/") or "postgres")
        if "sslmode=disable" in (u.query or ""):
            env.setdefault("DBT_PG_SSLMODE", "disable")
    target = args[args.index("--target") + 1] if "--target" in args else "duckdb"
    t = time.perf_counter()
    code = subprocess.call(["dbt", *args], cwd=ROOT / "dbt", env=env)
    secs = time.perf_counter() - t
    if args and args[0] in ("build", "run", "seed", "test"):
        path = ROOT / "data" / "warehouse" / "dbt_log.csv"
        new = not path.exists()
        with open(path, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["ran_at", "target", "command", "seconds", "exit_code"])
            w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), target, " ".join(args), round(secs, 1), code])
    sys.exit(code)


if __name__ == "__main__":
    main()
