import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path


CATEGORIES = ("Food", "Rent", "Transport", "Utilities", "Entertainment")
STATUSES = ("completed", "pending", "error")


def generate(output, rows, seed):
    randomizer = random.Random(seed)
    start = datetime(2024, 1, 1, 8, 0)

    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("transaction_id", "timestamp", "amount", "category", "status"))

        for index in range(1, rows + 1):
            transaction_id = f"T{index:07d}"
            timestamp = (start + timedelta(minutes=index * 17)).isoformat(sep=" ")
            amount = f"{randomizer.uniform(1, 750):.2f}"
            category = randomizer.choice(CATEGORIES)
            status = randomizer.choice(STATUSES)

            # Deterministic mixed-quality cases; some rows intentionally have
            # more than one validation failure.
            if index % 41 == 0:
                status = ""
            if index % 67 == 0:
                category = ""
            if index % 89 == 0:
                timestamp = "not-a-timestamp"
            if index % 101 == 0:
                amount = "invalid-amount"
            if index % 173 == 0:
                transaction_id = ""
            if index % 211 == 0:
                transaction_id = f"T{index - 1:07d}"

            writer.writerow((transaction_id, timestamp, amount, category, status))


def main():
    parser = argparse.ArgumentParser(description="Generate a mixed-quality OpsLens CSV fixture")
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--output", type=Path, default=Path("opslens_10000_transactions_mixed.csv"))
    args = parser.parse_args()
    if args.rows < 1:
        parser.error("--rows must be positive")
    generate(args.output, args.rows, args.seed)
    print(f"Generated {args.rows:,} rows at {args.output.resolve()}")


if __name__ == "__main__":
    main()
