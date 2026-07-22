import math
from collections import defaultdict

from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import get_db, transaction
from app.ingestion import enqueue_job, quality_report
from app.schema import FileValidationError

bp = Blueprint("main", __name__)


def current_user_id():
    return session.get("user_id")


def accessible_job(job_id):
    job = get_db().execute("SELECT * FROM ingestion_jobs WHERE id = ? AND user_id IS ?", (job_id, current_user_id())).fetchone()
    if not job or (current_user_id() is None and session.get("last_job_id") != job_id):
        abort(404)
    return job


def accessible_dataset(dataset_id):
    dataset = get_db().execute(
        "SELECT * FROM datasets WHERE id = ? AND user_id IS ? AND status = 'completed'", (dataset_id, current_user_id())
    ).fetchone()
    if not dataset:
        abort(404)
    return dataset


@bp.route("/", methods=["GET", "POST"])
def index():
    error = None
    if request.method == "POST":
        upload = request.files.get("file")
        if not upload or not upload.filename:
            error = "Choose a CSV file to upload."
        else:
            try:
                job_id, duplicate = enqueue_job(get_db(), upload.filename, upload.read(), current_user_id())
            except FileValidationError as exc:
                error = str(exc)
            else:
                session["last_job_id"] = job_id
                return redirect(url_for("main.job_status", job_id=job_id, duplicate=int(duplicate)))
    return render_template("upload.html", error=error)


@bp.route("/jobs/<int:job_id>")
def job_status(job_id):
    accessible_job(job_id)
    return render_template("ingestion.html", report=quality_report(get_db(), job_id), duplicate=request.args.get("duplicate") == "1")


@bp.route("/api/jobs/<int:job_id>")
def job_status_api(job_id):
    accessible_job(job_id)
    job = dict(quality_report(get_db(), job_id)["job"])
    job["result_url"] = url_for("main.overview", dataset_id=job["dataset_id"]) if job["dataset_id"] else None
    return jsonify(job)


def dashboard_data(dataset_id):
    connection = get_db()
    dataset = accessible_dataset(dataset_id)
    status_counts = {row[0]: row[1] for row in connection.execute(
        "SELECT status, COUNT(*) FROM transactions WHERE dataset_id = ? GROUP BY status", (dataset_id,)
    )}
    category_counts = {row[0]: row[1] for row in connection.execute(
        "SELECT category, COUNT(*) FROM transactions WHERE dataset_id = ? GROUP BY category", (dataset_id,)
    )}
    total_amount = connection.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE dataset_id = ?", (dataset_id,)).fetchone()[0]
    failures = connection.execute(
        """SELECT vr.rule || CASE WHEN vr.field IS NULL THEN '' ELSE ': ' || vr.field END, vr.failure_count
           FROM validation_results vr JOIN ingestion_jobs j ON j.id = vr.job_id
           WHERE j.dataset_id = ? ORDER BY vr.failure_count DESC""", (dataset_id,)
    ).fetchall()
    return dict(dataset=dataset, total_rows=dataset["total_rows"], valid_rows=dataset["accepted_rows"],
                invalid_rows=dataset["rejected_rows"],
                valid_pct=round(dataset["accepted_rows"] * 100 / dataset["total_rows"], 2) if dataset["total_rows"] else 0,
                error_counts={row[0]: row[1] for row in failures}, total_amount=round(total_amount, 2),
                category_counts=category_counts, status_counts=status_counts)


@bp.route("/dashboard")
def overview():
    dataset_id = request.args.get("dataset_id", type=int) or session.get("active_dataset_id")
    if not dataset_id:
        return redirect(url_for("main.index"))
    session["active_dataset_id"] = dataset_id
    return render_template("dashboard.html", **dashboard_data(dataset_id))


@bp.route("/analytics")
def analytics():
    dataset_id = request.args.get("dataset_id", type=int) or session.get("active_dataset_id")
    if not dataset_id:
        return redirect(url_for("main.index"))
    accessible_dataset(dataset_id)
    rows = get_db().execute(
        "SELECT occurred_at, amount, category, status FROM transactions WHERE dataset_id = ? ORDER BY occurred_at", (dataset_id,)
    ).fetchall()
    amounts = sorted(row["amount"] for row in rows)
    count = len(amounts)
    average = sum(amounts) / count if count else 0
    median = amounts[count // 2] if count % 2 else ((amounts[count // 2 - 1] + amounts[count // 2]) / 2 if count else 0)
    variance = sum((amount - average) ** 2 for amount in amounts) / count if count else 0
    daily, category_amounts = defaultdict(int), defaultdict(float)
    status_by_category = defaultdict(lambda: {"Completed": 0, "Pending": 0, "Error": 0})
    buckets = {"<10": 0, "10-50": 0, "50-200": 0, "200+": 0}
    for row in rows:
        daily[row["occurred_at"][:10]] += 1
        category_amounts[row["category"]] += row["amount"]
        status_by_category[row["category"]][row["status"].capitalize()] += 1
        key = "<10" if row["amount"] < 10 else "10-50" if row["amount"] < 50 else "50-200" if row["amount"] < 200 else "200+"
        buckets[key] += 1
    return render_template("analytics.html", avg_amount=round(average, 2), median_amount=round(median, 2),
        std_dev_amount=round(math.sqrt(variance), 2), cof_var=round(math.sqrt(variance) / average * 100, 2) if average else 0,
        dates=list(daily), daily_counts=list(daily.values()), buckets=buckets, category_amounts=dict(category_amounts),
        status_by_category=dict(status_by_category), min_amount=min(amounts) if amounts else 0,
        max_amount=max(amounts) if amounts else 0, amount_range=(max(amounts) - min(amounts)) if amounts else 0,
        unique_categories=len(category_amounts), unique_statuses=len({row["status"] for row in rows}))


@bp.route("/saved")
def saved():
    if not current_user_id():
        session["next"] = url_for("main.saved")
        return redirect(url_for("main.login"))
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 20, type=int), 1), 100)
    datasets = get_db().execute(
        """SELECT id, filename, uploaded_at, total_rows, accepted_rows, rejected_rows FROM datasets
           WHERE user_id = ? AND status = 'completed' ORDER BY uploaded_at DESC, id DESC LIMIT ? OFFSET ?""",
        (current_user_id(), per_page + 1, (page - 1) * per_page)).fetchall()
    return render_template("saved.html", datasets=datasets[:per_page], page=page, has_next=len(datasets) > per_page)


@bp.route("/saved/upload", methods=["POST"])
def uploaded_saved():
    if not current_user_id():
        return redirect(url_for("main.login"))
    return index()


@bp.route("/open/<int:dataset_id>")
def open_dataset(dataset_id):
    accessible_dataset(dataset_id)
    session["active_dataset_id"] = dataset_id
    return redirect(url_for("main.overview"))


@bp.route("/delete/<int:dataset_id>", methods=["POST"])
def delete_dataset(dataset_id):
    if not current_user_id():
        return redirect(url_for("main.login"))
    with transaction(get_db(), immediate=True):
        get_db().execute("DELETE FROM datasets WHERE id = ? AND user_id = ?", (dataset_id, current_user_id()))
    return redirect(url_for("main.saved"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = get_db().execute("SELECT id, password_hash FROM users WHERE email = ?", (request.form["email"].strip().lower(),)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session.clear(); session["user_id"] = user["id"]
            return redirect(request.args.get("next") or url_for("main.index"))
        error = "Invalid email or password"
    return render_template("login.html", error=error)


@bp.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        email, password = request.form["email"].strip().lower(), request.form["password"]
        if len(password) < 8:
            error = "Password must be at least 8 characters"
        else:
            try:
                with transaction(get_db(), immediate=True):
                    cursor = get_db().execute("INSERT INTO users(email, password_hash) VALUES (?, ?)", (email, generate_password_hash(password)))
            except Exception:
                error = "Email already registered"
            else:
                session.clear(); session["user_id"] = cursor.lastrowid
                return redirect(url_for("main.index"))
    return render_template("register.html", error=error)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("main.index"))


@bp.route("/health")
def health():
    return jsonify(status="ok")


@bp.route("/ready")
def ready():
    try:
        get_db().execute("SELECT 1").fetchone()
    except Exception:
        return jsonify(status="not_ready"), 503
    return jsonify(status="ready")


@bp.app_context_processor
def inject_user():
    user = None
    if current_user_id():
        row = get_db().execute("SELECT email FROM users WHERE id = ?", (current_user_id(),)).fetchone()
        if row:
            user = {"email": row["email"], "name": row["email"].split("@")[0], "avatar": row["email"][:2].upper()}
    return {"current_user": user}
