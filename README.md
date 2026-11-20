# PlantDoctor

AI plant-health assistant for farmers and growers (focus: Pakistan). Upload or photograph a leaf or
fruit; PlantDoctor identifies the plant, detects likely diseases and pests with calibrated confidence,
refuses to guess on unfamiliar photos, and gives a source-cited treatment plan with products sold in
Pakistan. Decision support only — not a laboratory diagnosis.

## Quick start (development)

    ./setup.sh                                   # Python venv + PyTorch (CUDA) + requirements
    cd frontend && npm ci && npm run build && cd ..
    ./run.sh                                     # http://127.0.0.1:8000

- First user whose email is in `PD_ADMIN_EMAILS` becomes admin. Copy `.env.example` to `.env` to configure.
- Without `ANTHROPIC_API_KEY` everything works; AI explanations and the assistant fall back to
  knowledge-base text.
- The original single-page UI is still available at `/classic`; the v1 endpoint `/api/predict` still works.
- Frontend dev server with hot reload: `cd frontend && npm run dev` (proxies `/api` to :8000).

## What's inside

| Area | Where | Notes |
|---|---|---|
| API (FastAPI) | `app/server.py`, `app/api/v1/*` | Versioned `/api/v1`, OpenAPI at `/api/docs` (dev) |
| Auth & security | `app/core/security.py` | argon2id, server-side sessions, CSRF, RBAC, rate limits, audit log |
| Database | `app/db.py`, `alembic/` | SQLite (dev) / PostgreSQL (prod), Alembic migrations |
| Inference | `app/inference.py`, `app/services/inference_service.py` | Two-stage plant → disease, calibration, OOD rejection, Grad-CAM, CPU fallback |
| Knowledge base | `app/knowledge/` | 30 plants, ~150 diseases/pests, FRAC/IRAC groups, references — **no doses** |
| Products | `app/knowledge/products.json`, `tools/verify_products.py` | Listings verified against live store pages, dated |
| Assistant | `app/api/v1/assistant.py`, `app/services/rag.py`, `app/services/llm.py` | BM25 retrieval over the KB, Claude, output safety validator |
| Weather | `app/services/weather.py` | Open-Meteo forecast + seasonal disease-risk rules, cached |
| Web app (React + TS) | `frontend/` | Landing, auth, dashboard, diagnose, history, plants, library, assistant, weather, settings, admin |
| ML | `ml/`, `tools/` | Dataset audit + grouped split, training, calibration, OOD, evaluation, pest model |
| Ops | `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `scripts/backup.sh` | |

Documentation: [architecture](docs/architecture.md) · [API](docs/api.md) · [security](docs/security.md) ·
[ML model card](docs/model_card.md) · [datasets](docs/datasets.md) · [deployment & rollback](docs/deployment.md) ·
[MVP launch checklist](docs/launch_checklist.md)

## Tests

    PD_DEVICE=cpu .venv/bin/pytest -q            # backend: auth, IDOR, uploads, predictions, KB safety, admin
    cd frontend && npx vitest run                # components
    cd frontend && npx playwright test           # E2E in Chrome, desktop + mobile, axe WCAG AA checks

## Machine learning

    .venv/bin/python tools/fetch_extra.py        # field / Pakistan crop datasets (Hugging Face mirrors)
    .venv/bin/python tools/fetch_wheat.py        # wheat (NUST NWRD + John Innes)
    .venv/bin/python tools/fetch_pests.py        # IP102 insects
    .venv/bin/python ml/run_v3.py                # audit + grouped split → architecture comparison → full training
    .venv/bin/python tools/train_pests.py        # insect model
    .venv/bin/python tools/catalog.py            # data/catalog.json + docs/datasets.md

Model numbers are reported in [docs/model_card.md](docs/model_card.md) exactly as measured, including the
much lower accuracy on real field photos.
