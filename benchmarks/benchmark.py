import csv
import io
import json
import statistics
import tempfile
import time
from pathlib import Path

from app.db import connect_database, migrate, transaction
from app.ingestion import enqueue_job, process_job
from app.worker import claim_next_job

CATEGORIES = ("Entertainment", "Food", "Rent", "Transport", "Utilities")
STATUSES = ("completed", "pending", "error")


def csv_fixture(row_count, prefix="T"):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(("transaction_id", "timestamp", "amount", "category", "status"))
    for index in range(row_count):
        writer.writerow((f"{prefix}{index:07d}", f"2024-{index % 12 + 1:02d}-{index % 28 + 1:02d} 12:00:00",
                         f"{(index % 50000) / 100:.2f}", CATEGORIES[index % 5], STATUSES[index % 3]))
    return buffer.getvalue().encode()


def timed(callable_, repeats=25):
    # Warm filesystem/database caches so index-build activity and cold reads do not
    # dominate a small local latency measurement.
    for _ in range(10):
        list(callable_())
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        list(callable_())
        samples.append((time.perf_counter() - started) * 1000)
    samples.sort()
    return {"median_ms": round(statistics.median(samples), 3), "p95_ms": round(samples[int(len(samples) * .95) - 1], 3)}


def load(connection, raw_bytes, filename):
    job_id, _ = enqueue_job(connection, filename, raw_bytes)
    claimed = claim_next_job(connection, "benchmark")
    started = time.perf_counter()
    if claimed != job_id or not process_job(connection, job_id):
        raise RuntimeError("benchmark ingestion failed")
    return (time.perf_counter() - started) * 1000


def query_measurements(connection, dataset_id):
    queries = {
        "history_page": lambda: connection.execute(
            "SELECT id, filename, uploaded_at, total_rows FROM datasets WHERE user_id IS NULL ORDER BY uploaded_at DESC, id DESC LIMIT 20"),
        "time_range": lambda: connection.execute(
            "SELECT occurred_at, amount, category, status FROM transactions WHERE dataset_id = ? AND occurred_at BETWEEN ? AND ? ORDER BY occurred_at",
            (dataset_id, "2024-03-01", "2024-05-31T23:59:59")),
        "category_range": lambda: connection.execute(
            "SELECT occurred_at, amount, status FROM transactions WHERE dataset_id = ? AND category = ? ORDER BY occurred_at", (dataset_id, "Food")),
        "status_aggregate": lambda: connection.execute(
            "SELECT status, COUNT(*) FROM transactions WHERE dataset_id = ? GROUP BY status", (dataset_id,)),
    }
    return {name: timed(query) for name, query in queries.items()}


def benchmark():
    ingestion = {}
    for size in (1000, 5000, 10000):
        with tempfile.TemporaryDirectory() as directory:
            connection = connect_database(Path(directory) / "ingestion.db")
            migrate(connection)
            elapsed_ms = load(connection, csv_fixture(size), f"transactions-{size}.csv")
            ingestion[str(size)] = {"duration_ms": round(elapsed_ms, 2), "rows_per_second": round(size / (elapsed_ms / 1000), 1)}
            connection.close()

    with tempfile.TemporaryDirectory() as directory:
        connection = connect_database(Path(directory) / "queries.db")
        migrate(connection)
        for batch in range(10):
            load(connection, csv_fixture(10000, prefix=f"B{batch}-"), f"batch-{batch}.csv")
        dataset_id = connection.execute("SELECT MAX(id) FROM datasets").fetchone()[0]
        with transaction(connection, immediate=True):
            for index in ("idx_datasets_user_uploaded", "idx_transactions_dataset_time", "idx_transactions_dataset_category_time", "idx_transactions_dataset_status"):
                connection.execute(f"DROP INDEX {index}")
        before = query_measurements(connection, dataset_id)
        with transaction(connection, immediate=True):
            connection.execute("CREATE INDEX idx_datasets_user_uploaded ON datasets(user_id, uploaded_at DESC, id DESC)")
            connection.execute("CREATE INDEX idx_transactions_dataset_time ON transactions(dataset_id, occurred_at)")
            connection.execute("CREATE INDEX idx_transactions_dataset_category_time ON transactions(dataset_id, category, occurred_at)")
            connection.execute("CREATE INDEX idx_transactions_dataset_status ON transactions(dataset_id, status)")
        after = query_measurements(connection, dataset_id)
        connection.close()
    return {"fixture_rows": 100000, "repeats": 25, "queries": {"before_indexes": before, "after_indexes": after}, "ingestion": ingestion}


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2))
