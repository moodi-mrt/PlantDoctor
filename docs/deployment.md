# Deployment

## Recommended MVP hosting

One CPU VM (4 vCPU / 8 GB RAM; e.g. Hetzner CPX31, DigitalOcean 8 GB, AWS Lightsail) running
`docker compose --profile prod`, with managed PostgreSQL and an S3-compatible bucket when traffic grows.
CPU inference of the EfficientNet-class model is a few hundred ms per image (see the model card),
which is adequate for an MVP; **GPU hosting is not justified** until measured load requires it.

## Environments

`PD_ENV=development | staging | production`. Staging should mirror production with its own database,
bucket and domain (`staging.<domain>`), deployed from the `main` branch; production from tags.

## First deploy

    cp .env.example .env      # set PD_ENV=production, PD_PUBLIC_URL, PD_DB_URL, POSTGRES_PASSWORD,
                              # PD_COOKIE_SECURE=1, PD_REQUIRE_VERIFIED_EMAIL=1, SMTP_*, PD_ADMIN_EMAILS
    DOMAIN=plantdoctor.example.com docker compose --profile prod up -d --build
    docker compose logs -f app            # migrations run automatically; wait for "PlantDoctor ready"
    curl https://plantdoctor.example.com/api/v1/health/ready

## Releases and rollback

- CI builds and tests every push; tag a release (`v3.x.y`) to deploy. Images are tagged by git SHA.
- Migrations are forward-only and additive (expand → migrate code → contract in a later release), so the
  previous image keeps working against the new schema.
- Rollback: `git checkout <previous tag> && docker compose --profile prod up -d --build`
  (or re-deploy the previous image tag). Model rollback needs no deploy: Admin → Models → Activate.

## Operations

- Health: `/api/v1/health/live` (process) and `/api/v1/health/ready` (DB + model) — used by the Docker
  HEALTHCHECK and any uptime monitor.
- Logs: JSON lines on stdout (`PD_LOG_JSON=1`) with `request_id`, path, status, latency, user id —
  ship to any log service; errors include stack traces server-side only.
- Error tracking: unhandled exceptions are logged with request id; add Sentry via its ASGI middleware if desired.
- Backups: `scripts/backup.sh` nightly via cron; test a restore monthly.
- Scaling out: move rate limiting to Redis, use S3 storage, then run more app instances behind the proxy.
