import argparse
import logging
import os
import socket
import time

from app import create_app
from app.db import get_db, transaction
from app.ingestion import process_job


logger = logging.getLogger("opslens.worker")


def worker_identity():
    return f"{socket.gethostname()}:{os.getpid()}"


def recover_stale_jobs(connection, stale_minutes=30):
    with transaction(connection, immediate=True):
        cursor = connection.execute(
            """
            UPDATE ingestion_jobs
            SET status = 'queued', started_at = NULL, worker_id = NULL,
                error_message = 'Recovered after worker timeout'
            WHERE status = 'processing'
              AND started_at < datetime('now', ?)
            """,
            (f"-{int(stale_minutes)} minutes",),
        )
    if cursor.rowcount:
        logger.warning("stale_jobs_recovered count=%s", cursor.rowcount)
    return cursor.rowcount


def claim_next_job(connection, worker_id=None):
    worker_id = worker_id or worker_identity()
    with transaction(connection, immediate=True):
        queued = connection.execute(
            "SELECT id FROM ingestion_jobs WHERE status = 'queued' ORDER BY queued_at, id LIMIT 1"
        ).fetchone()
        if not queued:
            return None
        cursor = connection.execute(
            """
            UPDATE ingestion_jobs
            SET status = 'processing', started_at = CURRENT_TIMESTAMP, worker_id = ?
            WHERE id = ? AND status = 'queued'
            """,
            (worker_id, queued["id"]),
        )
        if cursor.rowcount != 1:
            return None
    logger.info("ingestion_claimed job_id=%s worker_id=%s", queued["id"], worker_id)
    return queued["id"]


def run_once(app):
    with app.app_context():
        connection = get_db()
        job_id = claim_next_job(connection)
        if job_id is None:
            return False
        process_job(
            connection,
            job_id,
            rejected_sample_limit=app.config["REJECTED_ROW_SAMPLE_LIMIT"],
        )
        return True


def run_worker(app, poll_seconds=1.0):
    with app.app_context():
        recover_stale_jobs(get_db())
    logger.info("worker_started worker_id=%s", worker_identity())
    while True:
        if not run_once(app):
            time.sleep(poll_seconds)


def main():
    parser = argparse.ArgumentParser(description="Process queued OpsLens ingestion jobs")
    parser.add_argument("--once", action="store_true", help="process at most one queued job")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = create_app()
    if args.once:
        run_once(app)
    else:
        run_worker(app, args.poll_seconds)


if __name__ == "__main__":
    main()
