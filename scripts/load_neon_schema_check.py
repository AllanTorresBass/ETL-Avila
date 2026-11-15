"""Verify Neon connectivity and avila schema presence."""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_load import load_env


def main() -> None:
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL missing")
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'avila' ORDER BY 1
                """
            )
            tables = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT count(*) FROM avila.account")
            accounts = cur.fetchone()[0]
    print("avila tables:", ", ".join(tables))
    print("accounts:", accounts)


if __name__ == "__main__":
    main()
