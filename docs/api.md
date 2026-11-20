# API

Interactive OpenAPI docs: `/api/docs` (enabled outside production, or with `PD_DOCS=1`).

Conventions: JSON bodies; cookie session + `X-CSRF-Token` header for writes; errors are
`{"error": {"code", "message", "request_id", "details?"}}`; lists are cursor-paginated
`{"items", "next_cursor", "total"}`; every response carries `X-Request-ID`.

| Method & path | Auth | Purpose |
|---|---|---|
| `POST /api/v1/auth/register` · `login` · `logout` | — / session | Account and session |
| `POST /api/v1/auth/verify` · `resend-verification` · `forgot` · `reset` · `password` | mixed | Email verification, password reset/change |
| `GET /api/v1/auth/session` | — | Who am I (no 401 noise) |
| `GET/PATCH/DELETE /api/v1/users/me` | session | Profile, preferences, delete account |
| `POST /api/v1/predictions` | optional | Diagnose an image (`file`, optional `crop`, `plant_id`, `save`) — guests are rate limited and not stored |
| `GET /api/v1/predictions` | session | History with `crop`, `status`, `q`, `date_from/to`, `plant_id`, cursor |
| `GET/PATCH/DELETE /api/v1/predictions/{id}` | owner | Detail, notes/feedback/plant link, delete |
| `GET /api/v1/predictions/{id}/image` · `heatmap` · `report.pdf` · `explanation` | owner | Private image, Grad-CAM, PDF, AI explanation |
| `GET /api/v1/predictions/export.csv` | session | CSV export |
| `POST /api/v1/pests/identify` | optional | Insect identification (IP102 model) |
| `GET /api/v1/crops` · `crops/resolve?q=` | — | Crops, supported flag; name resolution (Urdu/Roman Urdu) |
| `GET /api/v1/diseases` · `diseases/{label}` | — | Knowledge Center search and detail |
| `GET /api/v1/products?label=` | — | Verified listings + labelled search links |
| `GET /api/v1/weather?q=|lat&lon&crops=` | — | Forecast and disease-risk alerts (source + fetch time) |
| `GET/POST/PATCH/DELETE /api/v1/plants` | session | My Plants |
| `GET /api/v1/analytics/overview` | session | Dashboard statistics |
| `POST /api/v1/assistant/chat` · `GET conversations[/{id}]` | session | Grounded assistant |
| `GET /api/v1/admin/overview` · `users` · `models` · `predictions/review` · `datasets` · `audit` · `system` | admin | Administration |
| `PATCH /api/v1/admin/users/{id}` · `admin/predictions/{id}/review`, `POST admin/models/{id}/activate` | admin | Admin actions |
| `GET /api/v1/health/live` · `health/ready` · `meta` | — | Health and public model facts |
| `GET /api/v1/demo/samples` · `POST demo/{file}` | — | Landing-page demo on bundled samples |
| `POST /api/predict`, `GET /api/info` | — | v1 compatibility (classic UI) |
