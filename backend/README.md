# Vantage Backend — Transparent Research Runs

The backend executes durable, synchronous, end-of-day research runs for supported US-listed equities. It returns deterministic metrics, typed quality states, registered reasons, evidence provenance, version identifiers, and an optional bounded AI interpretation. It does not place trades or provide investment advice.

## Stack and boundaries

- FastAPI on Python 3.12, managed with `uv`
- PostgreSQL 17 through SQLAlchemy 2 and psycopg 3; Alembic owns schema changes
- Supabase Auth only for bearer-token identity; research data is stored in PostgreSQL
- Provider protocols in `app/providers/contracts.py`; the Phase 1 adapter is `YFinanceSnapshotProvider`
- LangGraph for the deterministic metrics → optional interpretation → policy workflow
- OpenTelemetry spans with allowlisted attributes and optional Langfuse v4 export

`yfinance` is suitable for development and research prototyping, not a licensed production market-data entitlement. The adapter verifies `quoteType=EQUITY`, a supported US exchange code, and USD currency before accepting data.

## API

All research routes require a valid Supabase bearer token.

- `POST /api/v1/research-runs` creates and completes one run synchronously
- `GET /api/v1/research-runs/{run_id}` retrieves an owner-scoped run
- `GET /api/v1/research-runs?limit=20&before=...` lists owner-scoped history

Errors use the shared `SafeError` envelope. The incompatible legacy `/api/v1/analyze` route is intentionally absent.

## Deterministic results

The metrics registry currently emits one-, five-, and twenty-session return; twenty-session annualized volatility; twenty-session maximum drawdown; twenty-session average dollar volume; accepted, missing, and duplicate price counts; accepted news count; and distinct publisher count.

Stale, invalid, or insufficient price series produce a typed `insufficient_data` result and skip the model (`model=not_run`). News or model failures degrade an otherwise usable run to `review` without discarding the deterministic metrics. Model-authored text may reference accepted evidence IDs but may not introduce numeric claims.

## Local configuration

Copy `.env.example` to `.env`. Required production values include Supabase credentials, separate database URLs, a high-entropy telemetry salt, and provider credentials for the selected LLM.

The database split is intentional:

- `MIGRATION_DATABASE_URL` connects as the DDL owner and is preferred for migrations.
- `DATABASE_URL` connects as the runtime role and remains the migration fallback when a separate owner URL is unavailable.
- `VANTAGE_RUNTIME_DB_ROLE` names the existing role that receives schema usage, table `SELECT`/`INSERT`/`UPDATE`, and sequence usage during migration.

Heroku's `postgres://` database URLs are normalized to SQLAlchemy's `postgresql+psycopg://` dialect. Heroku deployments run `alembic upgrade head` in a release phase using the built web image, before the new web process starts. Configure `MIGRATION_DATABASE_URL` with the DDL owner whenever possible; fallback migrations using `DATABASE_URL` require that role to have the necessary DDL privileges.

The initial migration revokes `PUBLIC` access. Its downgrade deliberately raises an error because research history is immutable. Roll back application code by deploying the prior application version; use a reviewed forward migration for schema corrections.

From the repository root, `docker compose up --build` creates the local owner/runtime roles, applies migrations, and then starts the API. For a manual backend setup:

```bash
uv sync --frozen
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

## Telemetry

`TRACE_EXPORT_ENABLED=false` keeps spans local and performs no Langfuse export. When enabled with `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST`, the Langfuse client registers its exporter on the same OpenTelemetry provider. Export is restricted to the Vantage instrumentation scope after attributes, exception events, and status descriptions are redacted. Raw tokens, emails, user IDs, provider payloads, and exception strings are not exported.

## Verification

Run from `backend/` with a PostgreSQL database whose name contains `vantage_test`:

```bash
uv run alembic upgrade head
uv run ruff check app tests migrations
uv run mypy app/domain app/services app/providers app/repositories app/telemetry app/api
uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=85
```
