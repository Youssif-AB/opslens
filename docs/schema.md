# Transaction report schema

Schema version: `transactions-v1`

The header must contain exactly these columns, in any order:

| Column | Type | Rules |
| --- | --- | --- |
| `transaction_id` | text | Required, non-blank, unique within the file and dataset |
| `timestamp` | ISO 8601 date/time | Required; timezone input is normalized to a timezone-free ISO value |
| `amount` | decimal number | Required, finite, and greater than or equal to zero |
| `category` | category | Required: `Entertainment`, `Food`, `Rent`, `Transport`, or `Utilities` |
| `status` | category | Required: `completed`, `pending`, or `error` (case-insensitive input) |

The file must be UTF-8 (a UTF-8 BOM is accepted). Missing, unexpected, or duplicate header names fail the job. Row-level errors quarantine that row while valid rows load. Failure summaries distinguish `missing_value`, `invalid_type`, `out_of_range`, `invalid_category`, `invalid_status`, `duplicate_identifier`, and `malformed_row`.
