"""Runtime settings, read from environment variables (and an optional .env file).

Secrets (ANTHROPIC_API_KEY, SMTP password, S3 keys) are only ever read from the environment.
See .env.example for every variable.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


def _bool(name, default):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


ENV = os.environ.get("PD_ENV", "development")          # development | staging | production | test
IS_PROD = ENV in ("production", "staging")
PUBLIC_URL = os.environ.get("PD_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")

DATA_DIR = Path(os.environ.get("PD_DATA_DIR", ROOT / "data"))
DB_URL = os.environ.get("PD_DB_URL", f"sqlite:///{DATA_DIR / 'app.db'}")

# Storage: "local" (DATA_DIR/uploads) or "s3" (any S3-compatible bucket).
STORAGE = os.environ.get("PD_STORAGE", "local")
UPLOAD_DIR = Path(os.environ.get("PD_UPLOAD_DIR", DATA_DIR / "uploads"))
S3_BUCKET = os.environ.get("PD_S3_BUCKET", "")
S3_ENDPOINT = os.environ.get("PD_S3_ENDPOINT") or None
MAX_UPLOAD_MB = int(os.environ.get("PD_MAX_UPLOAD_MB", "15"))
MAX_IMAGE_PIXELS = int(os.environ.get("PD_MAX_IMAGE_PIXELS", str(40_000_000)))

# Sessions / auth
SESSION_COOKIE = "pd_session"
CSRF_COOKIE = "pd_csrf"
SESSION_DAYS = int(os.environ.get("PD_SESSION_DAYS", "14"))
COOKIE_SECURE = _bool("PD_COOKIE_SECURE", IS_PROD)
REQUIRE_VERIFIED_EMAIL = _bool("PD_REQUIRE_VERIFIED_EMAIL", IS_PROD)
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("PD_ADMIN_EMAILS", "").split(",") if e.strip()}
GUEST_SCANS_PER_DAY = int(os.environ.get("PD_GUEST_SCANS_PER_DAY", "3"))

# Email: "console" (dev: printed to log + data/outbox) or "smtp".
EMAIL_BACKEND = os.environ.get("PD_EMAIL_BACKEND", "console")
SMTP_HOST = os.environ.get("PD_SMTP_HOST", "localhost")
SMTP_PORT = int(os.environ.get("PD_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("PD_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("PD_SMTP_PASSWORD", "")
SMTP_TLS = _bool("PD_SMTP_TLS", True)
EMAIL_FROM = os.environ.get("PD_EMAIL_FROM", "PlantDoctor <no-reply@localhost>")

# CORS: same-origin by default. Comma-separated allowlist only if the SPA is hosted elsewhere.
CORS_ORIGINS = [o.strip() for o in os.environ.get("PD_CORS_ORIGINS", "").split(",") if o.strip()]

# Claude API: optional. Without credentials the app serves the curated knowledge base text only.
CLAUDE_MODEL = os.environ.get("PD_CLAUDE_MODEL", "claude-opus-5-5")
LLM_ENABLED = _bool("PD_LLM", True)

# Weather (Open-Meteo, no key needed)
DEFAULT_LOCATION = os.environ.get("PD_DEFAULT_LOCATION", "Lahore")
WEATHER_TTL_S = int(os.environ.get("PD_WEATHER_TTL", "3600"))
LLM_TTL_S = int(os.environ.get("PD_LLM_TTL", str(30 * 24 * 3600)))

MODEL_PATH = Path(os.environ.get("PD_MODEL", ROOT / "models" / "plantdoctor_effnetb0.pt"))
PEST_MODEL_PATH = Path(os.environ.get("PD_PEST_MODEL", ROOT / "models" / "pest_efficientnet_b0.pt"))
LOAD_MODELS = _bool("PD_LOAD_MODELS", True)   # tests can disable
DEVICE = os.environ.get("PD_DEVICE", "auto")   # auto | cpu | cuda

LOG_JSON = _bool("PD_LOG_JSON", IS_PROD)
LOG_LEVEL = os.environ.get("PD_LOG_LEVEL", "INFO")

for d in (DATA_DIR, UPLOAD_DIR):
    d.mkdir(parents=True, exist_ok=True)
