"""One explicit environment-driven configuration; .env files are not loaded."""
from pathlib import Path
from app.configuration import load_environment

_CONFIG = load_environment()
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
APP_ENV = _CONFIG["mode"]
SECRET_KEY = _CONFIG["secret"]
DEBUG = _CONFIG["debug"]
ALLOWED_HOSTS = _CONFIG["hosts"]
CORS_ALLOWED_ORIGINS = _CONFIG["origins"]
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = False
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INSTALLED_APPS = [
    "whitenoise.runserver_nostatic",
    "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
    "django.contrib.messages", "django.contrib.staticfiles", "django.contrib.postgres",
    "rest_framework", "app.apps.AppsConfig", "corsheaders",
]
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "app.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "app.wsgi.application"
_db = dj_database_url.parse(_CONFIG["url"], conn_max_age=_CONFIG["connection_age"])
_db.setdefault("OPTIONS", {}).update({
    "connect_timeout": _CONFIG["connect_timeout"],
    "options": "-c search_path=app,public -c statement_timeout=" + str(_CONFIG["statement_timeout"]),
})
_db["CONN_HEALTH_CHECKS"] = True
_db["TEST"] = {"NAME": "lineup_demo_test"}
DATABASES = {"default": _db}
DEMO_DATABASE_CONFIRMED = _CONFIG["demo_confirmation"]
LINEUP_THROTTLE_RATE = "30/min"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "app.views.errors.safe_exception_handler",
    "NUM_PROXIES": 0,
}
CACHES = {"default": {
    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    "LOCATION": "lineup-demo-throttle",
    "OPTIONS": {"MAX_ENTRIES": 512},
}}
DATA_UPLOAD_MAX_NUMBER_FIELDS = 32
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_SSL_REDIRECT = APP_ENV == "production"
SESSION_COOKIE_SECURE = APP_ENV == "production"
CSRF_COOKIE_SECURE = APP_ENV == "production"
SECURE_HSTS_SECONDS = 3600 if APP_ENV == "production" else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
if _CONFIG["trust_proxy"]:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

