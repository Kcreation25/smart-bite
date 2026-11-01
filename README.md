# SmartBite 2.0 — Personalized Nutrition & Budget Planner

SmartBite is a Flask-based web application concept for planning everyday Indian meals around a user's dietary preference, nutrition targets and monthly food budget.

## Core features
- Account registration and login
- Profile-based BMI, BMR and TDEE estimates
- Seven-day vegetarian, non-vegetarian and mixed meal plans
- Calorie and protein target estimates
- Budget feasibility and estimated monthly food cost
- Ingredient-level grocery list
- Nutrition dashboard, progress tracking and CSV report
- Rule-based nutrition assistant

## Dataset
The `data/` directory contains a curated meal catalogue extracted from the original project's embedded meal records and organized as CSV. It is project-created reference data, not a third-party benchmark or clinical dataset.

- `data/meals.csv`: meal type, meal name, estimated serving cost, calories, protein and ingredient quantities.
- `data/ingredient_price_reference.csv`: illustrative ingredient price assumptions.
- `data/README.md`: schema, assumptions and limitations.

Nutrition and price values are approximate and may vary by recipe, portion size, location and market conditions. This project is not medical advice.

## Source package
The full application source, including Flask routes, SQLite database code, templates, CSS, tests and the CSV-backed planner, is packaged separately as `smartbite_app_source.tar.xz` when provided with this project. Extract the archive to access the runnable application folder.

## Run locally
From the extracted `smartbite_app` folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY = "replace-with-a-long-random-secret"
python app.py
```

Open http://127.0.0.1:5000.

## Technology
Python · Flask · SQLite · HTML · CSS · Jinja · CSV

## Limitations
The planner and assistant are rule-based; no trained machine-learning model or live generative AI service is used. Calorie, protein and cost figures are estimates. Consult a qualified dietitian or clinician for medical nutrition needs.

## License
No license has been added. Confirm the intended distribution terms before assigning one.
