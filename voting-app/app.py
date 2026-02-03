from flask import Flask, render_template, request, redirect, session, url_for
import csv
import os
from datetime import datetime
from algorithms import calculate_all_results
import secrets

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

# ============== VOTING ROUTES ==============



# ============== HOME ==============

@app.route("/")
def home():
    return redirect(url_for("admin_login"))

# ============== RUN ==============

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
