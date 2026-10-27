"""SkillSync - Campus Skill Matching Platform (Flask + SQLite)."""
import os
import re
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (Flask, g, render_template, request, redirect, url_for,
                   session, flash, abort)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "skillsync.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SKILLSYNC_SECRET", "skillsync-dev-secret-change-me")

DEPARTMENTS = [
    "Computer Science", "Information Technology", "Electronics and Communication",
    "Electrical Engineering", "Mechanical Engineering", "Civil Engineering",
    "Artificial Intelligence and Data Science", "Business Administration",
    "Design", "Biotechnology", "Other",
]
YEARS = {1: "1st Year", 2: "2nd Year", 3: "3rd Year", 4: "4th Year", 5: "Postgraduate"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# ----------------------------------------------------------------- database
SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    department    TEXT NOT NULL,
    year          INTEGER NOT NULL,
    skills        TEXT NOT NULL DEFAULT '',
    interests     TEXT NOT NULL DEFAULT '',
    bio           TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id        INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    required_skills TEXT NOT NULL,
    team_size       INTEGER NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_interests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    message     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    UNIQUE(project_id, student_id)
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    con = sqlite3.connect(DATABASE)
    con.executescript(SCHEMA)
    con.commit()
    con.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------- matching engine
def split_items(raw):
    """'Python, sql ; Python' -> ['Python', 'sql'] (case-insensitive de-dupe)."""
    seen, out = set(), []
    for part in re.split(r"[,;\n]+", raw or ""):
        item = " ".join(part.split())
        if item and item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return out[:25]


def lset(items):
    return {i.lower() for i in items}


def overlap(a, b):
    """Overlap coefficient: |A and B| / min(|A|, |B|). 0 if either is empty."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


W_SKILLS, W_INTERESTS, W_COMPLEMENT = 0.40, 0.30, 0.30


def compute_match(me, other):
    """Explainable weighted score between two students (0-100).

    40%  shared skills      -> overlap coefficient of skill sets
    30%  shared interests   -> overlap coefficient of interest sets
    30%  complementary      -> how many skills the other student has that I lack
                               (3 or more new skills = full marks)
    """
    my_sk, ot_sk = split_items(me["skills"]), split_items(other["skills"])
    my_set, ot_set = lset(my_sk), lset(ot_sk)
    common = [s for s in ot_sk if s.lower() in my_set]
    complementary = [s for s in ot_sk if s.lower() not in my_set]

    my_in, ot_in = split_items(me["interests"]), split_items(other["interests"])
    common_interests = [i for i in ot_in if i.lower() in lset(my_in)]

    skill_part = overlap(my_set, ot_set)
    interest_part = overlap(lset(my_in), lset(ot_in))
    comp_part = min(1.0, len(complementary) / 3.0)

    score = round(100 * (W_SKILLS * skill_part + W_INTERESTS * interest_part
                         + W_COMPLEMENT * comp_part))
    return {
        "score": score,
        "common": common,
        "complementary": complementary,
        "common_interests": common_interests,
    }


def rank_students(me, others):
    ranked = [{"s": o, "m": compute_match(me, o)} for o in others]
    ranked.sort(key=lambda r: (-r["m"]["score"], r["s"]["name"].lower()))
    return ranked


def project_fit(me, project):
    """Share of a project's required skills that the student already has."""
    req = split_items(project["required_skills"])
    mine = lset(split_items(me["skills"]))
    have = [s for s in req if s.lower() in mine]
    missing = [s for s in req if s.lower() not in mine]
    pct = round(100 * len(have) / len(req)) if req else 0
    return {"pct": pct, "have": have, "missing": missing}


# -------------------------------------------------------------------- auth
@app.before_request
def load_user():
    g.user = None
    uid = session.get("user_id")
    if uid:
        g.user = get_db().execute("SELECT * FROM students WHERE id = ?", (uid,)).fetchone()
        if g.user is None:
            session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if g.user is None:
            flash("Please log in to continue.", "info")
            return redirect(url_for("login", next=request.path))
        return view(*a, **kw)
    return wrapped


@app.template_filter("items")
def items_filter(raw):
    return split_items(raw)


@app.template_filter("initials")
def initials_filter(name):
    parts = (name or "?").split()
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


@app.template_filter("year_label")
def year_label(y):
    return YEARS.get(y, str(y))


@app.template_filter("nice_date")
def nice_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").strftime("%d %b %Y")
    except (ValueError, TypeError):
        return s


# ------------------------------------------------------------------ public
@app.route("/")
def index():
    db = get_db()
    stats = {
        "students": db.execute("SELECT COUNT(*) FROM students").fetchone()[0],
        "projects": db.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
    }
    return render_template("index.html", stats=stats)


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("dashboard"))
    form, errors = {}, {}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in
                ("name", "email", "password", "confirm", "department", "year", "skills", "interests")}
        form["email"] = form["email"].lower()
        if len(form["name"]) < 2:
            errors["name"] = "Please enter your full name."
        if not EMAIL_RE.match(form["email"]):
            errors["email"] = "Enter a valid email address."
        if len(form["password"]) < 6:
            errors["password"] = "Password must be at least 6 characters."
        if form["password"] != form["confirm"]:
            errors["confirm"] = "Passwords do not match."
        if form["department"] not in DEPARTMENTS:
            errors["department"] = "Choose your department."
        if form["year"] not in {str(k) for k in YEARS}:
            errors["year"] = "Choose your year of study."
        if not split_items(form["skills"]):
            errors["skills"] = "Add at least one skill (separate with commas)."
        if not split_items(form["interests"]):
            errors["interests"] = "Add at least one area of interest."
        db = get_db()
        if "email" not in errors and db.execute(
                "SELECT 1 FROM students WHERE email = ?", (form["email"],)).fetchone():
            errors["email"] = "An account with this email already exists."
        if not errors:
            cur = db.execute(
                "INSERT INTO students (name, email, password_hash, department, year, skills, interests, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (form["name"], form["email"], generate_password_hash(form["password"]),
                 form["department"], int(form["year"]),
                 ", ".join(split_items(form["skills"])),
                 ", ".join(split_items(form["interests"])), now()))
            db.commit()
            session.clear()
            session["user_id"] = cur.lastrowid
            flash("Welcome to SkillSync! Your account is ready.", "success")
            return redirect(url_for("dashboard"))
    return render_template("register.html", form=form, errors=errors,
                           departments=DEPARTMENTS, years=YEARS)


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard"))
    error, email = None, ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM students WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['name'].split()[0]}!", "success")
            nxt = request.args.get("next", "")
            if nxt.startswith("/") and not nxt.startswith("//"):
                return redirect(nxt)
            return redirect(url_for("dashboard"))
        error = "Incorrect email or password."
    return render_template("login.html", error=error, email=email)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# --------------------------------------------------------------- dashboard
@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    me = g.user
    others = db.execute("SELECT * FROM students WHERE id != ?", (me["id"],)).fetchall()
    ranked = rank_students(me, others)
    matching_count = sum(1 for r in ranked if r["m"]["common"])
    recent = db.execute(
        "SELECT p.*, s.name AS owner_name FROM projects p JOIN students s ON s.id = p.owner_id "
        "ORDER BY p.created_at DESC, p.id DESC LIMIT 4").fetchall()
    recent_projects = [{"p": p, "fit": project_fit(me, p)} for p in recent]
    stats = {
        "students": db.execute("SELECT COUNT(*) FROM students").fetchone()[0],
        "projects": db.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
        "matching": matching_count,
        "mine": db.execute("SELECT COUNT(*) FROM projects WHERE owner_id = ?", (me["id"],)).fetchone()[0],
    }
    return render_template("dashboard.html", stats=stats, recommended=ranked[:3],
                           recent_projects=recent_projects)


# ----------------------------------------------------------------- profile
@app.route("/profile")
@login_required
def my_profile():
    return redirect(url_for("profile", student_id=g.user["id"]))


@app.route("/students/<int:student_id>")
@login_required
def profile(student_id):
    db = get_db()
    s = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if s is None:
        abort(404)
    is_me = s["id"] == g.user["id"]
    match = None if is_me else compute_match(g.user, s)
    projs = db.execute("SELECT * FROM projects WHERE owner_id = ? ORDER BY created_at DESC", (s["id"],)).fetchall()
    return render_template("profile.html", s=s, is_me=is_me, match=match, projs=projs)


@app.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    errors, form = {}, dict(g.user)
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in
                ("name", "department", "year", "skills", "interests", "bio")}
        if len(form["name"]) < 2:
            errors["name"] = "Please enter your full name."
        if form["department"] not in DEPARTMENTS:
            errors["department"] = "Choose your department."
        if form["year"] not in {str(k) for k in YEARS}:
            errors["year"] = "Choose your year of study."
        if not split_items(form["skills"]):
            errors["skills"] = "Add at least one skill."
        if not split_items(form["interests"]):
            errors["interests"] = "Add at least one area of interest."
        if len(form["bio"]) > 300:
            errors["bio"] = "Keep your bio under 300 characters."
        if not errors:
            db = get_db()
            db.execute(
                "UPDATE students SET name=?, department=?, year=?, skills=?, interests=?, bio=? WHERE id=?",
                (form["name"], form["department"], int(form["year"]),
                 ", ".join(split_items(form["skills"])),
                 ", ".join(split_items(form["interests"])), form["bio"], g.user["id"]))
            db.commit()
            flash("Profile updated. Your matches have been recalculated.", "success")
            return redirect(url_for("profile", student_id=g.user["id"]))
    return render_template("edit_profile.html", form=form, errors=errors,
                           departments=DEPARTMENTS, years=YEARS)


# ---------------------------------------------------------------- matching
@app.route("/students")
@login_required
def students():
    db = get_db()
    q = request.args.get("q", "").strip().lower()
    dept = request.args.get("department", "")
    sort = request.args.get("sort", "match")
    only_common = request.args.get("common") == "1"

    rows = db.execute("SELECT * FROM students WHERE id != ?", (g.user["id"],)).fetchall()
    ranked = rank_students(g.user, rows)
    results = []
    for r in ranked:
        s = r["s"]
        if dept and s["department"] != dept:
            continue
        if q and not (q in s["name"].lower()
                      or any(q in sk.lower() for sk in split_items(s["skills"]))
                      or any(q in i.lower() for i in split_items(s["interests"]))):
            continue
        if only_common and not r["m"]["common"]:
            continue
        results.append(r)
    if sort == "name":
        results.sort(key=lambda r: r["s"]["name"].lower())
    depts = [d["department"] for d in db.execute(
        "SELECT DISTINCT department FROM students ORDER BY department").fetchall()]
    return render_template("students.html", results=results, depts=depts, total=len(rows),
                           q=request.args.get("q", ""), dept=dept, sort=sort, only_common=only_common,
                           weights=(W_SKILLS, W_INTERESTS, W_COMPLEMENT))


# ----------------------------------------------------------- project hub
def fetch_project(pid):
    p = get_db().execute(
        "SELECT p.*, s.name AS owner_name, s.department AS owner_dept FROM projects p "
        "JOIN students s ON s.id = p.owner_id WHERE p.id = ?", (pid,)).fetchone()
    if p is None:
        abort(404)
    return p


@app.route("/projects")
@login_required
def projects():
    db = get_db()
    q = request.args.get("q", "").strip().lower()
    sort = request.args.get("sort", "recent")
    scope = request.args.get("scope", "all")
    rows = db.execute(
        "SELECT p.*, s.name AS owner_name, "
        "(SELECT COUNT(*) FROM project_interests pi WHERE pi.project_id = p.id) AS interest_count "
        "FROM projects p JOIN students s ON s.id = p.owner_id "
        "ORDER BY p.created_at DESC, p.id DESC").fetchall()
    items = []
    for p in rows:
        if scope == "mine" and p["owner_id"] != g.user["id"]:
            continue
        if q and not (q in p["title"].lower() or q in p["description"].lower()
                      or q in p["required_skills"].lower()):
            continue
        items.append({"p": p, "fit": project_fit(g.user, p)})
    if sort == "fit":
        items.sort(key=lambda i: -i["fit"]["pct"])
    return render_template("projects.html", items=items, q=request.args.get("q", ""),
                           sort=sort, scope=scope)


@app.route("/projects/new", methods=["GET", "POST"])
@login_required
def new_project():
    form, errors = {"team_size": "4"}, {}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in
                ("title", "description", "required_skills", "team_size")}
        if len(form["title"]) < 3:
            errors["title"] = "Give your project a title (3+ characters)."
        if len(form["description"]) < 20:
            errors["description"] = "Describe the project in at least 20 characters."
        if not split_items(form["required_skills"]):
            errors["required_skills"] = "List at least one required skill."
        try:
            size = int(form["team_size"])
            if not 2 <= size <= 12:
                raise ValueError
        except ValueError:
            errors["team_size"] = "Team size must be a number from 2 to 12."
        if not errors:
            db = get_db()
            cur = db.execute(
                "INSERT INTO projects (owner_id, title, description, required_skills, team_size, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (g.user["id"], form["title"], form["description"],
                 ", ".join(split_items(form["required_skills"])), size, now()))
            db.commit()
            flash("Project posted. Students with matching skills can now find it.", "success")
            return redirect(url_for("project_detail", pid=cur.lastrowid))
    return render_template("new_project.html", form=form, errors=errors)


@app.route("/projects/<int:pid>")
@login_required
def project_detail(pid):
    db = get_db()
    p = fetch_project(pid)
    fit = project_fit(g.user, p)
    is_owner = p["owner_id"] == g.user["id"]
    interested = db.execute(
        "SELECT pi.*, s.name, s.department, s.year, s.skills FROM project_interests pi "
        "JOIN students s ON s.id = pi.student_id WHERE pi.project_id = ? ORDER BY pi.created_at",
        (pid,)).fetchall()
    my_interest = next((i for i in interested if i["student_id"] == g.user["id"]), None)

    suggestions = []
    if is_owner:
        req = lset(split_items(p["required_skills"]))
        already = {i["student_id"] for i in interested}
        for s in db.execute("SELECT * FROM students WHERE id != ?", (g.user["id"],)).fetchall():
            if s["id"] in already:
                continue
            covers = [k for k in split_items(s["skills"]) if k.lower() in req]
            if covers:
                suggestions.append({"s": s, "covers": covers,
                                    "pct": round(100 * len(covers) / len(req))})
        suggestions.sort(key=lambda x: -x["pct"])
        suggestions = suggestions[:5]
    return render_template("project_detail.html", p=p, fit=fit, is_owner=is_owner,
                           interested=interested, my_interest=my_interest, suggestions=suggestions)


@app.route("/projects/<int:pid>/interest", methods=["POST"])
@login_required
def express_interest(pid):
    p = fetch_project(pid)
    if p["owner_id"] == g.user["id"]:
        flash("You own this project.", "info")
        return redirect(url_for("project_detail", pid=pid))
    db = get_db()
    try:
        db.execute("INSERT INTO project_interests (project_id, student_id, message, created_at) VALUES (?, ?, ?, ?)",
                   (pid, g.user["id"], request.form.get("message", "").strip()[:300], now()))
        db.commit()
        flash("Interest sent. The project owner can now see your profile.", "success")
    except sqlite3.IntegrityError:
        flash("You have already expressed interest in this project.", "info")
    return redirect(url_for("project_detail", pid=pid))


@app.route("/projects/<int:pid>/withdraw", methods=["POST"])
@login_required
def withdraw_interest(pid):
    db = get_db()
    db.execute("DELETE FROM project_interests WHERE project_id = ? AND student_id = ?", (pid, g.user["id"]))
    db.commit()
    flash("Your interest was withdrawn.", "info")
    return redirect(url_for("project_detail", pid=pid))


@app.route("/projects/<int:pid>/delete", methods=["POST"])
@login_required
def delete_project(pid):
    p = fetch_project(pid)
    if p["owner_id"] != g.user["id"]:
        abort(403)
    db = get_db()
    db.execute("DELETE FROM projects WHERE id = ?", (pid,))
    db.commit()
    flash("Project deleted.", "info")
    return redirect(url_for("projects"))


@app.errorhandler(404)
def not_found(_e):
    return render_template("error.html", code=404, msg="We couldn't find that page."), 404


@app.errorhandler(403)
def forbidden(_e):
    return render_template("error.html", code=403, msg="You don't have permission to do that."), 403


init_db()

if __name__ == "__main__":
    app.run(debug=True)
