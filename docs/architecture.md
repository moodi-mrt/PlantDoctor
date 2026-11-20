# Architecture

## System

```
Browser — React SPA (Vite build, served by FastAPI; mobile-first)
   │  same-origin HTTPS · HttpOnly session cookie + CSRF header
   ▼
FastAPI app (uvicorn, one process per host)
   ├─ middleware: request-id · JSON access log · security headers/CSP · error envelope
   ├─ /api/v1 routers: auth · users · predictions · pests · crops · diseases · products
   │                   weather · plants · analytics · assistant · admin · health · meta · demo
   ├─ services: inference (model registry, GPU lock, CPU fallback) · kb · rag · llm · weather
   │            products · storage · images · email · audit · report_pdf · seed · cache
   ▼
SQLAlchemy 2 + Alembic ── SQLite (dev) / PostgreSQL 16 (prod)
Storage driver ────────── local disk (dev) / S3-compatible bucket (prod), private keys
External ──────────────── Claude API (optional) · Open-Meteo (cached 1 h)
```

**Decisions** (see ADRs below):

1. **Monolith with an inference service boundary.** Inference costs ~0.1 s on a GPU and a few
   hundred ms on CPU; the model is ~16–35 MB. A separate inference service, Redis or Celery would
   add operational cost without a measured need. `InferenceService.analyze()` is the seam to split
   out later.
2. **Curated knowledge base as files, mirrored to the DB.** Treatment advice must be reviewable and
   versioned like code; `app/services/seed.py` mirrors it into tables for querying.
3. **The LLM never diagnoses.** The vision model produces the diagnosis; Claude only rewrites
   retrieved KB text, and a validator rejects doses or active ingredients that are not in the
   retrieved entries (falls back to KB text).
4. **Honest uncertainty over coverage.** Two-stage plant → disease, temperature-scaled
   probabilities, Mahalanobis OOD rejection, and `needs_input` / `unknown` / `unsupported_crop`
   statuses instead of forced answers. Severity is computed but not shown (not validated).

## Prediction flow

1. Upload is streamed with a 15 MB cap, decoded by Pillow (type is sniffed, not trusted),
   decompression bombs refused, quality checked (blur, exposure, resolution).
2. If the user typed a plant, the name is resolved (English / Urdu / Roman Urdu / scientific).
3. Model: test-time augmentation (centre + whole image, mirrored) → temperature-scaled probabilities.
   OOD score > threshold → `unknown`. Else crop probability = sum over that crop's classes; low or
   close → `needs_input` (ask the plant name). Disease = renormalised within crop; < 40 % → `uncertain`,
   < 70 % → `tentative`.
4. Grad-CAM on the final class; stored privately with the photo (EXIF stripped).
5. Response joins the KB entry (symptoms, causes, plan, references) and expert-help contacts.

## Data model

`users`, `sessions` (hashed tokens), `auth_tokens`, `organizations`/`memberships` (future),
`crops`, `diseases`, `treatments`, `products`, `external_sources`, `datasets`, `model_versions`,
`images`, `diagnoses` (model version, class, status, confidence, full result JSON, feedback, admin
review), `plants`, `assistant_conversations`/`assistant_messages`, `audit_events`, `api_cache`.
See `app/db.py` and `alembic/versions/`.

## ADRs

- **ADR-1 FastAPI monolith, no microservices** — single deployable, horizontal scaling by running more
  instances behind a load balancer once the in-memory rate limiter is moved to Redis.
- **ADR-2 React + TypeScript SPA** — replaced the vanilla JS page because the product needs ~15 routes,
  auth, admin and component tests; served by FastAPI so cookies stay same-origin. Classic UI kept at `/classic`.
- **ADR-3 Server-side sessions over JWT** — instant revocation (logout, password change, deactivation).
- **ADR-4 SQLite dev / PostgreSQL prod** — same ORM models and migrations; CI runs the suite on PostgreSQL.
- **ADR-5 BM25 retrieval, no vector DB** — ~180 short curated documents; lexical retrieval is accurate,
  explainable and dependency-free.
- **ADR-6 Grouped data split** — PlantVillage has several shots per leaf; random file splits leak.
