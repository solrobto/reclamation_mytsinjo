import os
import ssl
import sqlite3
from config import DATABASE_PATH, DATABASE_URL

_USE_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")

if _USE_POSTGRES:
    import pg8000

def is_postgres():
    return _USE_POSTGRES

def _translate_params(sql):
    # Convert SQLite-style placeholders to psycopg2 style.
    return sql.replace("?", "%s") if _USE_POSTGRES else sql

class DBConn:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        if _USE_POSTGRES:
            cur = self.conn.cursor()
            cur.execute(_translate_params(sql), params or ())
            return PgCursor(cur)
        return self.conn.execute(sql, params or ())

    def executemany(self, sql, seq_of_params):
        if _USE_POSTGRES:
            cur = self.conn.cursor()
            cur.executemany(_translate_params(sql), seq_of_params)
            return PgCursor(cur)
        return self.conn.executemany(sql, seq_of_params)

    def executescript(self, script):
        if not _USE_POSTGRES:
            return self.conn.executescript(script)
        cur = self.conn.cursor()
        statements = [s.strip() for s in script.split(";") if s.strip()]
        for stmt in statements:
            cur.execute(stmt)
        return PgCursor(cur)

    def cursor(self):
        if _USE_POSTGRES:
            return PgCursor(self.conn.cursor())
        return self.conn.cursor()

    def commit(self):
        return self.conn.commit()

    def close(self):
        return self.conn.close()

def get_db():
    if _USE_POSTGRES:
        sslmode = os.getenv("DB_SSLMODE", "prefer").lower()
        ssl_context = None
        if sslmode in ["require", "verify-full", "verify-ca"]:
            ssl_context = ssl.create_default_context()
        conn = pg8000.connect(DATABASE_URL, ssl_context=ssl_context)
        return DBConn(conn)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return DBConn(conn)

class PgCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def description(self):
        return self._cursor.description

    def fetchone(self):
        row = self._cursor.fetchone()
        return _row_to_dict(self._cursor, row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [_row_to_dict(self._cursor, row) for row in rows]

    def fetchmany(self, size=None):
        rows = self._cursor.fetchmany(size)
        return [_row_to_dict(self._cursor, row) for row in rows]

    def __iter__(self):
        for row in self._cursor:
            yield _row_to_dict(self._cursor, row)

def _row_to_dict(cursor, row):
    if row is None:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))
