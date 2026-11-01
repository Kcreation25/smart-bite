# SmartBite 2.0

Flask-based personalized nutrition and budget planner.

## Render deployment
This repository includes `render.yaml`. Create a Render Blueprint from this repository to deploy the Python web service. It uses `pip install -r requirements.txt`, `gunicorn app:app`, and `/health` as its health check.

**Persistence warning:** this version uses SQLite. On a free Render service, the filesystem is ephemeral, so account and meal-plan data may be lost after restarts or redeploys. Use this deployment as a demo until persistent storage or managed PostgreSQL is integrated.

## Local setup
Install dependencies with `pip install -r requirements.txt`, set a strong `SECRET_KEY`, then run `python app.py`.

## Tests
Run `python -m compileall -q .` and `python -m unittest discover -s tests -v`.

Nutrition and cost figures are estimates, not medical advice. The planner is rule-based and does not use a trained ML model.
