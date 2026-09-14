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

See `backend/README.md` and `frontend/README.md` for contracts, configuration, and verification commands.
