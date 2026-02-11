import os
import sqlite3
from pathlib import Path

import os
import ssl
import pg8000

from models import init_db

ROOT = Path(__file__).resolve().parent
SQLITE_PATH = ROOT / "reclamation.db"

TABLE_ORDER = [
    "bureaux",
    "users",
    "types_reclamation",
    "reclamations",
    "pieces_jointes",
    "historique_statut",
]

def _pg_connect():
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set.")
    sslmode = os.getenv("DB_SSLMODE", "prefer").lower()
    ssl_context = None
    if sslmode in ["require", "verify-full", "verify-ca"]:
        ssl_context = ssl.create_default_context()
    return pg8000.connect(db_url, ssl_context=ssl_context)

def _sqlite_connect():
    if not SQLITE_PATH.exists():
        raise RuntimeError(f"SQLite DB not found at {SQLITE_PATH}")
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _sqlite_columns(cur, table):
    cols = cur.execute(f"PRAGMA table_info({table})").fetchall()
    return [c["name"] for c in cols]

def _copy_table(sqlite_conn, pg_conn, table):
    sqlite_cur = sqlite_conn.cursor()
    cols = _sqlite_columns(sqlite_cur, table)
    if not cols:
        return
    rows = sqlite_cur.execute(
        f"SELECT {', '.join(cols)} FROM {table}"
    ).fetchall()

    if not rows:
        return

    pg_cur = pg_conn.cursor()
    placeholders = ", ".join(["%s"] * len(cols))
    col_list = ", ".join(cols)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
    values = [tuple(row[col] for col in cols) for row in rows]
    pg_cur.executemany(sql, values)

def _reset_sequences(pg_conn):
    cur = pg_conn.cursor()
    for table in TABLE_ORDER:
        cur.execute(
            f"""
            SELECT setval(
                pg_get_serial_sequence(%s, 'id'),
                GREATEST((SELECT COALESCE(MAX(id), 1) FROM {table}), 1),
                true
            )
            """,
            (table,),
        )

def migrate():
    # Ensure Postgres schema exists
    init_db()

    sqlite_conn = _sqlite_connect()
    pg_conn = _pg_connect()
    pg_conn.autocommit = False

    try:
        pg_cur = pg_conn.cursor()
        pg_cur.execute(
            """
            TRUNCATE TABLE
                pieces_jointes,
                historique_statut,
                reclamations,
                types_reclamation,
                users,
                bureaux
            RESTART IDENTITY CASCADE
            """
        )

        for table in TABLE_ORDER:
            _copy_table(sqlite_conn, pg_conn, table)

        _reset_sequences(pg_conn)
        pg_conn.commit()
    except Exception:
        pg_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()

if __name__ == "__main__":
    migrate()
    print("Migration complete.")
