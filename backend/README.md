# Vantage Backend — Transparent Research Run Engine

The Vantage backend provides an asynchronous, observable, and resilient research run engine for US equity end-of-day (EOD) market analysis.

> **Disclaimer**: Vantage is an analytical and educational research platform for US equities. It does NOT provide automated trade execution, broker integration, trading recommendations, or financial advice.

---

## Architecture Overview

- **Framework**: FastAPI (Python 3.12, managed with `uv`)
- **Database**: PostgreSQL with `psycopg` (v3) async/sync drivers and `SQLAlchemy` 2.0 / `Alembic`
- **Authentication**: Supabase Auth (JWT bearer token validation)
- **Market Data**: Protocol-driven snapshot abstraction (`MarketSnapshotProvider`), with `yfinance` as a development-only EOD adapter
- **LLM Synthesis**: Multi-provider LLM interface (`LLMProvider`) supporting Ollama (local GGUF), Google Gemini, and Groq with deterministic schema-based fallback
- **Observability**: Langfuse tracing with salted SHA-256 user pseudonymization and zero-leakage kill switch

---

## Quick Start & Local Setup

### 1. Prerequisites

- Python 3.12+
- `uv` package manager (`curl -LsSf https://astral.sh/uv/install.sh` or `winget install astral-sh.uv`)
- Docker (for local PostgreSQL)

### 2. Environment Configuration

Copy the sample environment file:

```bash
cp .env.example .env
```

Review and adjust variables in `.env`.

### 3. Disposable PostgreSQL Setup

Start a local PostgreSQL 17 container:

```bash
docker run -d \
  --name vantage-test-postgres \
  -e POSTGRES_USER=vantage_test \
  -e POSTGRES_PASSWORD=vantage_test \
  -e POSTGRES_DB=vantage_test \
  -p 5433:5432 \
  postgres:17-alpine
```

Create the migration owner role (for DDL privileges):

```bash
docker exec -i vantage-test-postgres psql -U vantage_test -d vantage_test << 'EOF'
CREATE ROLE vantage_owner WITH LOGIN PASSWORD 'vantage_owner' SUPERUSER;
GRANT ALL PRIVILEGES ON DATABASE vantage_test TO vantage_owner;
EOF
```

### 4. Database Connection Split

Vantage enforces strict separation of privilege between runtime application access and schema migrations:

- `DATABASE_URL`: Runtime connection string used by the application service for DML operations (`SELECT`, `INSERT`, `UPDATE`). Uses the `vantage_test` application role.
- `MIGRATION_DATABASE_URL`: Administrative connection string used exclusively by Alembic for DDL operations (`CREATE TABLE`, `ALTER TABLE`, `CREATE INDEX`). Uses the `vantage_owner` role.

```env
DATABASE_URL=postgresql+psycopg://vantage_test:vantage_test@localhost:5433/vantage_test
MIGRATION_DATABASE_URL=postgresql+psycopg://vantage_owner:vantage_owner@localhost:5433/vantage_test
```

### 5. Running Database Migrations

Apply database migrations:

```bash
uv run alembic upgrade head
```

#### Additive Rollback Policy
All schema migrations follow an **additive-only** evolution pattern:
- New features introduce new tables or nullable columns with default values.
- Existing columns and tables are never dropped or renamed in-place.
- Rollbacks are applied cleanly via `alembic downgrade -1` or by applying forward additive fixes, preserving existing data integrity.

### 6. Supabase Connection Boundaries

Supabase is used **strictly for identity and authentication** (issuing and verifying JWT bearer tokens).
- Vantage backend does **not** rely on Supabase database hosting, PostgREST, or proprietary Supabase client tables.
- All domain data (research runs, snapshots, interpretations, execution logs) resides in the standard PostgreSQL database managed via SQLAlchemy and Alembic.

---

## Market Data & Provider Selection

### Market Data Boundary (`MarketSnapshotProvider`)
- Market data ingestion is abstracted behind the `MarketSnapshotProvider` interface in `app/providers/market_data.py`.
- The included `YFinanceSnapshotProvider` is strictly for **development, testing, and research-only** EOD market snapshots.
- Production environments can swap in official licensed exchange data feeds (e.g. Polygon, Alpaca, IEX Cloud) without changing domain logic or the research graph.

### LLM Provider Selection (`LLMProvider`)
Configured via `LLM_PROVIDER` in `.env`:
- `ollama`: Local inference via Ollama (`OLLAMA_BASE_URL`, `OLLAMA_MODEL`)
- `gemini`: Google Gemini Cloud API (`GEMINI_API_KEY`, `GEMINI_MODEL`)
- `groq`: Groq Cloud API (`GROQ_API_KEY`, `GROQ_MODEL`)

#### Resilient Degradation Policy
If the selected LLM provider is unreachable, times out, or returns malformed output:
- The research run does **not** fail.
- Market data metrics, quality status, and valuation analysis complete successfully.
- An `InterpretationDegraded` state is generated with a safe fallback explanation code (e.g. `PROVIDER_UNAVAILABLE`, `TIMEOUT`, `MALFORMED_OUTPUT`).

---

## Telemetry & Observability

Observability is instrumented using Langfuse with strict privacy guarantees:

- **Kill Switch**: Set `TRACE_EXPORT_ENABLED=false` to completely disable trace export. All spans execute as local no-ops with zero network overhead.
- **PII Protection**: Raw user IDs and emails are never exported to trace backends. User identifiers are hashed using a salted SHA-256 digest (`hash(user_id + TELEMETRY_USER_SALT)`).
- **Langfuse Configuration**:
  ```env
  TRACE_EXPORT_ENABLED=true
  TELEMETRY_USER_SALT=your-secure-salt-value
  LANGFUSE_PUBLIC_KEY=pk-lf-...
  LANGFUSE_SECRET_KEY=sk-lf-...
  LANGFUSE_HOST=https://cloud.langfuse.com
  ```

---

## Legacy Compatibility Adapter

The legacy endpoint `POST /api/v1/analyze` is retained as a backward-compatible adapter:
- Accepts existing request payloads.
- Translates requests to research run executions internally.
- Maps the result to the legacy analysis schema so older clients continue to function without interruption.

---

## Testing & Verification

Run the comprehensive test suite:

```bash
# Run unit, integration, and contract tests with 85%+ coverage requirement
uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=85

# Lint and formatting check
uv run ruff check app tests migrations

# Static type checking
uv run mypy app/domain app/services app/providers app/repositories app/telemetry
```
