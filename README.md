# Vantage

Vantage is a transparent, traceable research assistant for end-of-day US-listed equity analysis. Phase 1 produces deterministic metrics and provenance-backed quality/reason records, with optional bounded model interpretation. It does not execute trades or provide investment advice.

## Run the local stack

Prerequisites: Docker 24+ with Compose v2. Copy the backend/frontend example environment files or export real Supabase and model-provider values before authenticating users.

```bash
docker compose up --build
```

Compose starts PostgreSQL 17, creates separate migration-owner and runtime roles, applies Alembic migrations, starts FastAPI at `http://localhost:8000`, and serves the frontend at `http://localhost:5173`. The root backend health check is `http://localhost:8000/`.

The default Supabase values are non-secret placeholders that allow containers to start; authentication requires real `SUPABASE_URL` and `SUPABASE_KEY` values. The default local runtime database password is development-only and must be replaced by an externally managed secret in deployed environments.

Ollama is optional and profile-gated:

```bash
docker compose --profile local up --build
```

Stop services without deleting data:

```bash
docker compose down
```

Deleting volumes also deletes the local PostgreSQL research history and Ollama models; only use `docker compose down -v` when that data is intentionally disposable.

## What CI verifies

Each CI job proves something different. A mocked browser flow, a container smoke test, and live-provider QA are three distinct kinds of verification and none substitutes for another:

- **Backend Tests & Quality Gates** — backend tests, lint, types, and the coverage gate against a PostgreSQL 17 service container.
- **Frontend Tests, Lint & Build** — Vitest unit tests, ESLint, and a production Vite build.
- **Mocked Browser Journey (Playwright, dev server)** — the browser journey against the Vite development server with Supabase auth and the research API replaced by Playwright route mocks. It checks user-visible behaviour only; no backend, database, or provider is involved.
- **Production Container Smoke Test** — builds the backend and frontend images, starts PostgreSQL on a fresh volume, applies Alembic migrations in a container, confirms the backend health endpoint answers and that Nginx serves the `/app` deep link, then replays the same route-mocked browser journey against the running images. This proves the production images build, migrate, start, and serve their routes. It does not exercise the API end to end: Supabase and the research API remain mocked in the browser.

No CI job contacts Supabase, a market-data provider, a model provider, or Langfuse. CI runs with `LLM_PROVIDER=disabled` and `TRACE_EXPORT_ENABLED=false`. Verifying behaviour against live providers is manual QA and is deliberately outside CI.

See `backend/README.md` and `frontend/README.md` for contracts, configuration, and verification commands.
