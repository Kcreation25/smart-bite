import sqlite3
import os
import json
from flask import g

DB_PATH = os.environ.get("SMARTBITE_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "smartbite.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS user_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    weight REAL, height REAL, age INTEGER, gender TEXT, activity REAL,
    diet TEXT, goal TEXT, budget REAL, meals_per_day INTEGER,
    custom_calories REAL, custom_protein REAL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS meal_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    calorie_target REAL, protein_target REAL,
    monthly_cost REAL, budget REAL,
    budget_insufficient INTEGER, impossible INTEGER,
    plan_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS grocery_lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meal_plan_id INTEGER NOT NULL REFERENCES meal_plans(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    total_cost REAL,
    grocery_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nutrition_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    logged_at TEXT NOT NULL DEFAULT (datetime('now')),
    meal_plan_id INTEGER REFERENCES meal_plans(id),
    avg_calories REAL, avg_protein REAL
);
CREATE TABLE IF NOT EXISTS progress_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    logged_at TEXT NOT NULL DEFAULT (datetime('now')),
    weight REAL,
    note TEXT
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    meal_plan_id INTEGER REFERENCES meal_plans(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    report_type TEXT
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    with app.app_context():
        db = sqlite3.connect(DB_PATH)
        db.executescript(SCHEMA)
        db.commit()
        db.close()
    app.teardown_appcontext(close_db)


def create_user(db, name, email, password_hash):
    cur = db.execute("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)", (name, email, password_hash))
    db.commit()
    return cur.lastrowid


def get_user_by_email(db, email):
    return db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def get_user_by_id(db, user_id):
    return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def upsert_profile(db, user_id, data):
    existing = db.execute("SELECT id FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
    if existing:
        db.execute("""UPDATE user_profiles SET weight=?, height=?, age=?, gender=?, activity=?,
            diet=?, goal=?, budget=?, meals_per_day=?, custom_calories=?, custom_protein=?,
            updated_at=datetime('now') WHERE user_id=?""",
            (data["weight"], data["height"], data["age"], data["gender"], data["activity"],
             data["diet"], data["goal"], data["budget"], data["meals_per_day"],
             data.get("custom_calories"), data.get("custom_protein"), user_id))
    else:
        db.execute("""INSERT INTO user_profiles
            (user_id, weight, height, age, gender, activity, diet, goal, budget,
             meals_per_day, custom_calories, custom_protein)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, data["weight"], data["height"], data["age"], data["gender"], data["activity"],
             data["diet"], data["goal"], data["budget"], data["meals_per_day"],
             data.get("custom_calories"), data.get("custom_protein")))
    db.commit()


def get_profile(db, user_id):
    return db.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()


def save_plan(db, user_id, profile, plan):
    cur = db.execute("""INSERT INTO meal_plans
        (user_id, calorie_target, protein_target, monthly_cost, budget, budget_insufficient, impossible, plan_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, profile["calorie_target"], profile["protein_target"], plan["monthly_cost"],
         profile["budget"], int(plan["budget_insufficient"]), int(plan["impossible"]), json.dumps(plan["days"])))
    db.commit()
    return cur.lastrowid


def save_grocery(db, meal_plan_id, user_id, grocery):
    db.execute("INSERT INTO grocery_lists (meal_plan_id, user_id, total_cost, grocery_json) VALUES (?, ?, ?, ?)",
               (meal_plan_id, user_id, grocery["total_cost"], json.dumps(grocery["rows"])))
    db.commit()


def log_nutrition_history(db, user_id, meal_plan_id, avg_calories, avg_protein):
    db.execute("INSERT INTO nutrition_history (user_id, meal_plan_id, avg_calories, avg_protein) VALUES (?, ?, ?, ?)",
               (user_id, meal_plan_id, avg_calories, avg_protein))
    db.commit()


def get_latest_plan(db, user_id):
    return db.execute("SELECT * FROM meal_plans WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (user_id,)).fetchone()


def get_latest_grocery(db, meal_plan_id):
    return db.execute("SELECT * FROM grocery_lists WHERE meal_plan_id = ? ORDER BY created_at DESC LIMIT 1", (meal_plan_id,)).fetchone()


def get_plan_history(db, user_id, limit=10):
    return db.execute("SELECT * FROM meal_plans WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit)).fetchall()


def add_progress(db, user_id, weight, note):
    db.execute("INSERT INTO progress_tracking (user_id, weight, note) VALUES (?, ?, ?)", (user_id, weight, note))
    db.commit()


def get_progress(db, user_id):
    return db.execute("SELECT * FROM progress_tracking WHERE user_id = ? ORDER BY logged_at ASC", (user_id,)).fetchall()


def log_report(db, user_id, meal_plan_id, report_type):
    db.execute("INSERT INTO reports (user_id, meal_plan_id, report_type) VALUES (?, ?, ?)", (user_id, meal_plan_id, report_type))
    db.commit()
