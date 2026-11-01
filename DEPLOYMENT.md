# Local setup and deployment

## Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set a strong `SECRET_KEY` in your environment before deployment. Do not commit real credentials or database files.

For a local run, use the entry point documented in the application source package. The hosted start command is defined in `Procfile`.

## Data

The meal catalogue is in `data/meals.csv`. The values are illustrative estimates, not medical guidance or live market prices.
