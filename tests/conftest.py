import pytest

from app import create_app
from app.db import get_db


@pytest.fixture
def app(tmp_path):
    application = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.db"), "SECRET_KEY": "test"})
    yield application


@pytest.fixture
def connection(app):
    with app.app_context():
        yield get_db()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def valid_csv():
    return (
        b"transaction_id,timestamp,amount,category,status\n"
        b"T1,2024-01-01 10:00:00,10.50,Food,completed\n"
        b"T2,2024-01-02 10:00:00,20.00,Rent,pending\n"
    )
