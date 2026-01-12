from app import app
from flask import render_template
from flask import request
import csv
from datetime import datetime

Headers = ['transaction_id', 'timestamp', 'amount', 'category', 'status']

def valid_amount(value):
    try:
        float(value)
        return True
    except:
        return False
    
def valid_timestamp(time):
    try:
        datetime.fromisoformat(time)
        return True
    except:
        return False


@app.route("/", methods = ["GET", "POST"])
def index():
    if request.method == "POST":
        uploaded_csv = request.files.get("file")

        if uploaded_csv.filename == "":
            return "No File Input"
        
        if not uploaded_csv.filename.lower().endswith(".csv"):
            return "Invalid file type. Please upload a CSV file."


        ## Header Validation
        uploaded_csv.seek(0)

        raw_text = uploaded_csv.read().decode("utf-8", errors="replace")
        reader = csv.reader(raw_text.splitlines())

        csv_headers = next(reader, None)

        if csv_headers == ["\ufeff"]:
            return "Empty CSV file"
        
        missing_headers = set(Headers) - set(csv_headers)

        if missing_headers:
            return (
                "<pre>"
                f"Missing Required Columns: \n"
                f"{', '.join(missing_headers)}"
                "</pre>"
            )
        
        ## Row Validation

        uploaded_csv.seek(0)

        row_reader = csv.DictReader(raw_text.splitlines())

        valid_rows = []
        invalid_rows = []
        error_counts = {}

        for row in row_reader:
            errors = []

            #required fields
            for field in Headers:
                if not row.get(field):
                    errors.append(f"missing {field}")

            if row.get("amount") and not valid_amount(row["amount"]):
                errors.append("Invalid Amount")

            if row.get("timestamp") and not valid_timestamp(row["timestamp"]):
                errors.append("Invalid Timestamp")

            if errors:
                invalid_rows.append({
                    "row": row,
                    "errors": errors
                })

                for err in errors:
                    error_counts[err] = error_counts.get(err, 0) + 1
                

            else:
                valid_rows.append(row)

        total_rows = len(valid_rows) + len(invalid_rows)

        valid_pct = (
            round((len(valid_rows)/total_rows) * 100, 2) if total_rows > 0 else 0
        )

        # Row Aggregation

        status_counts = {}
        category_counts = {}
        total_amount = 0.0

        for row in valid_rows:
            total_amount += float(row["amount"])

        for row in valid_rows:
            category = row["category"]
            category_counts[category] = category_counts.get(category, 0) + 1

        for row in valid_rows:
            status = row["status"]
            status_counts[status] = status_counts.get(status, 0) + 1


        report = (
            "<pre>"
            f"Total Rows: {total_rows}\n"
            f"Valid Rows: {len(valid_rows)} \n"
            f"Invalid Rows: {len(invalid_rows)}\n"
            f"Valid %: {valid_pct}%\n\n"
            "Error Breakdown: \n"

        )

        for err, count in error_counts.items():
            report += f" - {err}: {count}\n"

        report += f"\nAGGREGATES (VALID ROWS ONLY)\n"
        report += f"----------------------------\n"
        report += f"Total Amount: {round(total_amount, 2)}\n\n"
        report += f"By Category:\n"

        for cat, count in category_counts.items():
            report += f" - {cat}: {count}\n"
        
        report += "\nBy Status:\n"

        for status, count in status_counts.items():
            report += f" - {status}: {count}\n"

        report += "</pre>"

        return report
        
    return render_template("base.html")

@app.route("/health")
def health():
    return "OK"

