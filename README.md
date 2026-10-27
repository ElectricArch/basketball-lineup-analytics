# Lineup Explorer

An Angular dashboard compares basketball lineups from a small, independently
authored synthetic dataset. Django REST Framework aggregates PostgreSQL
possessions into canonical lineups of one to five players. The dashboard retains
reactive filters, sorting, comparison metrics, summary cards, and loading, error,
and empty states.

This repository is maintained as a personal portfolio showcase.
No project-wide open-source license is granted. Third-party
dependencies retain their respective licenses; see
[third-party notices](THIRD_PARTY_NOTICES.md).

## Project Background

This project was originally developed as a take-home technical assessment for a Software Engineering internship application.

I subsequently adapted it into an independent portfolio project, retaining the core basketball analytics functionality while improving security, configuration management, database isolation, dependency maintenance, and automated testing.

The portfolio version uses independently generated synthetic data and operates without access to the original project's database, credentials, or deployment infrastructure.

This repository represents an independently maintained technical showcase, not an official product or affiliated service.

## Architecture and requirements

- `backend/app/dbmodels/` and `migrations/`: UUID models and PostgreSQL arrays.
- `backend/app/helpers/lineups.py`: possession aggregation and metric formulas.
- `backend/app/views/`: anonymous, read-only JSON API with provisional bounds.
- `backend/app/demo_data.py`: deterministic 3-team, 21-player, 3-game,
  36-possession fixture; `load_demo_data` inserts it safely into confirmed targets.
- `frontend/src/app/lineups-summary/`: comparison dashboard and typed services.
- `frontend/server.js`: Express static server with SPA fallback and `/api` refusal.

Runtime pins: Python 3.13.5, Node 22.23.3, npm 10.9.9. Automated local validation
used PostgreSQL 16.15. Locked frontend versions
include Angular 21.2.25, CLI/build 21.2.28, Material/CDK 21.2.14, TypeScript
5.9.3, and RxJS 7.8.2. Backend pins include Django 5.2.18, DRF 3.18.3, and
sqlparse 0.6.0. Express 4.22.3 serves the production frontend; Gunicorn is retained
for a compatible Unix backend deployment.

## Local setup

Use a **new disposable PostgreSQL instance**, not an existing application or
valuable database. Never inherit an unknown connection URL. The commands below
match the automated disposable-instance validation described below. Use an
independent local port, such as 55432, for that new instance.
Bind it only to loopback, use independently generated credentials, and confirm
its data directory before executing any SQL. Provision authentication through
your local PostgreSQL tooling; no password belongs in source or shell history.

From the root, create the isolated Python environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple --only-binary=:all: --disable-pip-version-check pip==26.2.2
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: --disable-pip-version-check -r backend/requirements.txt
cd frontend
npm ci --ignore-scripts
cd ..
```

The lockfile includes dependencies with install hooks. The initial installation
uses `--ignore-scripts`; if a platform binary requires a hook, review that exact
package and hook before authorizing it. Do not reuse another project's dependency
directory. On Unix, use `.venv/bin/python` for subsequent Python commands.

In `psql`, connected **only to the newly provisioned local instance** as its
administrator, create independent roles and databases. Set each role's password
with the interactive `\password` prompt, rather than embedding it in this file:

```sql
CREATE ROLE lineup_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE lineup_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE DATABASE lineup_demo OWNER lineup_migrator;
CREATE DATABASE lineup_demo_test OWNER lineup_migrator;
```

Use explicit `-h 127.0.0.1 -p 55432 -U lineup_migrator -d lineup_demo` options
with `psql -X -v ON_ERROR_STOP=1 -f backend/scripts/init_local_db.sql` from the
root. Run the same initialization against `lineup_demo_test` before testing.
The script creates `app` before migrations and removes public-schema CREATE
permission. Its database-name guard is an additional precaution, not proof that
an instance is disposable. It does not create or reset a database.

Set environment variables in the current backend process; `.env.example` is a
reference and **no `.env` loader is installed**. Required values:

| Variable | Meaning |
|---|---|
| `APP_ENV` | Explicit `local`, `test`, or `production` |
| `DJANGO_SECRET_KEY` | Independently generated, diverse value of at least 50 characters |
| `DATABASE_URL` | Explicit PostgreSQL URI for the new target; local/test host must be loopback |
| `DJANGO_DEBUG` | Defaults false; production true is rejected |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated exact hosts; production requires an explicit list |
| `CORS_ALLOWED_ORIGINS` | Exact origins; local defaults allow loopback port 4210; production HTTPS only |
| `DEMO_DATABASE_CONFIRMED` | Must exactly match the disposable database name when loading fixtures |
| `DB_CONNECT_TIMEOUT` | Seconds, default 5, supported range 1-30 |
| `DB_STATEMENT_TIMEOUT_MS` | Default 5000, supported range 100-30000 |
| `DB_CONN_MAX_AGE` | Default 0 locally, 60 in production; supported range 0-600 |
| `DJANGO_TRUST_PROXY` | Defaults false; enable only after verifying the actual proxy boundary |
| `DJANGO_PROXY_CONFIRMATION` | `headers-stripped` acknowledges that verified boundary |

Generate the signing key in process, for example
`$env:DJANGO_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"`.
Do not print or commit the resulting value. Supply a connection URI privately
with properly encoded independently generated credentials. Test-mode database
names must start with `lineup_demo` and end with `_test`. The loader additionally
requires a `lineup_demo` prefix, local/test mode, and exact confirmation.

From `backend/`, with local settings and the migration-role connection to
`lineup_demo`, the intended workflow is:

```powershell
..\.venv\Scripts\python.exe manage.py migrate --noinput
..\.venv\Scripts\python.exe manage.py load_demo_data
```

The loader validates records, locks all four application tables, and inserts
transactionally. An exact fixture is a no-op; any conflicting application data
is refused. It offers no reset, delete, or force-overwrite option. After migration
and loading, grant only these application reads as the migration role:

```sql
GRANT CONNECT ON DATABASE lineup_demo TO lineup_reader;
GRANT USAGE ON SCHEMA app TO lineup_reader;
GRANT SELECT ON app.team, app.game, app.player, app.possession TO lineup_reader;
ALTER ROLE lineup_reader IN DATABASE lineup_demo SET default_transaction_read_only = on;
```

Switch the backend to the independent reader-role connection for serving. Keep
migration credentials out of the running web process. Start from `backend/`:

```powershell
..\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8010 --noreload
```

From `frontend/`, `npm start` is configured for `http://127.0.0.1:4210` and the
development backend is `http://127.0.0.1:8010`. These startup and browser steps
remain unverified here.

## API and metrics

`GET /api/v1/lineups` returns an array of lineup summaries. Parameters are
`lineup_size` (1-5), `team_id`, `player_id`, `min_possessions`, `sort_by`,
`sort_order` (`asc`/`desc`), and `limit`. Supported sort fields are total,
offensive, or defensive possessions; offensive, defensive, or net rating;
offensive/defensive effective shooting and rebound percentages; and offensive
or opponent turnover rate. Sorting ties use canonical team/player IDs.

Missing, invalid, zero, or negative HTTP limits use 100; larger limits clamp to
100. Dashboard choices are 10/25/50/100, with 25 selected initially. Its player
catalog requests one-player lineups with limit 100; all 21 synthetic players fit.
The default five-player minimum of 10 possessions has three fixture lineups.

Ratings are points per 100 side-specific possessions; net rating subtracts
defensive rating. Shooting and rebound rates use aggregated counts, and zero
denominators return zero. An unobserved side's zero is not measured performance.
Summary cards compare only the current returned results, so filters and output
limits affect their population.

Requests have query-length, parameter-count, and value-width limits. Before
aggregation, the service checks at most 1000 possessions, 96 players, 8 teams,
and distinct, known five-player sides. It refuses larger/unsupported datasets.
One aggregation runs at a time per process; busy requests return 503. A local
in-memory, per-process throttle allows 30 requests/minute per direct peer and
returns 429. Forwarded client-IP headers are ignored. These provisional controls
are neither global rate limiting nor demonstrated denial-of-service resistance.
The internal aggregation helper can still be unbounded. Use immutable demo data
and gateway limits for hosting; concurrent data changes could invalidate a guard.

## Validation status and commands

Automated validation completed on 2026-10-27 with the pinned runtimes, a fresh
isolated PostgreSQL cluster and synthetic data:

- All 60 backend tests and five additional API/Host/CORS/parser checks passed.
- Migrations and fixture loading passed on first and repeat runs. The explicit
  `lineup_demo_test` database was used with serial `--keepdb` testing.
- Reader-role SELECT passed; an INSERT was refused even after disabling the
  role's default read-only transaction setting.
- A fresh hooks-disabled npm installation, TypeScript compilation, production
  Angular build, compiled-output scan and Express route/API smoke checks passed.
- npm production/all audits and metadata checks for all 18 installed Python
  distributions reported zero entries, with no Python lookup failures. These
  dated feed results are limited assurance, not proof that no vulnerability exists.
- Owned Express and disposable PostgreSQL shutdown were verified.

From `backend/`, after dependencies and a confirmed new disposable demo/test
schema are provisioned, run:

```powershell
..\.venv\Scripts\python.exe -m pip check
..\.venv\Scripts\python.exe manage.py check
..\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
..\.venv\Scripts\python.exe manage.py test app.tests --keepdb --noinput --parallel 1
```

From `frontend/`, run `npm ci --ignore-scripts`,
`npx --no-install tsc -p tsconfig.app.json --noEmit` and `npm run build`.
The scoped Undici override patches the Angular build tool's pinned dependency.
The scoped Vitest override constrains an unused optional peer for npm 10
compatibility; this project does not install or configure Vitest/browser tooling.
The lockfile is consistent with the manifest and was verified by clean install.

Manual browser checks remain pending: real filters/catalog/rendering, debounce
and cancellation, loading/error/empty/retry/offline states, responsive layout,
and the production blank-backend no-request behavior. Build/static HTTP checks
do not establish those observations. Local HTTPS/static-directory warnings and
hosted Gunicorn/TLS/proxy/resource behavior remain separate deployment concerns.
HEAD currently performs the same eight database queries as GET and should not be
used as a zero-work health endpoint.

## Independent deployment prerequisites

Production frontend configuration intentionally has an empty backend address.
Set `frontend/src/environments/environment.prod.ts` to an independent HTTPS
backend origin before building. That public origin is bundled configuration;
never put signing keys or database configuration in browser code. Invalid or
empty configuration fails before the service issues an HTTP request.

The retained Railway JSON files contain generic build/start instructions, not
account identifiers or a database attachment. Configure a fresh service and
database independently. Provision `app`, run migrations as its owner separately,
load synthetic data in a confirmed local/test preparation environment, and serve
through a restricted reader role. Production connections require
`sslmode=verify-full` and an explicit trusted `sslrootcert`. Confirm certificate,
timeout, hostname, and proxy behavior on the actual independent target.

Gunicorn uses one sync worker with a 15-second timeout; local semaphores and
throttles remain per process. Supply gateway request/rate/concurrency limits,
resource budgets, HTTPS, trusted proxy header stripping, and monitoring. Verify
TLS redirects before exposing the service. Express serves the built Angular
routes; `/api` on that server returns JSON 404 rather than SPA HTML. For local
Express validation, the harness sets `HOST=127.0.0.1`; `HOST` accepts a literal
IP address. Without it, Express retains its normal deployment bind behavior.

Public hosting is optional and requires separate validation of the deployed TLS,
proxy, static-file, and resource controls.
