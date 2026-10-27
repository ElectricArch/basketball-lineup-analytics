"""Validate environment configuration without opening connections or loading .env."""
import os
import re
from urllib.parse import parse_qs, unquote, urlsplit

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
PLACEHOLDERS = ("replace", "change-me", "changeme", "example", "placeholder")

def _boolean(env, name, default=False):
    raw = env.get(name, str(default)).strip().lower()
    if raw not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError(name + " must be an explicit boolean")
    return raw in {"true", "1", "yes"}

def _number(env, name, default, low, high):
    try:
        value = int(env.get(name, str(default)))
    except ValueError:
        raise ValueError(name + " must be an integer") from None
    if not low <= value <= high:
        raise ValueError(name + " is outside its supported range")
    return value

def load_environment(env=None):
    env = os.environ if env is None else env
    mode = env.get("APP_ENV", "").strip()
    if mode not in {"local", "test", "production"}:
        raise ValueError("APP_ENV must explicitly be local, test, or production")
    secret = env.get("DJANGO_SECRET_KEY", "").strip()
    if len(secret) < 50 or len(set(secret)) < 8 or any(
        marker in secret.lower() for marker in PLACEHOLDERS
    ):
        raise ValueError("DJANGO_SECRET_KEY must be a generated server-side value")
    debug = _boolean(env, "DJANGO_DEBUG")
    if mode == "production" and debug:
        raise ValueError("Production debug mode is prohibited")
    url = env.get("DATABASE_URL", "").strip()
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise ValueError("DATABASE_URL is invalid") from None
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("DATABASE_URL must explicitly identify an independent PostgreSQL database")
    if parsed.fragment:
        raise ValueError("DATABASE_URL fragments are not supported")
    database = unquote(parsed.path.lstrip("/"))
    if "/" in database or not re.fullmatch(r"[A-Za-z0-9_]+", database):
        raise ValueError("DATABASE_URL database name is invalid")
    if mode in {"local", "test"} and parsed.hostname not in LOCAL_HOSTS:
        raise ValueError("Local/test databases must use an explicit loopback host")
    if mode == "test" and not (database.startswith("lineup_demo") and database.endswith("_test")):
        raise ValueError("Test mode requires a dedicated lineup_demo*_test database")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if any(len(values) != 1 for values in query.values()):
        raise ValueError("Duplicate database options are not supported")
    # Application code controls schema and resource options, not arbitrary URL options.
    if set(query) - {"sslmode", "sslrootcert", "sslcert", "sslkey"}:
        raise ValueError("Only explicit TLS database URL options are supported")
    if mode == "production":
        if query.get("sslmode") != ["verify-full"] or not query.get("sslrootcert", [""])[0]:
            raise ValueError("Production PostgreSQL requires verify-full and an explicit trusted CA")
    default_hosts = "localhost,127.0.0.1,[::1]" if mode != "production" else ""
    hosts = [v.strip() for v in env.get("DJANGO_ALLOWED_HOSTS", default_hosts).split(",") if v.strip()]
    if mode == "test" and "testserver" not in hosts:
        hosts.append("testserver")
    if not hosts or any(
        "*" in host or host.startswith(".") or
        not (re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", host) or host == "[::1]")
        for host in hosts
    ):
        raise ValueError("DJANGO_ALLOWED_HOSTS requires explicit hostnames without wildcards")
    origins = []
    default_origins = "http://localhost:4210,http://127.0.0.1:4210" if mode != "production" else ""
    for raw in env.get("CORS_ALLOWED_ORIGINS", default_origins).split(","):
        if not raw.strip():
            continue
        value = raw.strip().rstrip("/")
        try:
            origin = urlsplit(value)
            origin.port
        except ValueError:
            raise ValueError("CORS_ALLOWED_ORIGINS contains an invalid origin") from None
        if (origin.scheme not in {"http", "https"} or not origin.hostname or
            origin.username or origin.password or origin.path or origin.query or origin.fragment or
            "*" in value or (mode == "production" and origin.scheme != "https")):
            raise ValueError("CORS_ALLOWED_ORIGINS requires explicit supported origins")
        origins.append(value)
    trust_proxy = _boolean(env, "DJANGO_TRUST_PROXY")
    if trust_proxy and (mode != "production" or env.get("DJANGO_PROXY_CONFIRMATION") != "headers-stripped"):
        raise ValueError("Proxy trust requires an explicit verified production boundary")
    return {
        "mode": mode, "secret": secret, "url": url, "debug": debug,
        "hosts": hosts, "origins": origins, "database_name": database,
        "database_host": parsed.hostname, "database_port": port,
        "trust_proxy": trust_proxy,
        "connect_timeout": _number(env, "DB_CONNECT_TIMEOUT", 5, 1, 30),
        "statement_timeout": _number(env, "DB_STATEMENT_TIMEOUT_MS", 5000, 100, 30000),
        "connection_age": _number(env, "DB_CONN_MAX_AGE", 60 if mode == "production" else 0, 0, 600),
        "demo_confirmation": env.get("DEMO_DATABASE_CONFIRMED", ""),
    }

