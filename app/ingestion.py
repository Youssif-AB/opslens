import hashlib
import json
import logging
import time

from werkzeug.utils import secure_filename

from app.db import transaction
from app.schema import FileValidationError, SCHEMA_VERSION, validate_csv


logger = logging.getLogger("opslens.ingestion")


def content_hash(raw_bytes):
    return hashlib.sha256(raw_bytes).hexdigest()


def enqueue_job(connection, filename, raw_bytes, user_id=None):
    safe_name = secure_filename(filename or "")
    if not safe_name.lower().endswith(".csv"):
        raise FileValidationError("Only .csv files are accepted")
    if not raw_bytes:
        raise FileValidationError("CSV file is empty")
    digest = content_hash(raw_bytes)
    with transaction(connection, immediate=True):
        cursor = connection.execute(
            """
            INSERT INTO ingestion_jobs(user_id, filename, content_hash, schema_version, raw_csv)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, safe_name, digest, SCHEMA_VERSION, raw_bytes),
        )
    logger.info("ingestion_queued job_id=%s filename=%s", cursor.lastrowid, safe_name)
    return cursor.lastrowid, False


def persist_report(connection, job, report, rejected_sample_limit=25, fail_after_stage=False):
    with transaction(connection, immediate=True):
        cursor = connection.execute(
            """
            INSERT INTO datasets(
                user_id, filename, content_hash, schema_version, status, total_rows,
                accepted_rows, rejected_rows, duplicate_rows, completed_at
            ) VALUES (?, ?, ?, ?, 'completed', ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                job["user_id"], job["filename"], job["content_hash"], job["schema_version"],
                report.total_rows, report.accepted_rows, report.rejected_rows, report.duplicate_rows,
            ),
        )
        dataset_id = cursor.lastrowid
        connection.executemany(
            """
            INSERT INTO transactions(
                dataset_id, transaction_id, occurred_at, amount, category, status, source_row
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    dataset_id, row["transaction_id"], row["timestamp"], row["amount"],
                    row["category"], row["status"], row["source_row"],
                )
                for row in report.accepted
            ),
        )
        if fail_after_stage:
            raise RuntimeError("Injected failure after staging rows")
        connection.executemany(
            "INSERT INTO validation_results(job_id, rule, field, failure_count) VALUES (?, ?, ?, ?)",
            ((job["id"], rule, field, count) for (rule, field), count in report.failures.items()),
        )
        connection.executemany(
            "INSERT INTO rejected_rows(job_id, row_number, row_data, reasons) VALUES (?, ?, ?, ?)",
            (
                (
                    job["id"], item.row_number,
                    json.dumps(item.row, default=str, sort_keys=True),
                    json.dumps([{"rule": rule, "field": field} for rule, field in item.reasons]),
                )
                for item in report.rejected[:rejected_sample_limit]
            ),
        )
        connection.execute(
            """
            UPDATE ingestion_jobs
            SET dataset_id = ?, status = 'completed', total_rows = ?, accepted_rows = ?,
                rejected_rows = ?, duplicate_rows = ?, completed_at = CURRENT_TIMESTAMP,
                raw_csv = X''
            WHERE id = ? AND status = 'processing'
            """,
            (
                dataset_id, report.total_rows, report.accepted_rows,
                report.rejected_rows, report.duplicate_rows, job["id"],
            ),
        )
    return dataset_id


def process_job(connection, job_id, rejected_sample_limit=25, fail_after_stage=False):
    job = connection.execute("SELECT * FROM ingestion_jobs WHERE id = ?", (job_id,)).fetchone()
    if not job or job["status"] != "processing":
        return False
    started = time.perf_counter()
    try:
        report = validate_csv(bytes(job["raw_csv"]))
        dataset_id = persist_report(connection, job, report, rejected_sample_limit, fail_after_stage)
    except Exception as error:
        duration_ms = round((time.perf_counter() - started) * 1000)
        with transaction(connection, immediate=True):
            connection.execute(
                """
                UPDATE ingestion_jobs SET status = 'failed', completed_at = CURRENT_TIMESTAMP,
                    processing_ms = ?, error_message = ?, raw_csv = X''
                WHERE id = ? AND status = 'processing'
                """,
                (duration_ms, str(error)[:500], job_id),
            )
        logger.exception("ingestion_failed job_id=%s duration_ms=%s", job_id, duration_ms)
        return False
    duration_ms = round((time.perf_counter() - started) * 1000)
    connection.execute("UPDATE ingestion_jobs SET processing_ms = ? WHERE id = ?", (duration_ms, job_id))
    logger.info(
        "ingestion_completed job_id=%s dataset_id=%s duration_ms=%s accepted=%s rejected=%s duplicates=%s",
        job_id, dataset_id, duration_ms, report.accepted_rows, report.rejected_rows, report.duplicate_rows,
    )
    return True


def quality_report(connection, job_id):
    job = connection.execute(
        """
        SELECT id, dataset_id, filename, schema_version, status, total_rows, accepted_rows,
               rejected_rows, duplicate_rows, queued_at, started_at, completed_at,
               processing_ms, error_message
        FROM ingestion_jobs WHERE id = ?
        """,
        (job_id,),
    ).fetchone()
    if not job:
        return None
    failures = connection.execute(
        "SELECT rule, field, failure_count FROM validation_results WHERE job_id = ? ORDER BY failure_count DESC, rule, field",
        (job_id,),
    ).fetchall()
    rejected = connection.execute(
        "SELECT row_number, row_data, reasons FROM rejected_rows WHERE job_id = ? ORDER BY row_number",
        (job_id,),
    ).fetchall()
    return {"job": job, "failures": failures, "rejected_sample": rejected}
