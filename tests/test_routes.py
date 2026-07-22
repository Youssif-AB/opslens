import io

from app.db import get_db, transaction
from app.worker import run_once


def test_upload_queues_job_and_status_api_updates(app, client, valid_csv):
    response = client.post("/", data={"file": (io.BytesIO(valid_csv), "report.csv")}, content_type="multipart/form-data")
    assert response.status_code == 302
    assert "/jobs/" in response.location
    assert run_once(app)
    status = client.get(response.location.replace("?duplicate=0", "").replace("http://localhost", "/").replace("//jobs", "/jobs"))
    assert status.status_code == 200
    assert b"completed" in status.data


def test_upload_rejects_non_csv(client):
    response = client.post("/", data={"file": (io.BytesIO(b"text"), "report.txt")}, content_type="multipart/form-data")
    assert response.status_code == 200
    assert b"Only .csv files" in response.data


def test_health_and_readiness(client):
    assert client.get("/health").json == {"status": "ok"}
    assert client.get("/ready").json == {"status": "ready"}


def test_saved_reports_are_paginated(app, client):
    client.post("/register", data={"email": "user@example.com", "password": "password123"})
    with app.app_context():
        with transaction(get_db(), immediate=True):
            for index in range(3):
                get_db().execute("INSERT INTO datasets(user_id, filename, status) VALUES (1, ?, 'completed')", (f"report-{index}.csv",))
    first = client.get("/saved?per_page=2")
    second = client.get("/saved?per_page=2&page=2")
    assert first.data.count(b"dataset-card") == 2
    assert second.data.count(b"dataset-card") == 1


def test_registration_hashes_password(app, client):
    client.post("/register", data={"email": "secure@example.com", "password": "password123"})
    with app.app_context():
        stored = get_db().execute("SELECT password_hash FROM users WHERE email = 'secure@example.com'").fetchone()[0]
    assert stored != "password123"
    assert client.post("/login", data={"email": "secure@example.com", "password": "password123"}).status_code == 302
