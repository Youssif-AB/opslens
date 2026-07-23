from app.db import migrate


def test_migrations_are_idempotent(connection):
    migrate(connection)
    migrate(connection)
    assert [row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")] == [1, 2]
