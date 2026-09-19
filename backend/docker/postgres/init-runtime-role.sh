#!/bin/sh
# Bootstraps the least-privilege runtime application role (vantage_runtime).
#
# This script runs once, on first initialization of an empty PostgreSQL data
# directory, via /docker-entrypoint-initdb.d/. The role's password is never
# hardcoded here: it is supplied externally through POSTGRES_RUNTIME_PASSWORD
# and passed to psql as a bound variable, never interpolated into shell text.
#
# Schema/table privileges for this role are granted separately by the Alembic
# migrations (see VANTAGE_RUNTIME_DB_ROLE), not by this script — it only
# creates the role with LOGIN and a password.
#
# Development-only note: docker-compose.yml provides a placeholder default
# for POSTGRES_RUNTIME_PASSWORD so the stack starts out of the box. That
# default is not a production credential; deployed environments must supply
# their own value from a managed secret store, never this file or its
# fallback.
set -eu

: "${POSTGRES_RUNTIME_PASSWORD:?POSTGRES_RUNTIME_PASSWORD must be set to bootstrap the runtime role}"

psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --no-password \
    --set=runtime_password="$POSTGRES_RUNTIME_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE vantage_runtime LOGIN PASSWORD %L', :'runtime_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vantage_runtime')
\gexec
SQL
