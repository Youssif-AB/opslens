import pytest

from app.schema import FileValidationError, validate_csv


def test_valid_report(valid_csv):
    report = validate_csv(valid_csv)
    assert (report.total_rows, report.accepted_rows, report.rejected_rows) == (2, 2, 0)


def test_missing_and_unexpected_columns_are_file_errors():
    with pytest.raises(FileValidationError, match="missing columns: status"):
        validate_csv(b"transaction_id,timestamp,amount,category,extra\nT1,2024-01-01,1,Food,x\n")


def test_invalid_types_missing_values_and_duplicates_are_counted():
    raw = (b"transaction_id,timestamp,amount,category,status\n"
           b"T1,bad,nope,,completed\nT1,2024-01-01,1,Food,pending\n")
    report = validate_csv(raw)
    assert report.rejected_rows == 2
    assert report.duplicate_rows == 1
    assert report.failures[("invalid_type", "timestamp")] == 1
    assert report.failures[("invalid_type", "amount")] == 1
    assert report.failures[("missing_value", "category")] == 1


def test_malformed_row_is_rejected():
    raw = (b"transaction_id,timestamp,amount,category,status\n"
           b"T1,2024-01-01,1,Food,completed,unexpected\n")
    report = validate_csv(raw)
    assert report.failures[("malformed_row", None)] == 1
