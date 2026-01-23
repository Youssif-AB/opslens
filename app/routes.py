from app import app
from flask import render_template
from flask import request
import csv
from datetime import datetime
import math
from collections import defaultdict
from app.db import get_db
from flask import session
from flask import redirect



valid_rows = []
invalid_rows = []
error_counts = {}
total_rows = 0
valid_pct = 0
status_counts = {}
category_counts = {}
total_amount = 0.0

Headers = ['transaction_id', 'timestamp', 'amount', 'category', 'status']

def valid_amount(value):
    try:
        float(value)
        return True        
    except:
        return False
        
def valid_timestamp(time):
    try:
        datetime.fromisoformat(time.replace(" ", "T"))
        return True
    except:
        return False


@app.route("/", methods = ["GET", "POST"])
def index():
    if request.method == "POST":

        global valid_rows, invalid_rows, error_counts
        global total_rows, valid_pct, status_counts, category_counts, total_amount

        valid_rows = []
        invalid_rows = []
        error_counts = {}
        status_counts = {}
        category_counts = {}
        total_amount = 0.0

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

        for row in row_reader:
            errors = []

            #required fields
            for field in Headers:
                if not row.get(field):
                    errors.append(f"Missing {field}")

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


        for row in valid_rows:
            total_amount += float(row["amount"])

        for row in valid_rows:
            category = row["category"]
            category_counts[category] = category_counts.get(category, 0) + 1

        for row in valid_rows:
            status = row["status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        if "user_id" in session:
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO datasets (user_id, filename) VALUES (?, ?)",
                (session["user_id"], uploaded_csv.filename)
            )
            conn.commit()
            conn.close()


        return render_template(
            "dashboard.html",
            total_rows = total_rows,
            valid_rows = len(valid_rows),
            invalid_rows = len(invalid_rows),
            valid_pct = valid_pct,
            error_counts = error_counts,
            total_amount = round(total_amount,2),
            category_counts = category_counts,
            status_counts = status_counts
            )
        
    return render_template("upload.html")

@app.route("/dashboard")
def overview():
    return render_template(
            "dashboard.html",
            total_rows = total_rows,
            valid_rows = len(valid_rows),
            invalid_rows = len(invalid_rows),
            valid_pct = valid_pct,
            error_counts = error_counts,
            total_amount = round(total_amount,2),
            category_counts = category_counts,
            status_counts = status_counts
            )

@app.route("/analytics")
def analytics():
    avg_amount = (
        sum(float(r["amount"]) for r in valid_rows) / len(valid_rows)
        if valid_rows else 0
    )

    amounts = sorted(float(r["amount"]) for r in valid_rows)

    n = len(amounts)
    if n == 0:
        median_amount = 0
    elif n % 2 == 1:
        median_amount = amounts[n//2]
    else:
        median_amount = (amounts[n//2 - 1] + amounts[n//2]) / 2
    
    mean = avg_amount

    variance = (
        sum((float(r["amount"]) - mean) ** 2 for r in valid_rows) / len(valid_rows)
        if valid_rows else 0
        )
    
    std_dev_amount = math.sqrt(variance)

    cof_var = (std_dev_amount/avg_amount) * 100 if avg_amount != 0 else 0

    daily_counts = defaultdict(int)


    for row in valid_rows + [r["row"] for r in invalid_rows]:
        ts = row.get("timestamp")
        try:
            date = datetime.fromisoformat(ts.replace(" ", "T")).date()
            daily_counts[str(date)] += 1
        except:
            continue

    sorted_days = sorted(daily_counts.items())

    if not sorted_days:
        dates = []
        counts = []
    else:
        MAX_POINTS = len(sorted_days)
        if len(sorted_days) > MAX_POINTS:
            step = max(1, len(sorted_days) // MAX_POINTS)
            sampled = sorted_days[::step]
        else:
            sampled = sorted_days

        dates = [
            datetime.strptime(d, "%Y-%m-%d").strftime("%b %d")
            for d, _ in sampled
        ]
        counts = [c for _, c in sampled]


    buckets = {
        "<10":0,
        "10-50":0,
        "50-200":0,
        "200+":0
    }

    for r in valid_rows:
        amt = float(r["amount"])
        if amt < 10:
            buckets["<10"] += 1
        elif amt < 50:
            buckets["10-50"] +=1
        elif amt < 200:
            buckets["50-200"] += 1
        else:
            buckets["200+"] +=1

    category_amounts = {}

    for r in valid_rows:
        cat = r["category"]
        category_amounts[cat] = category_amounts.get(cat, 0) + float(r["amount"])

    status_by_category = {}

    for r in valid_rows:
        cat = r["category"]
        status = r["status"].strip().capitalize()

        if cat not in status_by_category:
            status_by_category[cat] = {
                "Completed": 0,
                "Pending": 0,
                "Error": 0
            }

        # guard in case status is unexpected
        if status in status_by_category[cat]:
            status_by_category[cat][status] += 1


    
    min_amount = min(amounts) if amounts else 0
    max_amount = max(amounts) if amounts else 0
    amount_range = max_amount - min_amount

    unique_categories = len(set(r["category"] for r in valid_rows))
    unique_statuses = len(set(r["status"] for r in valid_rows))

    return render_template(
        "analytics.html",
        avg_amount=round(avg_amount, 2),
        median_amount=round(median_amount, 2),
        std_dev_amount=round(std_dev_amount, 2),
        cof_var=round(cof_var, 2),
        dates= dates,
        daily_counts=counts,
        buckets=buckets,
        category_amounts=category_amounts,
        status_by_category=status_by_category,
        min_amount=min_amount,
        max_amount=max_amount,
        amount_range=amount_range,
        unique_categories=unique_categories,
        unique_statuses=unique_statuses
)

from flask import redirect, url_for

@app.route("/saved")
def saved():
    if "user_id" not in session:
        session["next"] = "/saved"
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT filename, uploaded_at
        FROM datasets
        WHERE user_id = ?
        ORDER BY uploaded_at DESC
        """,
        (session["user_id"],)
    )

    datasets = cur.fetchall()
    conn.close()

    return render_template("saved.html", datasets=datasets)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id from users where email = ?", (email, ))
        user = cur.fetchone()
        conn.close()

        if user:
            session["user_id"] = user["id"]
            
            next_page = request.args.get("next") or session.pop("next", "/")
            return redirect(next_page)
        
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        cur = conn.cursor()

        # check if user already exists
        cur.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        )
        existing = cur.fetchone()

        if existing:
            conn.close()
            return render_template(
                "register.html",
                error="Email already registered"
            )

        # create user (plain-text password, as requested)
        cur.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, password)
        )
        conn.commit()

        # log them in immediately
        user_id = cur.lastrowid
        conn.close()

        session["user_id"] = user_id

        next_page = session.pop("next", "/")
        return redirect(next_page)

    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/health")
def health():
    return "OK"

@app.context_processor
def inject_user():
    user = None

    if "user_id" in session:
        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "SELECT email FROM users WHERE id = ?",
            (session["user_id"],)
        )
        row = cur.fetchone()
        conn.close()

        if row:
            email = row["email"]
            user = {
                "email": email,
                "name": email[:4],
                "avatar": email[:2].upper()
            }

    return dict(current_user=user)