"""
Core nutrition and budget logic for SmartBite.
Framework-free so it can be tested independently from Flask.
"""
import itertools
import re
import csv
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
MEAL_DATA_PATH = DATA_DIR / "meals.csv"


def load_meal_database(path=MEAL_DATA_PATH):
    pools = {"veg": [], "non-veg": [], "mixed": []}
    with Path(path).open("r", newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            diet = row["diet_type"].strip()
            if diet not in pools:
                raise ValueError(f"Unknown diet_type in meal dataset: {diet}")
            ingredients = json.loads(row["ingredients_json"])
            pools[diet].append({
                "name": row["meal_name"].strip(),
                "cost": float(row["estimated_cost_inr"]),
                "cal": float(row["calories_kcal"]),
                "protein": float(row["protein_g"]),
                "ing": ingredients,
            })
    if any(not pool for pool in pools.values()):
        raise ValueError("Meal dataset must contain at least one meal for veg, non-veg and mixed diets.")
    return pools


MEALS = load_meal_database()
NONVEG_NAMES = {m["name"] for m in MEALS["non-veg"]}
_seen = set()
ALL_MEALS_FLAT = []
for _pool in MEALS.values():
    for _m in _pool:
        if _m["name"] not in _seen:
            _seen.add(_m["name"])
            ALL_MEALS_FLAT.append(_m)

UNIT_PRICE = {
    "rice": 45 / 1000, "wheat": 40 / 1000, "pulses": 110 / 1000, "vegetables": 35 / 1000,
    "chicken": 200 / 1000, "fish": 250 / 1000, "mutton": 650 / 1000, "paneer": 320 / 1000,
    "oil": 140 / 1000, "milk": 60 / 1000, "eggs": 6,
}
UNIT_LABEL = {
    "rice": "Rice", "wheat": "Wheat flour (atta)", "pulses": "Pulses / dal", "vegetables": "Mixed vegetables",
    "chicken": "Chicken", "fish": "Fish", "mutton": "Mutton", "paneer": "Paneer",
    "oil": "Cooking oil", "milk": "Milk / curd", "eggs": "Eggs",
}


def calc_profile(row, budget_override=None):
    row = dict(row)
    weight, height, age = float(row["weight"]), float(row["height"]), int(row["age"])
    activity, gender = float(row["activity"]), row["gender"]
    diet, goal = row["diet"], row["goal"]
    meals_per_day = int(row["meals_per_day"])
    budget = float(budget_override) if budget_override is not None else float(row["budget"])
    custom_calories, custom_protein = row.get("custom_calories"), row.get("custom_protein")
    bmi = weight / ((height / 100) ** 2)
    bmr = 10 * weight + 6.25 * height - 5 * age + (5 if gender == "male" else -161)
    tdee = bmr * activity
    calorie_is_custom = bool(custom_calories)
    if calorie_is_custom:
        calorie_target = float(custom_calories)
    elif goal == "loss":
        calorie_target = tdee - 500
    elif goal == "gain":
        calorie_target = tdee + 350
    else:
        calorie_target = tdee
    if not calorie_is_custom:
        calorie_target = max(calorie_target, 1500 if gender == "male" else 1200)
    protein_is_custom = bool(custom_protein)
    protein_target = float(custom_protein) if protein_is_custom else weight * (1.0 if goal == "maintain" else 1.6)
    daily_budget = budget / 30
    return {
        "weight": weight, "height": height, "age": age, "gender": gender, "activity": activity,
        "diet": diet, "goal": goal, "budget": budget, "meals_per_day": meals_per_day,
        "bmi": bmi, "bmr": bmr, "tdee": tdee, "calorie_target": calorie_target,
        "calorie_is_custom": calorie_is_custom, "protein_target": protein_target,
        "protein_is_custom": protein_is_custom, "daily_budget": daily_budget,
        "per_meal_budget": daily_budget / meals_per_day,
    }


def bmi_category(bmi):
    if bmi < 18.5:
        return "Underweight"
    if bmi < 25:
        return "Normal"
    if bmi < 30:
        return "Overweight"
    return "Obese"


def min_cost_for_calorie_target(pool, meals_per_day, calorie_target):
    best = None
    for combo in itertools.product(range(len(pool)), repeat=meals_per_day):
        cal = sum(pool[i]["cal"] for i in combo)
        if cal < calorie_target * 0.95:
            continue
        cost = sum(pool[i]["cost"] for i in combo)
        if best is None or cost < best["cost"]:
            best = {"cost": cost, "cal": cal, "items": [pool[i] for i in combo]}
    return best


def _generate_week(pool, profile):
    days, last_picked = [], None
    meals_per_day = profile["meals_per_day"]
    for d in range(7):
        day_meals, remaining_cal = [], profile["calorie_target"]
        for m in range(meals_per_day):
            target = remaining_cal / (meals_per_day - m)
            candidates = [x for x in pool if x["name"] != last_picked] or list(pool)
            candidates = sorted(candidates, key=lambda x: abs(x["cal"] - target))
            top_n = candidates[:min(3, len(candidates))]
            pick = top_n[(d + m) % len(top_n)]
            day_meals.append(pick)
            remaining_cal -= pick["cal"]
            last_picked = pick["name"]
        days.append({
            "meals": day_meals, "total_cal": sum(x["cal"] for x in day_meals),
            "total_protein": sum(x["protein"] for x in day_meals),
            "total_cost": sum(x["cost"] for x in day_meals),
        })
    return days


def build_plan(profile):
    full_pool = MEALS[profile["diet"]]
    feasible = min_cost_for_calorie_target(full_pool, profile["meals_per_day"], profile["calorie_target"])
    min_monthly_cost = feasible["cost"] * 30 if feasible else None
    impossible = feasible is None
    budget_insufficient = min_monthly_cost is not None and min_monthly_cost > profile["budget"]
    pool = [m for m in full_pool if m["cost"] <= profile["per_meal_budget"] * 1.6]
    if not pool:
        pool = sorted(full_pool, key=lambda m: m["cost"])[:4]
    ranked = sorted(pool, key=lambda m: (m["protein"] / m["cost"]), reverse=True)
    days = _generate_week(ranked, profile)
    weekly_cost = sum(d["total_cost"] for d in days)
    monthly_cost = weekly_cost * (30 / 7)
    attempts = 0
    while monthly_cost > profile["budget"] and attempts < 4 and len(ranked) > profile["meals_per_day"]:
        keep = max(profile["meals_per_day"], len(ranked) - 2)
        ranked = sorted(ranked, key=lambda m: m["cost"])[:keep]
        days = _generate_week(ranked, profile)
        weekly_cost = sum(d["total_cost"] for d in days)
        monthly_cost = weekly_cost * (30 / 7)
        attempts += 1
    return {
        "days": days, "weekly_cost": weekly_cost, "monthly_cost": monthly_cost,
        "budget_insufficient": budget_insufficient, "impossible": impossible,
        "min_monthly_cost": min_monthly_cost,
    }


def build_grocery_list(plan):
    totals = {}
    for day in plan["days"]:
        for meal in day["meals"]:
            for row in meal["ing"]:
                unit = "pc" if row.get("unit") == "pc" else "g"
                key = row["i"]
                totals.setdefault(key, {"qty": 0.0, "unit": unit})
                totals[key]["qty"] += row["q"] * (30 / 7)
    rows = []
    for key, t in totals.items():
        if t["unit"] == "pc":
            display_qty, display_unit = round(t["qty"]), "eggs"
            cost = display_qty * UNIT_PRICE["eggs"]
        else:
            display_qty = round(t["qty"] / 1000, 1)
            display_unit = "kg" + (" (or L)" if key == "oil" else "")
            cost = t["qty"] * UNIT_PRICE[key]
        rows.append({"label": UNIT_LABEL[key], "qty": display_qty, "unit": display_unit, "cost": round(cost)})
    rows.sort(key=lambda r: r["cost"], reverse=True)
    return {"rows": rows, "total_cost": sum(r["cost"] for r in rows)}


def build_insights(profile, plan, avg_protein):
    tips = []
    cat = bmi_category(profile["bmi"])
    if cat == "Underweight":
        tips.append("Your BMI is under 18.5 — this plan leans on calorie-dense, protein-rich meals to help you gain steadily.")
    elif cat in ("Overweight", "Obese"):
        tips.append("Your BMI is above the typical range — pair this calorie deficit with regular movement, and reassess in 3-4 weeks rather than expecting fast changes.")
    else:
        tips.append("Your BMI sits in the typical range — this plan is built to maintain that while hitting your protein target.")
    if avg_protein < profile["protein_target"] * 0.9:
        tips.append(f"Average protein ({round(avg_protein)}g/day) is a little under your {round(profile['protein_target'])}g target — swap in one egg- or paneer-based meal on lighter days.")
    else:
        tips.append(f"Protein is on track: averaging {round(avg_protein)}g/day against a {round(profile['protein_target'])}g target.")
    if plan["budget_insufficient"]:
        tips.append(f"As flagged above, this budget can't fully reach {round(profile['calorie_target'])} kcal/day at the cheapest — raise the monthly budget or accept the closest affordable plan shown here.")
    else:
        tips.append(f"You're within budget — the full month (staples + typical overhead) comes to about ₹{round(plan['monthly_cost'])} against your ₹{round(profile['budget'])} allowance.")
    if profile["goal"] == "loss":
        tips.append("A ~500 kcal daily deficit targets roughly 0.4-0.5 kg of loss per week — a pace that's easier to sustain than aggressive cuts.")
    if profile["goal"] == "gain":
        tips.append("A moderate surplus plus your protein target supports lean gain — strength training 3+ times a week makes the extra calories count.")
    tips.append("Aim for at least 2.5-3 litres of water daily, more on hot days or after exercise.")
    return tips


def assistant_answer(query, profile, plan, grocery):
    if not profile or not plan:
        return "Generate a plan first — then I can answer using your actual numbers."
    q = query.lower()
    pool = MEALS[profile["diet"]]
    ranked = sorted(pool, key=lambda m: (m["protein"] / m["cost"]), reverse=True)
    if re.search(r"cheap(er)?.*protein|protein.*cheap", q):
        parts = [f"{m['name']} ({m['protein']/m['cost']:.2f}g protein per ₹, {m['protein']}g for ₹{m['cost']})" for m in ranked[:3]]
        return f"Best protein-per-rupee options in your {profile['diet']} list: " + "; ".join(parts) + "."
    if re.search(r"replace|swap|instead of", q) and "chicken" in q and "paneer" in q:
        chicken = next((m for m in ALL_MEALS_FLAT if "chicken" in m["name"].lower()), None)
        paneer = next((m for m in ALL_MEALS_FLAT if "paneer" in m["name"].lower()), None)
        if chicken and paneer:
            c_eff, p_eff = chicken["protein"] / chicken["cost"], paneer["protein"] / paneer["cost"]
            verdict = ("Paneer is the cheaper protein source here — a workable swap if you're not chasing max protein density."
                       if p_eff > c_eff else
                       "Chicken is more protein-efficient per rupee, but paneer works fine if you want a vegetarian day.")
            return (f"{chicken['name']} gives {chicken['protein']}g protein for ₹{chicken['cost']} ({c_eff:.2f}g/₹). "
                    f"{paneer['name']} gives {paneer['protein']}g protein for ₹{paneer['cost']} ({p_eff:.2f}g/₹). {verdict}")
        return "I don't have a direct paneer-vs-chicken pair in the current diet type — switch diet type to 'mixed' to compare both."
    if re.search(r"reduce.*(cost|budget|grocery)|cheaper.*(plan|week)|lower.*cost", q):
        names = ", ".join(m["name"] for m in sorted(pool, key=lambda m: m["cost"])[:3])
        return f"Your current plan runs about ₹{round(plan['monthly_cost'])}/month. Leaning more on {names} — your cheapest options — could bring the monthly grocery total down, though you'd trade off some variety and, in a couple of cases, some protein per meal."
    if re.search(r"workout|exercise|gym|post-workout|after training", q):
        best = sorted(pool, key=lambda m: m["protein"], reverse=True)[0]
        return f"Based on your {round(profile['protein_target'])}g daily protein target, {best['name']} ({best['protein']}g protein, {best['cal']} kcal, ₹{best['cost']}) is your highest-protein option in this diet type — a solid post-workout meal within 1-2 hours of training, alongside your normal water intake."
    if re.search(r"diabetes|diabetic|blood sugar|sugar level", q):
        lower_gi = [m for m in pool if not re.search(r"biryani|bhature|pulao|fried rice", m["name"], re.I)]
        names = " and ".join(m["name"] for m in lower_gi[:2]) if lower_gi else "the dal- and salad-based options"
        return f"I can't tailor a medical diet — please check with a doctor or dietitian for diabetes-specific targets. In general terms, meals like {names} lean less on refined white rice/fried dishes than options like biryani or bhature, which can help moderate blood sugar spikes — but this is general information, not a diagnosis-specific plan."
    return (f"Your plan: {round(profile['calorie_target'])} kcal/day, {round(profile['protein_target'])}g protein/day, "
            f"₹{round(profile['budget'])}/month budget, currently costing about ₹{round(plan['monthly_cost'])}/month. "
            "Ask me about cheaper protein, ingredient swaps, reducing cost, post-workout meals, or general dietary patterns.")
