"""
Django settings for the Payment Verification & Reconciliation Automation system.

All environment-specific values come from the ".env" file (see ".env.example"),
so the same code runs on a developer laptop and on the central office computer.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    """Read a string setting from the environment."""
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean setting ("true", "1", "yes" are truthy)."""
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    """Read a comma separated list setting."""
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = env("DJANGO_SECRET_KEY", "insecure-development-key-change-me")
if not DEBUG and SECRET_KEY.startswith("insecure"):
    raise RuntimeError("Set DJANGO_SECRET_KEY in .env before running with DJANGO_DEBUG=False.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Project apps (see docs/ARCHITECTURE.md)
    "apps.accounts",
    "apps.core",
    "apps.receipts",
    "apps.reconciliation",
    "apps.cards",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serves /static/ when DEBUG=False
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",  # CSP + no-store for private pages
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.app_context",
            ],
        },
    },
]

# --------------------------------------------------------------------------
# Database: SQLite for zero-setup development, PostgreSQL for production.
# --------------------------------------------------------------------------
if env("DB_ENGINE", "sqlite") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", "payment_reconciliation"),
            "USER": env("DB_USER", "postgres"),
            "PASSWORD": env("DB_PASSWORD"),
            "HOST": env("DB_HOST", "127.0.0.1"),
            "PORT": env("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {
                "timeout": 20,  # wait instead of failing when the import thread holds a write lock
                "init_command": "PRAGMA journal_mode=WAL;",  # readers do not block the writer
                "transaction_mode": "IMMEDIATE",
            },
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Authentication (BR: users cannot change or reset their own password)
# --------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.ActiveAwareBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home_redirect"
LOGOUT_REDIRECT_URL = "accounts:login"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

import sys  # noqa: E402

if "test" in sys.argv:
    # Tests create many users; a fast hasher keeps the suite quick. Never used outside "manage.py test".
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# --------------------------------------------------------------------------
# Internationalisation. The UI is English-only (project requirement).
# --------------------------------------------------------------------------
LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Kuala_Lumpur"
USE_I18N = False
USE_TZ = True

# --------------------------------------------------------------------------
# Static files
# --------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# --------------------------------------------------------------------------
# Security hardening (applies when DEBUG=False)
# --------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 8      # one working day
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", False)
    SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "0"))

# --------------------------------------------------------------------------
# Upload limits (REQ-F-1.3)
# --------------------------------------------------------------------------
MAX_UPLOAD_MB = 5
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_MB * 1024 * 1024
ALLOWED_STATEMENT_EXTENSIONS = (".csv", ".xlsx")
ALLOWED_CARD_FILE_EXTENSIONS = (".csv", ".xlsx")     # Customer service: file with the card numbers
CARD_BIN = "461699"                                  # every card number starts with this BIN (the Teller types the rest)
CARD_OTHERS_INCOME_RM = 30                           # "Others Income" per card collected by a customer, in the Excel report
# Uploaded customer PDFs (card activation) are kept here, outside the static folder; they are served only to signed-in users.
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "media/"

# --------------------------------------------------------------------------
# Business rules. Every number the matching engine uses lives here.
# --------------------------------------------------------------------------
NAME_WORD_MIN_SCORE = float(env("NAME_WORD_MIN_SCORE", "85"))      # RapidFuzz ratio of one name word (a small typo is allowed)
NAME_MATCH_MIN_WORDS = int(env("NAME_MATCH_MIN_WORDS", "2"))      # how many name words must be shared (account holder vs bank name)
# Which single mismatch sends a receipt to Review instead of Not found: any of "name", "amount", "reference". For now only "amount".
REVIEW_REASONS = tuple(env_list("REVIEW_REASONS", "amount"))
BANK_DATA_RETENTION_DAYS = int(env("BANK_DATA_RETENTION_DAYS", "31"))   # bank statement data is deleted after this many days
OFFLINE_TIMESTAMP_MAX_AGE_DAYS = 31                               # offline receipts older than this use server time
REFERENCE_MIN_LENGTH = int(env("REFERENCE_MIN_LENGTH", "6"))      # NFR-PERF-2 (frontend + backend)
REFERENCE_MAX_LENGTH = int(env("REFERENCE_MAX_LENGTH", "20"))
STATEMENT_HEADER_ROW = 4                                          # BR-5: header is on row 4 (rows 1-3 are preamble)
IMPORT_RUN_SYNC = False   # False: process imports in a background thread (progress bar); tests set True

# --------------------------------------------------------------------------
# Password reset by e-mail (Forgot password). The emailed link is valid for this many seconds.
# SITE_BASE_URL is the address users type in the browser; it is used to build the link inside the e-mail.
# --------------------------------------------------------------------------
PASSWORD_RESET_TIMEOUT = int(env("PASSWORD_RESET_MINUTES", "60")) * 60
SITE_BASE_URL = env("SITE_BASE_URL").rstrip("/")

# --------------------------------------------------------------------------
# Notifications (BR-7). In-app + browser notifications always; e-mail digest optional.
# --------------------------------------------------------------------------
NOTIFY_BY_EMAIL = env_bool("NOTIFY_BY_EMAIL", False)
EMAIL_HOST = env("EMAIL_HOST")
# With no EMAIL_HOST the mail is only printed in the server window (development). As soon as EMAIL_HOST is filled in, real SMTP is used
# automatically, so forgetting to change EMAIL_BACKEND can no longer make mail "disappear".
_default_backend = "django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST else "django.core.mail.backends.console.EmailBackend"
EMAIL_BACKEND = env("EMAIL_BACKEND", "") or _default_backend
if EMAIL_HOST and EMAIL_BACKEND.endswith("console.EmailBackend"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_TIMEOUT = 15
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "reconciliation@company.local")

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
