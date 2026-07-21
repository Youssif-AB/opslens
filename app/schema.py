import csv
import io
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation


SCHEMA_VERSION = "transactions-v1"
REQUIRED_COLUMNS = ("transaction_id", "timestamp", "amount", "category", "status")
ALLOWED_CATEGORIES = frozenset({"Entertainment", "Food", "Rent", "Transport", "Utilities"})
ALLOWED_STATUSES = frozenset({"completed", "pending", "error"})


class FileValidationError(ValueError):
    """The CSV cannot be interpreted using the declared report schema."""


@dataclass(frozen=True)
class RejectedRecord:
    row_number: int
    row: dict
    reasons: tuple


@dataclass(frozen=True)
class ValidationReport:
    total_rows: int
    accepted: tuple
    rejected: tuple
    duplicate_rows: int
    failures: Counter

    @property
    def accepted_rows(self):
        return len(self.accepted)

    @property
    def rejected_rows(self):
        return len(self.rejected)


def _parse_timestamp(value):
    parsed = datetime.fromisoformat(value.replace(" ", "T"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed.isoformat(timespec="seconds")


def _validate_row(row, row_number, seen_ids):
    reasons = []
    normalized = {}
    for field in REQUIRED_COLUMNS:
        value = (row.get(field) or "").strip()
        if not value:
            reasons.append(("missing_value", field))
        normalized[field] = value

    transaction_id = normalized["transaction_id"]
    if transaction_id and transaction_id in seen_ids:
        reasons.append(("duplicate_identifier", "transaction_id"))
    if transaction_id:
        seen_ids.add(transaction_id)

    if normalized["timestamp"]:
        try:
            normalized["timestamp"] = _parse_timestamp(normalized["timestamp"])
        except (TypeError, ValueError):
            reasons.append(("invalid_type", "timestamp"))

    if normalized["amount"]:
        try:
            amount = Decimal(normalized["amount"])
            if not amount.is_finite():
                raise InvalidOperation
            if amount < 0:
                reasons.append(("out_of_range", "amount"))
            normalized["amount"] = float(amount)
        except (InvalidOperation, ValueError):
            reasons.append(("invalid_type", "amount"))

    if normalized["category"] and normalized["category"] not in ALLOWED_CATEGORIES:
        reasons.append(("invalid_category", "category"))
    normalized["status"] = normalized["status"].lower()
    if normalized["status"] and normalized["status"] not in ALLOWED_STATUSES:
        reasons.append(("invalid_status", "status"))
    if None in row:
        reasons.append(("malformed_row", None))

    normalized["source_row"] = row_number
    return normalized, tuple(dict.fromkeys(reasons))


def validate_csv(raw_bytes):
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise FileValidationError("CSV must be UTF-8 encoded") from error

    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = reader.fieldnames
        if not headers:
            raise FileValidationError("CSV is empty or has no header row")
        missing = sorted(set(REQUIRED_COLUMNS) - set(headers))
        unexpected = sorted(set(headers) - set(REQUIRED_COLUMNS))
        if missing or unexpected or len(headers) != len(set(headers)):
            details = []
            if missing:
                details.append(f"missing columns: {', '.join(missing)}")
            if unexpected:
                details.append(f"unexpected columns: {', '.join(unexpected)}")
            if len(headers) != len(set(headers)):
                details.append("duplicate column names")
            raise FileValidationError("Invalid header: " + "; ".join(details))

        accepted = []
        rejected = []
        failures = Counter()
        seen_ids = set()
        duplicate_rows = 0
        for row_number, row in enumerate(reader, start=2):
            normalized, reasons = _validate_row(row, row_number, seen_ids)
            if reasons:
                rejected.append(RejectedRecord(row_number, dict(row), reasons))
                failures.update(reasons)
                if ("duplicate_identifier", "transaction_id") in reasons:
                    duplicate_rows += 1
            else:
                accepted.append(normalized)
    except csv.Error as error:
        raise FileValidationError(f"Malformed CSV: {error}") from error

    return ValidationReport(
        total_rows=len(accepted) + len(rejected),
        accepted=tuple(accepted),
        rejected=tuple(rejected),
        duplicate_rows=duplicate_rows,
        failures=failures,
    )
