"""Django settings of the Tuxedo Finance backend.

The backend serves a JSON API under ``/api/`` and the built React client for
every other path. Installation values come from the environment or from the
file named by ``TUXEDO_ENV_FILE`` (default: ``backend/.env``).
"""

import os
import sys
import zoneinfo
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.utils.csp import CSP
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Process variables take priority over the file, so CI and Docker stay explicit.
load_dotenv(dotenv_path=Path(os.environ.get("TUXEDO_ENV_FILE", BASE_DIR / ".env")), override=False)


def env_flag(name, default):
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


DEBUG = env_flag("DEBUG", "False")
ALLOW_SIGNUPS = env_flag("ALLOW_SIGNUPS", "True")
HTTPS = env_flag("HTTPS", "False")
# Attempts to sign in or sign up, for each address. The browser journeys raise
# it, because they create many users from one address.
AUTH_THROTTLE = os.environ.get("TUXEDO_AUTH_THROTTLE", "10/m").strip()

SECRET_KEY = os.environ.get("SECRET_KEY", "").strip()
if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY must be set in the environment.")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "ninja",
    "accounts",
    "banking",
    "ledger",
    "investments",
    "reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    # Serves the built client; security and CSP headers above apply to its files.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# Each installation owns its data directory. The default keeps development data
# inside the ignored ``backend/var/`` folder.
DATA_DIR = Path(os.environ.get("TUXEDO_DATA_DIR", BASE_DIR / "var"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
        "OPTIONS": {
            "init_command": "PRAGMA journal_mode=WAL;PRAGMA synchronous=NORMAL;",
            "timeout": 20,
            "transaction_mode": "IMMEDIATE",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# The client sends its language in Accept-Language. The server translates only
# validation and domain messages.
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("pt-br", "Português (Brasil)")]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True

# The financial time zone. ``config.clock`` reads today's date in this zone.
# Stored datetimes stay in UTC.
TIME_ZONE = os.environ.get("TUXEDO_TIME_ZONE", "America/Sao_Paulo").strip()
try:
    zoneinfo.ZoneInfo(TIME_ZONE)
except (zoneinfo.ZoneInfoNotFoundError, ValueError) as error:
    raise ImproperlyConfigured(
        f"TUXEDO_TIME_ZONE must be an IANA time zone name, for example "
        f"America/Sao_Paulo or UTC. {TIME_ZONE!r} is not a known time zone."
    ) from error
USE_TZ = True

# The built client. WhiteNoise serves its files from the site root; the
# fallback view in ``config.urls`` returns ``index.html`` for client routes.
CLIENT_DIR = Path(os.environ.get("TUXEDO_CLIENT_DIR", BASE_DIR.parent / "web" / "dist"))
WHITENOISE_ROOT = CLIENT_DIR if CLIENT_DIR.is_dir() else None
# In development a new build is served without a restart. In production the
# files are listed once at startup.
WHITENOISE_AUTOREFRESH = DEBUG
STATIC_URL = "static/"

# Scripts and styles come only from this installation. Inline style attributes
# stay allowed because the client positions windows and charts with them.
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],
    "font-src": [CSP.SELF],
    "img-src": [CSP.SELF, "data:"],
    "connect-src": [CSP.SELF],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
}

SESSION_COOKIE_SECURE = HTTPS
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = HTTPS
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_SSL_REDIRECT = HTTPS
SECURE_HSTS_SECONDS = 31536000 if HTTPS else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = HTTPS
SECURE_HSTS_PRELOAD = HTTPS
if HTTPS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Tests hash passwords with a fast algorithm and log only errors, so a run
# stays short and its output shows failures only.
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"
if TESTING:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LOG_LEVEL = "ERROR" if TESTING else os.environ.get("LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"app": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"}},
    # The level is on the handler: records that propagate from Django's own
    # loggers do not pass through the level of the root logger.
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "app", "level": LOG_LEVEL}
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
}
