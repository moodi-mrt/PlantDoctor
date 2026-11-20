# MVP launch checklist

- [ ] `.env` production values set; `PD_COOKIE_SECURE=1`, `PD_REQUIRE_VERIFIED_EMAIL=1`, real SMTP, admin email
- [ ] Domain + TLS (Caddy) working; HSTS header present
- [ ] `/api/v1/health/ready` green; uptime monitor configured
- [ ] Backups scheduled and one restore tested
- [ ] Active model version reviewed in Admin → Models; field accuracy and limits shown on the landing page
- [ ] Knowledge base reviewed by an agronomist (Pakistan-registered actives per crop)
- [ ] Product listings re-verified (`tools/verify_products.py`) within the last 30 days
- [ ] Privacy notice and terms published; image-sharing opt-in defaults to off
- [ ] Claude API key set (optional) and monthly spend limit configured
- [ ] Feedback loop: review queue triaged weekly; mislabeled cases fed into the next dataset version
- [ ] Support contact published; extension-office referral text checked for each province
