# Security

Target: OWASP ASVS level 1 for a public web app handling personal photos.

| Control | Implementation |
|---|---|
| Passwords | argon2id (`argon2-cffi`), min. 10 chars, common-password and email-in-password checks, automatic rehash |
| Sessions | 256-bit random token in `HttpOnly; SameSite=Lax; Secure` (prod) cookie; only SHA-256 stored; 14-day rolling expiry; revoked on logout, password change/reset, deactivation |
| CSRF | Double-submit: `pd_csrf` cookie must match `X-CSRF-Token` header on every state-changing request with a session |
| Account enumeration | Same error for wrong password / unknown email; same response for password-reset requests; constant-time dummy hash |
| Authorization | Role dependencies (`farmer`, `consultant`, `admin`); every user-data query is scoped by owner; "not found" and "not yours" both return 404 (tested) |
| Rate limits | Login 5/min per IP+email and 30/5 min per IP; register 10/h; predictions 30/min per user, guest scans/day per IP; assistant 20/min, 200/day; reset 5/h |
| Uploads | Streamed with size cap; type decided by decoding (JPEG/PNG/WebP only); truncated files and decompression bombs rejected; stored re-encoded (EXIF/GPS removed) under random keys; served only to the owner through authorised endpoints |
| Admin access to photos | Only for users who opted in ("Help improve the model"); every view is audit-logged |
| Injection | SQLAlchemy parameterised queries; React escapes output; assistant markdown rendered as text nodes (no HTML) |
| Headers | CSP (`default-src 'self'`, no inline scripts), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, HSTS in production |
| CORS | Closed (same origin). Optional allowlist via `PD_CORS_ORIGINS` |
| Secrets | Environment variables only (`.env` is git-ignored; `.env.example` documents them) |
| Audit | `audit_events`: register, login (success/failure), logout, password change/reset, email verification, account deletion, diagnosis deletion, admin role/status changes, model activation, admin image views |
| Privacy | Account deletion removes user, diagnoses, plants, conversations and stored images; guest scans are never stored |
| LLM safety | The model receives only KB text; outputs with dose-like quantities or ingredients not in the retrieved entries are discarded |
| Transport / at rest | TLS terminated by Caddy (Let's Encrypt); use managed PostgreSQL with encryption at rest and an S3 bucket with SSE (the S3 driver requests AES256) |
| Backups | `scripts/backup.sh` (pg_dump + image store, 14-day retention); restore steps in the script header |

Known gaps (tracked): malware scanning of uploads is not performed (images are re-encoded, which
removes active content); the rate limiter is per-process (move to Redis before running several
instances); no 2FA yet.
