from app.ingestion import enqueue_job, process_job, quality_report
from app.worker import claim_next_job


def run_queued(connection, job_id, fail_after_stage=False):
    assert claim_next_job(connection, "test-worker") == job_id
    return process_job(connection, job_id, fail_after_stage=fail_after_stage)


def test_successful_job_persists_rows_and_quality(connection, valid_csv):
    job_id, duplicate = enqueue_job(connection, "safe report.csv", valid_csv)
    assert not duplicate
    assert run_queued(connection, job_id)
    report = quality_report(connection, job_id)
    assert report["job"]["status"] == "completed"
    assert report["job"]["accepted_rows"] == 2
    assert connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 2
    assert report["job"]["raw_csv"] if "raw_csv" in report["job"].keys() else True


def test_data_quality_counts_and_sample_are_persisted(connection):
    raw = (b"transaction_id,timestamp,amount,category,status\n"
           b"T1,2024-01-01,1,Food,completed\nT2,bad,nope,,pending\n")
    job_id, _ = enqueue_job(connection, "mixed.csv", raw)
    assert run_queued(connection, job_id)
    report = quality_report(connection, job_id)
    assert (report["job"]["total_rows"], report["job"]["accepted_rows"], report["job"]["rejected_rows"]) == (2, 1, 1)
    assert len(report["rejected_sample"]) == 1
    assert {(row["rule"], row["field"]): row["failure_count"] for row in report["failures"]}[("invalid_type", "amount")] == 1


def test_duplicate_upload_returns_existing_successful_job(connection, valid_csv):
    first, _ = enqueue_job(connection, "first.csv", valid_csv)
    assert run_queued(connection, first)
    second, duplicate = enqueue_job(connection, "renamed.csv", valid_csv)
    assert duplicate and second == first
    assert connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 1


def test_transaction_failure_rolls_back_dataset_and_marks_job_failed(connection, valid_csv):
    job_id, _ = enqueue_job(connection, "rollback.csv", valid_csv)
    assert not run_queued(connection, job_id, fail_after_stage=True)
    assert connection.execute("SELECT status FROM ingestion_jobs WHERE id = ?", (job_id,)).fetchone()[0] == "failed"
    assert connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0


def test_file_validation_failure_marks_job_failed(connection):
    job_id, _ = enqueue_job(connection, "bad.csv", b"wrong,header\n1,2\n")
    assert not run_queued(connection, job_id)
    row = connection.execute("SELECT status, error_message FROM ingestion_jobs WHERE id = ?", (job_id,)).fetchone()
    assert row["status"] == "failed"
    assert "Invalid header" in row["error_message"]


def test_job_can_only_be_claimed_once(connection, valid_csv):
    job_id, _ = enqueue_job(connection, "once.csv", valid_csv)
    assert claim_next_job(connection, "worker-one") == job_id
    assert claim_next_job(connection, "worker-two") is None
