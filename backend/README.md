# Super Bajaar backend

The modular API entry point is `app.main:app`. The existing AWS service was reported as listening on `127.0.0.1:8001`; preserve that live service and its configuration until a separately tested cutover is approved. PostgreSQL was reported on `127.0.0.1:5432`.

## Local setup

1. Create and activate a Python virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Run tests from this directory with `pytest -q`.
4. Run a local development instance on an isolated port, for example:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Do not launch this scaffold on port 8001 while the current service owns that listener. Do not point local tests at production data. Configure secrets in environment variables; never commit a real `.env` file.

## Current scope

The health endpoint is a foundation only. Catalogue, variant validation, inventory, order, payment, delivery and ERP workflows are not yet implemented. SQL under `../database` is a reference asset and is not automatically applied.
