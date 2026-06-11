# Automation Hub

Automation Hub is the new FastAPI service scaffold for the automation workflow.

## Local Setup

Run commands from this folder:

```powershell
cd automation_hub
copy .env.example .env
uv sync --extra dev
uv run uvicorn automation_hub.web.app:app --reload
```

The development server exposes the live health check at:

```text
http://localhost:8000/health/live
```

## Verification

Run the new service checks from the `automation_hub/` folder:

```powershell
uv run pytest tests/unit/test_app.py -v
uv run ruff check .
uv run mypy src
```

The repository still contains legacy scripts and legacy tests outside this folder. Those checks can have pre-existing failures unrelated to this scaffold, so Task 1 verification should be scoped to the `automation_hub/` commands above.
