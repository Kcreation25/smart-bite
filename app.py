import os
import io
import csv
import json
import secrets
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash

import db
import planner

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)

db.init_db(app)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = db.get_user_by_id(db.get_db(), user_id) if user_id else None


@app.route("/")
def index():
    if g.user:
        return redirect(url_for("dashboard"))
    return render_template("home.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "application": "SmartBite"})


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        error = None
        if not name or not email or not password:
            error = "Name, email, and password are all required."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif db.get_user_by_email(db.get_db(), email):
            error = "An account with that email already exists."
        if error:
            flash(error)
            return render_template("signup.html")
        password_hash = generate_password_hash(password)
        user_id = db.create_user(db.get_db(), name, email, password_hash)
        session.clear()
        session["user_id"] = user_id
        return redirect(url_for("profile_setup"))
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = db.get_user_by_email(db.get_db(), email)
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Incorrect email or password.")
            return render_template("login.html")
        session.clear()
        session["user_id"] = user["id"]
        profile = db.get_profile(db.get_db(), user["id"])
        return redirect(url_for("dashboard") if profile else url_for("profile_setup"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _form_to_profile_data(form):
    def f(key, default=None):
        val = form.get(key, "")
        return float(val) if val not in ("", None) else default
    return {
        "weight": f("weight"), "height": f("height"), "age": int(form.get("age")),
        "gender": form.get("gender", "male"), "activity": f("activity"),
        "diet": form.get("diet", "veg"), "goal": form.get("goal", "maintain"),
        "budget": f("budget"), "meals_per_day": int(form.get("meals_per_day")),
        "custom_calories": f("custom_calories", None),
        "custom_protein": f("custom_protein", None),
    }


@app.route("/profile-setup", methods=["GET", "POST"])
@login_required
def profile_setup():
    if request.method == "POST":
        data = _form_to_profile_data(request.form)
        db.upsert_profile(db.get_db(), g.user["id"], data)
        _generate_and_store_plan(g.user["id"], data)
        return redirect(url_for("dashboard"))
    existing = db.get_profile(db.get_db(), g.user["id"])
    return render_template("setup.html", profile=existing)


def _generate_and_store_plan(user_id, profile_row, budget_override=None):
    profile = planner.calc_profile(profile_row, budget_override=budget_override)
    plan = planner.build_plan(profile)
    grocery = planner.build_grocery_list(plan)
    conn = db.get_db()
    plan_id = db.save_plan(conn, user_id, profile, plan)
    db.save_grocery(conn, plan_id, user_id, grocery)
    avg_cal = sum(d["total_cal"] for d in plan["days"]) / 7
    avg_protein = sum(d["total_protein"] for d in plan["days"]) / 7
    db.log_nutrition_history(conn, user_id, plan_id, avg_cal, avg_protein)
    return profile, plan, grocery


@app.route("/regenerate", methods=["POST"])
@login_required
def regenerate():
    profile_row = db.get_profile(db.get_db(), g.user["id"])
    if not profile_row:
        return redirect(url_for("profile_setup"))
    budget_override = request.form.get("budget_override", type=float)
    _generate_and_store_plan(g.user["id"], profile_row, budget_override=budget_override)
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
@login_required
def dashboard():
    conn = db.get_db()
    profile_row = db.get_profile(conn, g.user["id"])
    if not profile_row:
        return redirect(url_for("profile_setup"))
    plan_row = db.get_latest_plan(conn, g.user["id"])
    if not plan_row:
        profile, plan, grocery = _generate_and_store_plan(g.user["id"], profile_row)
        plan_row = db.get_latest_plan(conn, g.user["id"])
    else:
        profile = planner.calc_profile(profile_row, budget_override=plan_row["budget"])
        days = json.loads(plan_row["plan_json"])
        plan = {
            "days": days, "monthly_cost": plan_row["monthly_cost"],
            "weekly_cost": sum(d["total_cost"] for d in days),
            "budget_insufficient": bool(plan_row["budget_insufficient"]),
            "impossible": bool(plan_row["impossible"]), "min_monthly_cost": None,
        }
        grocery_row = db.get_latest_grocery(conn, plan_row["id"])
        grocery = {"rows": json.loads(grocery_row["grocery_json"]), "total_cost": grocery_row["total_cost"]}
    avg_protein = sum(d["total_protein"] for d in plan["days"]) / 7
    avg_cal = sum(d["total_cal"] for d in plan["days"]) / 7
    insights = planner.build_insights(profile, plan, avg_protein)
    bmi_cat = planner.bmi_category(profile["bmi"])
    protein_cal = avg_protein * 4
    remaining_cal = max(avg_cal - protein_cal, 0)
    carbs_g = round((remaining_cal * 0.6) / 4)
    fat_g = round((remaining_cal * 0.4) / 9)
    if plan["min_monthly_cost"] is None:
        full_pool = planner.MEALS[profile["diet"]]
        feasible = planner.min_cost_for_calorie_target(full_pool, profile["meals_per_day"], profile["calorie_target"])
        plan["min_monthly_cost"] = feasible["cost"] * 30 if feasible else None
    return render_template(
        "dashboard.html", profile=profile, plan=plan, grocery=grocery, insights=insights,
        bmi_cat=bmi_cat, nonveg_names=planner.NONVEG_NAMES,
        avg_protein=round(avg_protein), avg_cal=round(avg_cal),
        protein_g=round(avg_protein), carbs_g=carbs_g, fat_g=fat_g,
        days_labels=[f"Day {i+1}" for i in range(7)],
    )


@app.route("/about")
@login_required
def about():
    return render_template("about.html")


@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    conn = db.get_db()
    profile_row = db.get_profile(conn, g.user["id"])
    plan_row = db.get_latest_plan(conn, g.user["id"])
    if not profile_row or not plan_row:
        return jsonify({"answer": "Generate a plan first — then I can answer using your actual numbers."})
    profile = planner.calc_profile(profile_row, budget_override=plan_row["budget"])
    days = json.loads(plan_row["plan_json"])
    plan = {
        "days": days, "monthly_cost": plan_row["monthly_cost"],
        "budget_insufficient": bool(plan_row["budget_insufficient"]),
        "impossible": bool(plan_row["impossible"]),
    }
    grocery_row = db.get_latest_grocery(conn, plan_row["id"])
    grocery = {"rows": json.loads(grocery_row["grocery_json"]), "total_cost": grocery_row["total_cost"]}
    message = request.json.get("message", "") if request.is_json else request.form.get("message", "")
    return jsonify({"answer": planner.assistant_answer(message, profile, plan, grocery)})


@app.route("/progress", methods=["POST"])
@login_required
def progress():
    weight = request.form.get("weight", type=float)
    note = request.form.get("note", "").strip()
    if weight:
        db.add_progress(db.get_db(), g.user["id"], weight, note)
        flash("Progress logged.")
    return redirect(url_for("dashboard"))


@app.route("/report/csv")
@login_required
def report_csv():
    conn = db.get_db()
    plan_row = db.get_latest_plan(conn, g.user["id"])
    if not plan_row:
        return redirect(url_for("dashboard"))
    days = json.loads(plan_row["plan_json"])
    grocery_row = db.get_latest_grocery(conn, plan_row["id"])
    grocery_rows = json.loads(grocery_row["grocery_json"])
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["SmartBite 7-Day Meal Plan"])
    writer.writerow(["Day", "Meal", "Cost (₹)", "Calories", "Protein (g)"])
    for i, day in enumerate(days, start=1):
        for meal in day["meals"]:
            writer.writerow([f"Day {i}", meal["name"], meal["cost"], meal["cal"], meal["protein"]])
    writer.writerow([])
    writer.writerow(["Monthly Grocery List"])
    writer.writerow(["Ingredient", "Quantity", "Est. Cost (₹)"])
    for row in grocery_rows:
        writer.writerow([row["label"], f"{row['qty']} {row['unit']}", row["cost"]])
    db.log_report(conn, g.user["id"], plan_row["id"], "csv")
    mem = io.BytesIO(buf.getvalue().encode("utf-8"))
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name="smartbite_plan.csv")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
