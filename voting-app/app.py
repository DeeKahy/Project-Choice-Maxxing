import csv
import os
import secrets
from datetime import datetime

from algorithms import calculate_all_results
from flask import Flask, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

DATA_DIR = "data"
ADMIN_USER = "admin"
ADMIN_PASS = "admin"

os.makedirs(DATA_DIR, exist_ok=True) # i sweat to god if you delete this i will delete your first born child

# ============== CSV GARBAGE ==============

def read_csv(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def write_csv(filepath, rows, fieldnames):
    """Write list of dicts to CSV"""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def append_csv(filepath, row, fieldnames):
    """Append single row to CSV, create if needed"""
    file_exists = os.path.exists(filepath)
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


# ============== POLL GARBAGE ==============

def get_polls():
    return read_csv(f"{DATA_DIR}/polls.csv")

def get_poll(poll_id):
    polls = get_polls()
    return next((p for p in polls if p["id"] == poll_id), None)

def get_options(poll_id):
    return read_csv(f"{DATA_DIR}/options_{poll_id}.csv")

def get_votes(poll_id):
    return read_csv(f"{DATA_DIR}/votes_{poll_id}.csv")

def save_polls(polls):
    write_csv(f"{DATA_DIR}/polls.csv", polls,
              ["id", "title", "description", "created_at", "is_open", "max_score"])

def generate_id():
    return secrets.token_urlsafe(6)

# ============== YOUR SECURITY NIGHTMARE ==============

def is_admin():
    return session.get("admin") == True

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if (request.form["username"] == ADMIN_USER and
            request.form["password"] == ADMIN_PASS):
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error="Invalid credentials")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))

# ============== "SECURE" ROUTES ==============

@app.route("/admin/dashboard")
def admin_dashboard():
    if not is_admin():
        return redirect(url_for("admin_login"))
    polls = get_polls()
    return render_template("admin_dashboard.html", polls=polls)

@app.route("/admin/create", methods=["GET", "POST"])
def admin_create():
    if not is_admin():
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        poll_id = generate_id()
        poll = {
            "id": poll_id,
            "title": request.form["title"],
            "description": request.form.get("description", ""),
            "created_at": datetime.now().isoformat(),
            "is_open": "true",
            "max_score": request.form.get("max_score", "5")
        }
        append_csv(f"{DATA_DIR}/polls.csv", poll,
                   ["id", "title", "description", "created_at", "is_open", "max_score"])

        # Save options
        options = request.form.getlist("options")
        option_rows = [{"id": i+1, "name": opt, "description": ""}
                       for i, opt in enumerate(options) if opt.strip()]
        write_csv(f"{DATA_DIR}/options_{poll_id}.csv", option_rows,
                  ["id", "name", "description"])

        return redirect(url_for("admin_poll", poll_id=poll_id))

    return render_template("admin_create.html")

@app.route("/admin/poll/<poll_id>")
def admin_poll(poll_id):
    if not is_admin():
        return redirect(url_for("admin_login"))

    poll = get_poll(poll_id)
    if not poll:
        return "Poll not found", 404

    options = get_options(poll_id)
    votes = get_votes(poll_id)

    # Calculate results using all methods
    results = calculate_all_results(votes, options, int(poll.get("max_score", 5)))

    return render_template("admin_poll.html",
                          poll=poll, options=options, votes=votes, results=results)

@app.route("/admin/poll/<poll_id>/delete_vote/<username>", methods=["POST"])
def delete_vote(poll_id, username):
    if not is_admin():
        return redirect(url_for("admin_login"))

    votes = get_votes(poll_id)
    votes = [v for v in votes if v["username"] != username]

    options = get_options(poll_id)
    fieldnames = ["username", "submitted_at"] + [f"option_{o['id']}" for o in options]
    write_csv(f"{DATA_DIR}/votes_{poll_id}.csv", votes, fieldnames)

    return redirect(url_for("admin_poll", poll_id=poll_id))

@app.route("/admin/poll/<poll_id>/delete", methods=["POST"])
def delete_poll(poll_id):
    if not is_admin():
        return redirect(url_for("admin_login"))

    # Remove poll from polls.csv
    polls = get_polls()
    polls = [p for p in polls if p["id"] != poll_id]
    save_polls(polls)

    # Delete associated files
    options_file = f"{DATA_DIR}/options_{poll_id}.csv"
    votes_file = f"{DATA_DIR}/votes_{poll_id}.csv"
    if os.path.exists(options_file):
        os.remove(options_file)
    if os.path.exists(votes_file):
        os.remove(votes_file)

    return redirect(url_for("admin_dashboard"))

# ============== VOTING ROUTES ==============



# ============== HOME ==============

@app.route("/")
def home():
    return redirect(url_for("admin_login"))

# ============== RUN ==============

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
