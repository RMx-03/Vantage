# Vantage

Vantage is a transparent, traceable research assistant for end-of-day US-listed equity analysis. Each research run produces deterministic metrics and provenance-backed quality and reason records, with an optional bounded model interpretation. It does not execute trades or provide investment advice.

Accounts are first-party: email and password, with email verification and password reset, issued and checked by the Vantage backend itself. There is no third-party identity provider.

## Layout

| Path | Contents |
|---|---|
| `backend/` | FastAPI API, PostgreSQL schema (Alembic), research workflow, authentication, email. See [backend/README.md](backend/README.md). |
| `frontend/` | React workspace: sign-in, research terminal, run history, settings. See [frontend/README.md](frontend/README.md). |
| `docker-compose.yml` | Local stack: PostgreSQL, migrations, backend, frontend, and optional Ollama. |
| `heroku.yml` | Backend container build and release-phase migration for Heroku. |
| `frontend/vercel.json` | Vercel rewrite that proxies `/api/*` to the Heroku backend. |

## Run the local stack

Prerequisites: Docker 24+ with Compose v2.

Compose reads its configuration from a `.env` file in the **repository root**, not from `backend/.env` or `frontend/.env`. Create it from the example and fill in the two required secrets:

```bash
cp .env.example .env
openssl rand -hex 32   # paste as AUTH_JWT_SECRET
openssl rand -hex 32   # paste as TELEMETRY_USER_SALT (a different value)
```

The backend refuses to start if either value is missing, shorter than 32 bytes, or looks like a placeholder. That is deliberate: a running API with a weak signing secret would issue forgeable tokens.

```bash
docker compose up --build
```

Compose starts PostgreSQL 17, creates separate migration-owner and runtime roles, applies Alembic migrations, starts FastAPI at `http://localhost:8000`, and serves the frontend at `http://localhost:5173`. The backend health check is `http://localhost:8000/`.

The default database passwords are development-only and must be replaced by externally managed secrets in deployed environments.

Ollama is optional and profile-gated. The profile starts Ollama but does not select it; set `LLM_PROVIDER=ollama` as well:

```bash
docker compose --profile local up --build
```

Stop services without deleting data:

```bash
docker compose down
```

`docker compose down -v` also deletes the local PostgreSQL data (accounts and research history) and Ollama models. Use it only when that data is disposable.

### Email in local development

By default `EMAIL_PROVIDER=noop`: the backend logs that a message would have been sent and sends nothing. The verification or reset link is **not** logged, because a link in a log file is a usable credential.

To use a local account for research without real email, mark it verified directly in the local database:

```bash
docker compose exec postgres psql -U vantage_owner -d vantage -c \
  "UPDATE vantage_auth.users SET email_verified_at = now() WHERE email = 'you@example.com';"
```

Addresses are stored lowercased. Sign out and back in afterwards so the new access token carries the verified state.

To send real email through Brevo, add these to the root `.env` and restart the backend:

| Variable | Value |
|---|---|
| `EMAIL_PROVIDER` | `brevo` |
| `BREVO_API_KEY` | A Brevo **API** key (`xkeysib-…`). An SMTP key (`xsmtpsib-…`) is rejected by the API with 401. |
| `EMAIL_FROM` | A sender verified in the Brevo account, such as `Vantage <you@example.com>` |
| `APP_BASE_URL` | Where links in emails point; `http://localhost:5173` locally |

With `EMAIL_PROVIDER=brevo`, the backend refuses to start without a key or with the placeholder sender. Test only with addresses you control: sending to disposable inboxes can get a Brevo account suspended.

### Troubleshooting: backend exits at startup

Read the backend log (`docker compose logs backend`). Every startup refusal names the setting at fault, for example `AUTH_JWT_SECRET must be at least 32 bytes; refusing to start.` Fix that value in the root `.env` and run `docker compose up -d backend`.

### Troubleshooting: `role "vantage_runtime" does not exist`

The PostgreSQL container bootstraps its least-privilege runtime role from
`backend/docker/postgres/init-runtime-role.sh`. A checkout with CRLF line endings breaks
that script's shebang, so the role is never created and the migration fails. `.gitattributes`
keeps `*.sh` at LF for new clones, but an existing clone made with `core.autocrlf=true`
still holds the CRLF copy. Fix it once with:

```bash
git add --renormalize . && git checkout -- backend/docker/postgres/init-runtime-role.sh
```

Then recreate the database volume (`docker compose down --volumes`) so the initializer runs again.

## Deployment

The frontend is hosted on Vercel and the backend on Heroku. Vercel rewrites `/api/*` to the Heroku app, so the browser talks to a single origin. The refresh-token cookie is therefore first-party and the API needs no cross-origin credentials.

The backend is built from `backend/Dockerfile` via `heroku.yml`. The release phase runs `alembic upgrade head` before the new web process starts. Behind Vercel and the Heroku router, set `TRUSTED_PROXY_HOPS=2` so rate limits key on the real client address rather than a proxy's. See [backend/README.md](backend/README.md) for the full configuration.

## What CI verifies

Each CI job proves something different. A mocked browser flow, a container smoke test, and live-provider QA are three distinct kinds of verification and none substitutes for another:

- **Backend Tests & Quality Gates** — backend tests, lint, format, types, and the coverage gate against a PostgreSQL 17 service container.
- **Frontend Tests, Lint & Build** — dependency audit, Vitest unit tests with coverage, ESLint, the design-system check, and a production Vite build.
- **Mocked Browser Journey (Playwright, dev server)** — the browser journey against the Vite development server with the auth and research APIs replaced by Playwright route mocks. It checks user-visible behaviour only; no backend, database, or provider is involved.
- **Production Container Smoke Test** — builds the backend and frontend images, starts PostgreSQL on a fresh volume, applies Alembic migrations in a container, checks that `PUBLIC` holds no application grants and that the runtime role is refused schema DDL, confirms the backend health endpoint answers and that Nginx serves both `/` and the `/app` deep link, then replays the same route-mocked browser journey against the running images. This proves the production images build, migrate, start, and serve their routes. It does not exercise the API end to end: the auth and research APIs remain mocked in the browser.

No CI job contacts a market-data provider, a model provider, an email provider, or Langfuse. CI runs with `LLM_PROVIDER=disabled` and `TRACE_EXPORT_ENABLED=false`, and email uses the default no-op sender. Verifying behaviour against live providers, including real email delivery, is manual QA and is deliberately outside CI.
