import os
import sqlite3
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, g

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "smart-queue-demo-secret")
DB_PATH = os.path.join(os.path.dirname(__file__), "queue.db")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

ACTIVE_STATUSES = ("waiting", "called", "serving")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            avg_minutes INTEGER NOT NULL DEFAULT 10
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            service_id INTEGER NOT NULL,
            appointment_date TEXT NOT NULL,
            appointment_time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'waiting',
            created_at TEXT NOT NULL,
            called_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            notes TEXT,
            FOREIGN KEY(service_id) REFERENCES services(id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_daily_token
        ON appointments(appointment_date, token);
        """
    )
    count = db.execute("SELECT COUNT(*) FROM services").fetchone()[0]
    if count == 0:
        db.executemany(
            "INSERT INTO services(name, avg_minutes) VALUES (?, ?)",
            [
                ("General Enquiry", 8),
                ("Document Verification", 12),
                ("Payment / Billing", 10),
                ("Technical Support", 15),
            ],
        )
    db.commit()
    db.close()


def generate_token(appointment_date):
    db = get_db()
    row = db.execute(
        "SELECT token FROM appointments WHERE appointment_date=? ORDER BY id DESC LIMIT 1",
        (appointment_date,),
    ).fetchone()
    next_num = 1
    if row:
        try:
            next_num = int(row["token"].replace("Q", "")) + 1
        except ValueError:
            next_num += 1
    return f"Q{next_num:03d}"


def appointment_with_service(appointment_id):
    return get_db().execute(
        """
        SELECT a.*, s.name AS service_name, s.avg_minutes
        FROM appointments a
        JOIN services s ON s.id=a.service_id
        WHERE a.id=?
        """,
        (appointment_id,),
    ).fetchone()


def queue_metrics(appt):
    if not appt:
        return {"position": None, "people_ahead": None, "estimated_wait": None}
    if appt["status"] not in ACTIVE_STATUSES:
        return {"position": 0, "people_ahead": 0, "estimated_wait": 0}

    rows = get_db().execute(
        """
        SELECT a.id, a.created_at
        FROM appointments a
        WHERE a.appointment_date=?
          AND a.status IN ('waiting','called','serving')
        ORDER BY a.created_at ASC, a.id ASC
        """,
        (appt["appointment_date"],),
    ).fetchall()
    ids = [r["id"] for r in rows]
    try:
        pos = ids.index(appt["id"]) + 1
    except ValueError:
        pos = 0
    ahead = max(pos - 1, 0)
    return {
        "position": pos,
        "people_ahead": ahead,
        "estimated_wait": ahead * appt["avg_minutes"],
    }


def admin_required():
    return session.get("admin_logged_in") is True


@app.route("/")
def index():
    today = date.today().isoformat()
    db = get_db()
    counts = {
        "waiting": db.execute("SELECT COUNT(*) FROM appointments WHERE appointment_date=? AND status='waiting'", (today,)).fetchone()[0],
        "serving": db.execute("SELECT COUNT(*) FROM appointments WHERE appointment_date=? AND status='serving'", (today,)).fetchone()[0],
        "completed": db.execute("SELECT COUNT(*) FROM appointments WHERE appointment_date=? AND status='completed'", (today,)).fetchone()[0],
    }
    current = db.execute(
        """
        SELECT a.token, s.name AS service_name
        FROM appointments a JOIN services s ON s.id=a.service_id
        WHERE a.appointment_date=? AND a.status='serving'
        ORDER BY a.started_at DESC LIMIT 1
        """,
        (today,),
    ).fetchone()
    return render_template("index.html", counts=counts, current=current)


@app.route("/book", methods=["GET", "POST"])
def book():
    db = get_db()
    services = db.execute("SELECT * FROM services ORDER BY name").fetchall()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        service_id = request.form.get("service_id", "").strip()
        appt_date = request.form.get("appointment_date", "").strip()
        appt_time = request.form.get("appointment_time", "").strip()

        if not all([name, phone, service_id, appt_date, appt_time]):
            flash("Please fill all required fields.", "danger")
            return render_template("book.html", services=services, today=date.today().isoformat())
        try:
            selected_date = datetime.strptime(appt_date, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid appointment date.", "danger")
            return render_template("book.html", services=services, today=date.today().isoformat())
        if selected_date < date.today():
            flash("Appointment date cannot be in the past.", "danger")
            return render_template("book.html", services=services, today=date.today().isoformat())

        token = generate_token(appt_date)
        created = datetime.now().isoformat(timespec="seconds")
        cur = db.execute(
            """
            INSERT INTO appointments
            (token, customer_name, phone, email, service_id, appointment_date, appointment_time, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'waiting', ?)
            """,
            (token, name, phone, email, service_id, appt_date, appt_time, created),
        )
        db.commit()
        return redirect(url_for("ticket", appointment_id=cur.lastrowid))

    return render_template("book.html", services=services, today=date.today().isoformat())


@app.route("/ticket/<int:appointment_id>")
def ticket(appointment_id):
    appt = appointment_with_service(appointment_id)
    if not appt:
        return "Appointment not found", 404
    metrics = queue_metrics(appt)
    return render_template("ticket.html", appt=appt, metrics=metrics)


@app.route("/track", methods=["GET", "POST"])
def track():
    appt = None
    metrics = None
    query = ""
    if request.method == "POST":
        query = request.form.get("token", "").strip().upper()
        appt = get_db().execute(
            """
            SELECT a.*, s.name AS service_name, s.avg_minutes
            FROM appointments a JOIN services s ON s.id=a.service_id
            WHERE a.token=?
            ORDER BY a.appointment_date DESC, a.id DESC LIMIT 1
            """,
            (query,),
        ).fetchone()
        if appt:
            metrics = queue_metrics(appt)
        else:
            flash("Token not found.", "warning")
    return render_template("track.html", appt=appt, metrics=metrics, query=query)


@app.route("/queue")
def queue_board():
    today = date.today().isoformat()
    rows = get_db().execute(
        """
        SELECT a.id, a.token, a.status, a.appointment_time, s.name AS service_name
        FROM appointments a JOIN services s ON s.id=a.service_id
        WHERE a.appointment_date=? AND a.status IN ('waiting','called','serving')
        ORDER BY CASE a.status WHEN 'serving' THEN 0 WHEN 'called' THEN 1 ELSE 2 END,
                 a.created_at ASC
        """,
        (today,),
    ).fetchall()
    return render_template("queue.html", rows=rows, today=today)


@app.route("/api/queue")
def api_queue():
    today = date.today().isoformat()
    rows = get_db().execute(
        """
        SELECT a.id, a.token, a.status, a.appointment_time, s.name AS service_name
        FROM appointments a JOIN services s ON s.id=a.service_id
        WHERE a.appointment_date=? AND a.status IN ('waiting','called','serving')
        ORDER BY CASE a.status WHEN 'serving' THEN 0 WHEN 'called' THEN 1 ELSE 2 END,
                 a.created_at ASC
        """,
        (today,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/status/<int:appointment_id>")
def api_status(appointment_id):
    appt = appointment_with_service(appointment_id)
    if not appt:
        return jsonify({"error": "not found"}), 404
    data = dict(appt)
    data.update(queue_metrics(appt))
    return jsonify(data)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect admin password.", "danger")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
def admin_dashboard():
    if not admin_required():
        return redirect(url_for("admin_login"))
    today = date.today().isoformat()
    rows = get_db().execute(
        """
        SELECT a.*, s.name AS service_name
        FROM appointments a JOIN services s ON s.id=a.service_id
        WHERE a.appointment_date=?
        ORDER BY a.created_at ASC
        """,
        (today,),
    ).fetchall()
    summary = {}
    for status in ["waiting", "called", "serving", "completed", "skipped", "cancelled"]:
        summary[status] = sum(1 for r in rows if r["status"] == status)
    return render_template("admin.html", rows=rows, summary=summary, today=today)


@app.post("/admin/call-next")
def admin_call_next():
    if not admin_required():
        return redirect(url_for("admin_login"))
    db = get_db()
    today = date.today().isoformat()
    existing = db.execute(
        "SELECT id FROM appointments WHERE appointment_date=? AND status='called' LIMIT 1", (today,)
    ).fetchone()
    if existing:
        flash("A token is already called. Start or skip it first.", "warning")
        return redirect(url_for("admin_dashboard"))
    row = db.execute(
        """
        SELECT id FROM appointments
        WHERE appointment_date=? AND status='waiting'
        ORDER BY created_at ASC, id ASC LIMIT 1
        """,
        (today,),
    ).fetchone()
    if not row:
        flash("No waiting tokens.", "info")
    else:
        db.execute(
            "UPDATE appointments SET status='called', called_at=? WHERE id=?",
            (datetime.now().isoformat(timespec="seconds"), row["id"]),
        )
        db.commit()
        flash("Next token called.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/status/<int:appointment_id>/<status>")
def admin_status(appointment_id, status):
    if not admin_required():
        return redirect(url_for("admin_login"))
    allowed = {"waiting", "called", "serving", "completed", "skipped", "cancelled"}
    if status not in allowed:
        return "Invalid status", 400
    db = get_db()
    now = datetime.now().isoformat(timespec="seconds")
    fields = {"called": "called_at", "serving": "started_at", "completed": "completed_at"}
    if status in fields:
        db.execute(f"UPDATE appointments SET status=?, {fields[status]}=? WHERE id=?", (status, now, appointment_id))
    else:
        db.execute("UPDATE appointments SET status=? WHERE id=?", (status, appointment_id))
    db.commit()
    flash(f"Token updated to {status}.", "success")
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
else:
    init_db()
