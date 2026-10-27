-- psql only; explicitly provision a new disposable local database first.
-- This name guard supplements that operational boundary; it does not prove disposal.
\set ON_ERROR_STOP on
SELECT left(current_database(), length('lineup_demo')) = 'lineup_demo' AS confirmed_demo_name \gset
\if :confirmed_demo_name
BEGIN;
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION CURRENT_USER;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
COMMIT;
\else
-- ON_ERROR_STOP makes this a script failure (psql exit 3), not a successful quit.
DO $refuse$
BEGIN
    RAISE EXCEPTION 'Refusing schema initialization outside a lineup_demo database.';
END;
$refuse$;
\endif
