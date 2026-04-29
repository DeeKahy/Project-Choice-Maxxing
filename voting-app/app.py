import csv
import os
import secrets
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from algorithms import calculate_all_results
from flask import Flask, abort, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

DATA_DIR = "data"
# ADMIN_USER / ADMIN_PASS are now ONLY the bootstrap credentials used the
# first time the app starts with no users in users.csv. After that, real
# accounts live in data/users.csv with hashed passwords. Override via
# FLASK_ADMIN_USER / FLASK_ADMIN_PASS env vars when seeding.
ADMIN_USER = os.environ.get("FLASK_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("FLASK_ADMIN_PASS", "admin")

# Change directory to the one this file is in so DATA_DIR resolves correctly
# regardless of where the process was launched from.
os.chdir(Path(__file__).resolve().parent)
print(f"Current working directory:\n{os.getcwd()}")

os.makedirs(
    DATA_DIR, exist_ok=True
)  # i sweat to god if you delete this i will delete your first born child


# Persist the Flask secret key across restarts so logged-in admins don't get
# kicked out every time the process bounces. Priority:
#   1. FLASK_SECRET_KEY env var (recommended for production)
#   2. data/.secret_key file (auto-generated on first boot)
#   3. ephemeral random bytes (only as a last-resort fallback)
def _load_or_create_secret_key():
    env_key = os.environ.get("FLASK_SECRET_KEY")
    if env_key:
        return env_key.encode("utf-8")
    key_path = Path(DATA_DIR) / ".secret_key"
    if key_path.exists():
        return key_path.read_bytes()
    new_key = secrets.token_bytes(32)
    try:
        key_path.write_bytes(new_key)
        os.chmod(key_path, 0o600)
    except OSError as e:
        print(f"⚠️  Could not persist secret key to {key_path}: {e}")
    return new_key


app.secret_key = _load_or_create_secret_key()


# ============== CSRF PROTECTION ==============
#
# Rolling our own (rather than pulling in Flask-WTF) keeps the dependency
# list short. Each session gets a random token; every state-changing form
# must echo it back in a hidden `csrf_token` field, and every non-safe
# request is rejected with 400 if the token doesn't match.


def _get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


@app.context_processor
def _inject_csrf_token():
    """Make `csrf_token()` callable inside Jinja templates."""
    return {"csrf_token": _get_csrf_token}


_CSRF_EXEMPT_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.before_request
def _csrf_protect():
    if request.method in _CSRF_EXEMPT_METHODS:
        return
    # Tests use Flask's test client and bypass forms entirely. Keep them
    # focused on behaviour, not on token plumbing — the dedicated CSRF
    # tests below flip TESTING off to verify the real-world behaviour.
    if app.config.get("TESTING"):
        return
    submitted = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not expected or not secrets.compare_digest(expected, submitted):
        abort(400, description="CSRF token missing or invalid")

# ============== CSV GARBAGE ==============

# A re-entrant lock that serializes ALL CSV access so the read-modify-write
# patterns in the routes (e.g. "load polls, mutate, save_polls") aren't
# interleaved with concurrent voters or admins. This is a single-process
# lock — multi-worker deployments would also need fcntl/flock — but it
# matches the default Flask development server and the docker single-worker
# CMD line. RLock so a route can hold the lock across nested helper calls.
_csv_lock = threading.RLock()


@contextmanager
def csv_lock():
    """Acquire the global CSV lock. Use around any read-modify-write
    sequence that spans more than one helper call."""
    with _csv_lock:
        yield


def read_csv(filepath):
    with _csv_lock:
        if not os.path.exists(filepath):
            return []
        with open(filepath, "r", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))


def write_csv(filepath, rows, fieldnames):
    """Write list of dicts to CSV.

    `restval=""` fills in missing keys with empty strings (helpful when
    adding new columns to existing files); `extrasaction="ignore"` silently
    drops keys that aren't in `fieldnames` so a stale row dict doesn't blow
    up the writer.
    """
    with _csv_lock:
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=fieldnames, restval="", extrasaction="ignore"
            )
            writer.writeheader()
            writer.writerows(rows)


def append_csv(filepath, row, fieldnames):
    """Append single row to CSV, create if needed."""
    with _csv_lock:
        file_exists = os.path.exists(filepath)
        with open(filepath, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=fieldnames, restval="", extrasaction="ignore"
            )
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)


# ============== POLL GARBAGE ==============

# polls.csv schema. `owner` is the username of the account that created the
# poll; older rows from before this column existed will round-trip with
# owner="" (and are visible to admins only).
POLLS_FIELDS = [
    "id",
    "title",
    "description",
    "created_at",
    "is_open",
    "max_score",
    "owner",
]

# Each non-admin account is capped at this many polls. Admins are exempt.
# Override with the MAX_POLLS_PER_USER env var.
try:
    MAX_POLLS_PER_USER = max(1, int(os.environ.get("MAX_POLLS_PER_USER", "50")))
except ValueError:
    MAX_POLLS_PER_USER = 50


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
    write_csv(f"{DATA_DIR}/polls.csv", polls, POLLS_FIELDS)


def generate_id():
    return secrets.token_urlsafe(6)


def user_poll_count(username):
    """Return how many polls a given user owns. Used to enforce the
    MAX_POLLS_PER_USER limit on non-admin accounts."""
    if not username:
        return 0
    return sum(1 for p in get_polls() if p.get("owner") == username)


# ============== USERS ==============

USERS_FIELDS = ["username", "password_hash", "is_admin", "created_at"]


def _users_path():
    return f"{DATA_DIR}/users.csv"


def get_users():
    return read_csv(_users_path())


def get_user(username):
    if not username:
        return None
    return next((u for u in get_users() if u["username"] == username), None)


def save_users(users):
    write_csv(_users_path(), users, USERS_FIELDS)


def add_user(username, password, is_admin_flag=False):
    """Append a new user. Returns True on success, False if the username
    is already taken (callers should validate format/length first)."""
    with csv_lock():
        users = get_users()
        if any(u["username"] == username for u in users):
            return False
        users.append(
            {
                "username": username,
                "password_hash": generate_password_hash(password),
                "is_admin": "true" if is_admin_flag else "false",
                "created_at": datetime.now().isoformat(),
            }
        )
        save_users(users)
        return True


def seed_first_admin():
    """If users.csv is empty, create a starter admin so the app is usable
    out of the box. The credentials come from FLASK_ADMIN_USER /
    FLASK_ADMIN_PASS env vars (defaulting to admin/admin) — print a loud
    warning so operators know to change them."""
    if get_users():
        return
    add_user(ADMIN_USER, ADMIN_PASS, is_admin_flag=True)
    if ADMIN_PASS == "admin":
        print(
            "⚠️  Seeded initial admin with default password 'admin'. "
            "Log in and change it immediately, or set FLASK_ADMIN_PASS before first launch."
        )
    else:
        print(f"✅  Seeded initial admin '{ADMIN_USER}' from FLASK_ADMIN_PASS env var.")


seed_first_admin()


# ============== AUTH ==============


def current_user():
    return get_user(session.get("admin_username"))


def is_admin():
    user = current_user()
    return bool(user and user.get("is_admin") == "true")


def is_logged_in():
    return current_user() is not None


def can_manage_poll(poll, user=None):
    """Admins can manage anything; regular users can manage polls they own."""
    if user is None:
        user = current_user()
    if not user or not poll:
        return False
    if user.get("is_admin") == "true":
        return True
    return poll.get("owner") == user.get("username")


def _username_is_valid(username):
    """Allow alphanumerics + underscore + hyphen, length 1-32."""
    if not username or len(username) > 32:
        return False
    return all(c.isalnum() or c in "_-" for c in username)


MIN_PASSWORD_LEN = 4


@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    """Any user (admin or not) can log in here; admin-only features still
    gate on `is_admin()` further down. The route is named `admin_login`
    for backward compatibility with existing URL references."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_user(username)
        if user and check_password_hash(user.get("password_hash", ""), password):
            session.clear()
            session["admin_username"] = username
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error="Invalid credentials")
    return render_template("admin_login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    """Public self-service signup. Creates a non-admin account and logs the
    new user straight in. Validation matches `admin_users_create` so admins
    and self-signups go through the same rules."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        error = None
        if not _username_is_valid(username):
            error = "Username must be 1-32 alphanumeric characters (underscore/hyphen allowed)."
        elif len(password) < MIN_PASSWORD_LEN:
            error = f"Password must be at least {MIN_PASSWORD_LEN} characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif get_user(username):
            error = "Username already taken."

        if error:
            return render_template(
                "signup.html", error=error, form_username=username
            )

        add_user(username, password, is_admin_flag=False)
        session.clear()
        session["admin_username"] = username
        return redirect(url_for("admin_dashboard"))

    return render_template("signup.html", form_username="")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


# ============== USER MANAGEMENT ROUTES ==============


@app.route("/admin/users")
def admin_users():
    if not is_admin():
        return redirect(url_for("admin_login"))
    users = get_users()
    # Don't leak hashes into the template context.
    safe_users = [
        {k: v for k, v in u.items() if k != "password_hash"} for u in users
    ]
    return render_template(
        "admin_users.html", users=safe_users, current=current_user()
    )


@app.route("/admin/users/create", methods=["GET", "POST"])
def admin_users_create():
    if not is_admin():
        return redirect(url_for("admin_login"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        is_admin_flag = request.form.get("is_admin") == "on"

        error = None
        if not _username_is_valid(username):
            error = "Username must be 1-32 alphanumeric characters (underscore/hyphen allowed)."
        elif len(password) < MIN_PASSWORD_LEN:
            error = f"Password must be at least {MIN_PASSWORD_LEN} characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif get_user(username):
            error = "Username already taken."

        if error:
            return render_template(
                "admin_user_create.html",
                error=error,
                form_username=username,
                form_is_admin=is_admin_flag,
            )

        add_user(username, password, is_admin_flag=is_admin_flag)
        return redirect(url_for("admin_users"))
    return render_template(
        "admin_user_create.html", form_username="", form_is_admin=False
    )


@app.route("/admin/users/<username>/delete", methods=["POST"])
def admin_users_delete(username):
    if not is_admin():
        return redirect(url_for("admin_login"))
    if username == session.get("admin_username"):
        # Refuse to lock yourself out.
        return redirect(url_for("admin_users"))
    with csv_lock():
        users = [u for u in get_users() if u["username"] != username]
        # Refuse to delete the last admin so the system can't be orphaned.
        if not any(u.get("is_admin") == "true" for u in users):
            return redirect(url_for("admin_users"))
        save_users(users)
    return redirect(url_for("admin_users"))


@app.route("/admin/change-password", methods=["GET", "POST"])
def admin_change_password():
    if not is_admin():
        return redirect(url_for("admin_login"))
    user = current_user()
    if request.method == "POST":
        old = request.form.get("old_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        error = None
        if not check_password_hash(user["password_hash"], old):
            error = "Current password is incorrect."
        elif len(new) < MIN_PASSWORD_LEN:
            error = f"New password must be at least {MIN_PASSWORD_LEN} characters."
        elif new != confirm:
            error = "New passwords do not match."

        if error:
            return render_template("admin_change_password.html", error=error)

        with csv_lock():
            users = get_users()
            for u in users:
                if u["username"] == user["username"]:
                    u["password_hash"] = generate_password_hash(new)
            save_users(users)
        return render_template(
            "admin_change_password.html", success="Password updated."
        )
    return render_template("admin_change_password.html")


# ============== "SECURE" ROUTES ==============


@app.route("/admin/dashboard")
def admin_dashboard():
    user = current_user()
    if not user:
        return redirect(url_for("admin_login"))
    polls = get_polls()
    if user.get("is_admin") != "true":
        # Regular users see only the polls they created.
        polls = [p for p in polls if p.get("owner") == user["username"]]
    return render_template(
        "admin_dashboard.html",
        polls=polls,
        current=user,
        is_admin=user.get("is_admin") == "true",
        poll_count=len(polls),
        poll_limit=MAX_POLLS_PER_USER,
        at_limit=(
            user.get("is_admin") != "true" and len(polls) >= MAX_POLLS_PER_USER
        ),
    )


ALLOWED_MAX_SCORES = {"3", "5", "10"}
MAX_TITLE_LEN = 200
MAX_DESCRIPTION_LEN = 1000
MAX_OPTION_LEN = 200
MAX_OPTIONS = 50


def _render_create_form(**ctx):
    """Helper: render admin_create.html with whatever context the caller has,
    plus the limit info every render needs."""
    user = current_user()
    is_admin_user = bool(user and user.get("is_admin") == "true")
    return render_template(
        "admin_create.html",
        is_admin=is_admin_user,
        poll_limit=MAX_POLLS_PER_USER,
        poll_count=user_poll_count(user["username"]) if user else 0,
        **ctx,
    )


@app.route("/admin/create", methods=["GET", "POST"])
def admin_create():
    user = current_user()
    if not user:
        return redirect(url_for("admin_login"))

    is_admin_user = user.get("is_admin") == "true"

    # Cheap guard: even for GET, refuse the page when a non-admin is at
    # their limit so they don't fill out a form just to be rejected.
    if not is_admin_user and user_poll_count(user["username"]) >= MAX_POLLS_PER_USER:
        return _render_create_form(
            error=(
                f"You've reached the {MAX_POLLS_PER_USER}-poll limit. "
                "Delete an old poll before creating a new one."
            ),
            limit_reached=True,
            form_title="",
            form_description="",
            form_max_score="5",
            form_options=["", ""],
        )

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        max_score = request.form.get("max_score", "5")
        raw_options = request.form.getlist("options")
        # De-dupe and trim, preserve original order.
        seen = set()
        options = []
        for opt in raw_options:
            o = opt.strip()
            if not o or o in seen:
                continue
            seen.add(o)
            options.append(o)

        # Validate.
        error = None
        if not title:
            error = "Poll title is required."
        elif len(title) > MAX_TITLE_LEN:
            error = f"Poll title is too long (max {MAX_TITLE_LEN} characters)."
        elif len(description) > MAX_DESCRIPTION_LEN:
            error = f"Description is too long (max {MAX_DESCRIPTION_LEN} characters)."
        elif max_score not in ALLOWED_MAX_SCORES:
            error = "Max score must be 3, 5, or 10."
        elif len(options) < 2:
            error = "At least two distinct, non-blank options are required."
        elif len(options) > MAX_OPTIONS:
            error = f"Too many options (max {MAX_OPTIONS})."
        elif any(len(o) > MAX_OPTION_LEN for o in options):
            error = f"Each option must be at most {MAX_OPTION_LEN} characters."

        if error:
            return _render_create_form(
                error=error,
                form_title=title,
                form_description=description,
                form_max_score=max_score,
                form_options=options or ["", ""],
            )

        poll_id = generate_id()
        poll = {
            "id": poll_id,
            "title": title,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "is_open": "true",
            "max_score": max_score,
            "owner": user["username"],
        }
        option_rows = [
            {"id": i + 1, "name": opt, "description": ""}
            for i, opt in enumerate(options)
        ]
        # Single transaction so the limit check, polls.csv and
        # options_*.csv all stay in sync. Re-check the count INSIDE the
        # lock to defeat a race where a non-admin opens the form, deletes
        # nothing, then submits while another tab also submits.
        with csv_lock():
            if (
                not is_admin_user
                and user_poll_count(user["username"]) >= MAX_POLLS_PER_USER
            ):
                return _render_create_form(
                    error=(
                        f"You've reached the {MAX_POLLS_PER_USER}-poll limit. "
                        "Delete an old poll before creating a new one."
                    ),
                    limit_reached=True,
                    form_title=title,
                    form_description=description,
                    form_max_score=max_score,
                    form_options=options or ["", ""],
                )
            append_csv(f"{DATA_DIR}/polls.csv", poll, POLLS_FIELDS)
            write_csv(
                f"{DATA_DIR}/options_{poll_id}.csv",
                option_rows,
                ["id", "name", "description"],
            )

        return redirect(url_for("admin_poll", poll_id=poll_id))

    return _render_create_form(
        form_title="",
        form_description="",
        form_max_score="5",
        form_options=["", "", ""],
    )


@app.route("/admin/poll/<poll_id>")
def admin_poll(poll_id):
    user = current_user()
    if not user:
        return redirect(url_for("admin_login"))

    poll = get_poll(poll_id)
    if not poll:
        return "Poll not found", 404
    if not can_manage_poll(poll, user):
        # Don't reveal that the poll exists to non-owners.
        return "Poll not found", 404

    options = get_options(poll_id)
    votes = get_votes(poll_id)

    # Calculate results using all methods
    results = calculate_all_results(votes, options, int(poll.get("max_score", 5)))

    return render_template(
        "admin_poll.html", poll=poll, options=options, votes=votes, results=results
    )


@app.route("/admin/poll/<poll_id>/delete_vote/<username>", methods=["POST"])
def delete_vote(poll_id, username):
    user = current_user()
    if not user:
        return redirect(url_for("admin_login"))
    poll = get_poll(poll_id)
    if not poll or not can_manage_poll(poll, user):
        return "Poll not found", 404

    with csv_lock():
        votes = get_votes(poll_id)
        votes = [v for v in votes if v["username"] != username]

        options = get_options(poll_id)
        fieldnames = ["username", "submitted_at"] + [
            f"option_{o['id']}" for o in options
        ]
        write_csv(f"{DATA_DIR}/votes_{poll_id}.csv", votes, fieldnames)

    return redirect(url_for("admin_poll", poll_id=poll_id))


@app.route("/admin/poll/<poll_id>/toggle", methods=["POST"])
def toggle_poll(poll_id):
    user = current_user()
    if not user:
        return redirect(url_for("admin_login"))
    poll = get_poll(poll_id)
    if not poll or not can_manage_poll(poll, user):
        return "Poll not found", 404

    with csv_lock():
        polls = get_polls()
        for p in polls:
            if p["id"] == poll_id:
                p["is_open"] = "false" if p["is_open"] == "true" else "true"
        save_polls(polls)

    return redirect(url_for("admin_poll", poll_id=poll_id))


@app.route("/admin/poll/<poll_id>/delete", methods=["POST"])
def delete_poll(poll_id):
    user = current_user()
    if not user:
        return redirect(url_for("admin_login"))
    poll = get_poll(poll_id)
    if not poll or not can_manage_poll(poll, user):
        return "Poll not found", 404

    with csv_lock():
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


@app.route("/vote/<poll_id>", methods=["GET", "POST"])
def vote(poll_id):
    poll = get_poll(poll_id)
    if not poll:
        return "Poll not found", 404
    if poll["is_open"] != "true":
        return redirect(url_for("results", poll_id=poll_id))

    options = get_options(poll_id)
    max_score = int(poll.get("max_score", 5))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        if not username:
            return render_template(
                "voting.html",
                poll=poll,
                options=options,
                max_score=max_score,
                error="Username required",
            )

        vote_row = {"username": username, "submitted_at": datetime.now().isoformat()}

        # Validate every score is an int in [0, max_score] BEFORE writing.
        # Without this, a non-numeric or out-of-range value crashes
        # algorithms.parse_votes (int("") -> ValueError) when results render.
        for opt in options:
            raw = request.form.get(f"score_{opt['id']}", "0")
            try:
                score_int = int(raw)
            except (ValueError, TypeError):
                return render_template(
                    "voting.html",
                    poll=poll,
                    options=options,
                    max_score=max_score,
                    error=f"Invalid score for '{opt['name']}'",
                )
            if not (0 <= score_int <= max_score):
                return render_template(
                    "voting.html",
                    poll=poll,
                    options=options,
                    max_score=max_score,
                    error=f"Score for '{opt['name']}' must be between 0 and {max_score}",
                )
            vote_row[f"option_{opt['id']}"] = str(score_int)

        fieldnames = ["username", "submitted_at"] + [
            f"option_{o['id']}" for o in options
        ]
        # Hold the lock from the duplicate check through the append so two
        # simultaneous submissions for the same username can't both pass the
        # uniqueness check before either has written.
        with csv_lock():
            if any(v["username"] == username for v in get_votes(poll_id)):
                return render_template(
                    "voting.html",
                    poll=poll,
                    options=options,
                    max_score=max_score,
                    error="You already voted!",
                )
            append_csv(f"{DATA_DIR}/votes_{poll_id}.csv", vote_row, fieldnames)

        return redirect(url_for("results", poll_id=poll_id))

    return render_template(
        "voting.html", poll=poll, options=options, max_score=max_score
    )


@app.route("/results/<poll_id>")
def results(poll_id):
    poll = get_poll(poll_id)
    if not poll:
        return "Poll not found", 404

    options = get_options(poll_id)
    votes = get_votes(poll_id)

    # Calculate results using all methods
    results = calculate_all_results(votes, options, int(poll.get("max_score", 5)))

    return render_template(
        "results.html", poll=poll, options=options, votes=votes, results=results
    )


# ============== HOME ==============


@app.route("/")
def home():
    return redirect(url_for("admin_login"))


# ============== RUN ==============

if __name__ == "__main__":
    # Bind/port and debug flag are env-driven so prod can run without the
    # Werkzeug debugger (which is an RCE vector when accessible).
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    app.run(host=host, port=port, debug=debug)
