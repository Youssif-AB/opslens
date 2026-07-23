import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import current_app, g


def connect_database(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def get_db():
    if "db" not in g:
        g.db = connect_database(current_app.config["DATABASE"])
    return g.db


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


@contextmanager
def transaction(connection, immediate=False):
    connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()


MIGRATIONS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS datasets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        filename TEXT NOT NULL,
        content_hash TEXT,
        schema_version TEXT NOT NULL DEFAULT 'transactions-v1',
        status TEXT NOT NULL DEFAULT 'completed',
        total_rows INTEGER NOT NULL DEFAULT 0,
        accepted_rows INTEGER NOT NULL DEFAULT 0,
        rejected_rows INTEGER NOT NULL DEFAULT 0,
        duplicate_rows INTEGER NOT NULL DEFAULT 0,
        uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT,
        CHECK (status IN ('processing', 'completed', 'failed'))
    );
    CREATE TABLE IF NOT EXISTS ingestion_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        dataset_id INTEGER REFERENCES datasets(id) ON DELETE SET NULL,
        filename TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        schema_version TEXT NOT NULL DEFAULT 'transactions-v1',
        raw_csv BLOB NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        total_rows INTEGER NOT NULL DEFAULT 0,
        accepted_rows INTEGER NOT NULL DEFAULT 0,
        rejected_rows INTEGER NOT NULL DEFAULT 0,
        duplicate_rows INTEGER NOT NULL DEFAULT 0,
        queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        started_at TEXT,
        completed_at TEXT,
        error_message TEXT,
        processing_ms INTEGER,
        worker_id TEXT,
        CHECK (status IN ('queued', 'processing', 'completed', 'failed'))
    );
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
        transaction_id TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        amount REAL NOT NULL,
        category TEXT NOT NULL,
        status TEXT NOT NULL,
        source_row INTEGER NOT NULL,
        UNIQUE (dataset_id, transaction_id)
    );
    CREATE TABLE IF NOT EXISTS validation_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL REFERENCES ingestion_jobs(id) ON DELETE CASCADE,
        rule TEXT NOT NULL,
        field TEXT,
        failure_count INTEGER NOT NULL,
        UNIQUE (job_id, rule, field)
    );
    CREATE TABLE IF NOT EXISTS rejected_rows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL REFERENCES ingestion_jobs(id) ON DELETE CASCADE,
        row_number INTEGER NOT NULL,
        row_data TEXT NOT NULL,
        reasons TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_datasets_user_uploaded ON datasets(user_id, uploaded_at DESC, id DESC);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_datasets_successful_hash ON datasets(user_id, content_hash)
        WHERE status = 'completed' AND content_hash IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_jobs_status_queued ON ingestion_jobs(status, queued_at, id);
    CREATE INDEX IF NOT EXISTS idx_jobs_user_queued ON ingestion_jobs(user_id, queued_at DESC, id DESC);
    CREATE INDEX IF NOT EXISTS idx_transactions_dataset_time ON transactions(dataset_id, occurred_at);
    CREATE INDEX IF NOT EXISTS idx_transactions_dataset_category ON transactions(dataset_id, category);
    """,
    """
    DROP INDEX IF EXISTS idx_transactions_dataset_category;
    CREATE INDEX IF NOT EXISTS idx_transactions_dataset_category_time
        ON transactions(dataset_id, category, occurred_at);
    CREATE INDEX IF NOT EXISTS idx_transactions_dataset_status
        ON transactions(dataset_id, status);
    """
]


def migrate(connection):
    connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
    for version, script in enumerate(MIGRATIONS, start=1):
        if version not in applied:
            existing = {row[1] for row in connection.execute("PRAGMA table_info(datasets)")}
            additions = {
                "content_hash": "TEXT",
                "schema_version": "TEXT NOT NULL DEFAULT 'transactions-v1'",
                "status": "TEXT NOT NULL DEFAULT 'completed'",
                "total_rows": "INTEGER NOT NULL DEFAULT 0",
                "accepted_rows": "INTEGER NOT NULL DEFAULT 0",
                "rejected_rows": "INTEGER NOT NULL DEFAULT 0",
                "duplicate_rows": "INTEGER NOT NULL DEFAULT 0",
                "completed_at": "TEXT",
            }
            for column, definition in additions.items():
                if existing and column not in existing:
                    connection.execute(f"ALTER TABLE datasets ADD COLUMN {column} {definition}")
            connection.executescript(script)
            connection.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)", (version,))


def init_db():
    migrate(get_db())


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
