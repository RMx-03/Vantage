# Vantage Backend — Transparent Research Runs

The backend executes durable, synchronous, end-of-day research runs for supported US-listed equities. It returns deterministic metrics, typed quality states, registered reasons, evidence provenance, version identifiers, and an optional bounded AI interpretation. It does not place trades or provide investment advice.

## Stack and boundaries

- FastAPI on Python 3.12, managed with `uv`
- PostgreSQL 17 through SQLAlchemy 2 and psycopg 3; Alembic owns schema changes
- First-party email/password identity: Argon2id password hashes, 15-minute HS256 access tokens, rotating refresh tokens in an HttpOnly cookie, email verification and password reset. Accounts and research data are stored in PostgreSQL
- Transactional email through Brevo, or a no-op sender for development and tests
- Provider protocols in `app/providers/contracts.py`; the Phase 1 adapter is `YFinanceSnapshotProvider`
- LangGraph for the deterministic metrics → optional interpretation → policy workflow
- OpenTelemetry spans with allowlisted attributes and optional Langfuse v4 export

`yfinance` is suitable for development and research prototyping, not a licensed production market-data entitlement. The adapter verifies `quoteType=EQUITY`, a supported US exchange code, and USD currency before accepting data.

## API

### Authentication — `/api/v1/auth`

| Route | Purpose |
|---|---|
| `POST /register` | Create an account and send a verification email. Answers `202` whether or not the address is already registered; the owner of an existing address gets an "account already exists" email instead. |
| `POST /login` | Exchange email and password for an access token; sets the refresh cookie. |
| `POST /refresh` | Rotate the refresh cookie and return a new access token. Reusing a rotated token revokes its whole family. |
| `POST /logout` | Revoke the current refresh token and clear the cookie. |
| `POST /logout-all` | Revoke every refresh token for the signed-in account. |
| `GET /me` | The signed-in account, including `email_verified`. |
| `POST /verify-email` | Consume a single-use verification token. |
| `POST /resend-verification` | Send a new verification link; the previous one stops working. Same `202` answer for every address. |
| `POST /forgot-password` | Send a password-reset link. Same `202` answer for every address. |
| `POST /reset-password` | Set a new password with a single-use reset token; signs out every session. |
| `POST /change-password` | Change the password of the signed-in account, given the current one. |

The refresh cookie is scoped to `Path=/api/v1/auth`. `refresh` and `logout` reject requests a browser marks as cross-site (`Sec-Fetch-Site`). Rate limits are sliding windows stored in PostgreSQL: registration per source, login per address and source together, resend and forgot-password both per address and per source, and change-password per account.

### Research — `/api/v1/research-runs`

All research routes require a valid Vantage access token. Creating a run also requires a verified email address; an unverified account receives `403`.

- `POST /api/v1/research-runs` creates and completes one run synchronously
- `GET /api/v1/research-runs/{run_id}` retrieves an owner-scoped run
- `GET /api/v1/research-runs?limit=20&before=...` lists owner-scoped history

Errors use the shared `SafeError` envelope. The incompatible legacy `/api/v1/analyze` route is intentionally absent.

## Deterministic results

The metrics registry currently emits one-, five-, and twenty-session return; twenty-session annualized volatility; twenty-session maximum drawdown; twenty-session average dollar volume; accepted, missing, and duplicate price counts; accepted news count; and distinct publisher count.

Stale, invalid, or insufficient price series produce a typed `insufficient_data` result and skip the model (`model=not_run`). News or model failures degrade an otherwise usable run to `review` without discarding the deterministic metrics. Model-authored text may reference accepted evidence IDs but may not introduce numeric claims.

## Local configuration

Copy `.env.example` to `.env` when running the backend outside Docker Compose. Under Compose, configuration comes from the repository root's `.env` instead (see the root README).

The application refuses to start on a configuration that cannot work safely, and names the setting at fault:

- `AUTH_JWT_SECRET` and `TELEMETRY_USER_SALT` must each be at least 32 bytes and not look like a placeholder. Generate each with `openssl rand -hex 32`.
- `AUTH_COOKIE_SAMESITE` must be `lax`, `strict` or `none`, and `none` requires `AUTH_COOKIE_SECURE=true`.
- `EMAIL_PROVIDER` must be `noop` or `brevo`. `brevo` requires `BREVO_API_KEY` and an `EMAIL_FROM` that is not the shipped placeholder.

Other settings that matter in a deployment:

| Setting | Purpose |
|---|---|
| `AUTH_COOKIE_SECURE` | `true` in production; `false` only for plain-HTTP local development. |
| `TRUSTED_PROXY_HOPS` | How many proxies append to `X-Forwarded-For`. `0` (default) ignores the header. Production behind Vercel and Heroku is `2`; a wrong value puts every user in one rate-limit bucket. |
| `ARGON2_MAX_CONCURRENCY` | Concurrent password hashes (19 MiB each); bounds memory on a small dyno. |
| `AUTH_*_MAX_ATTEMPTS`, `AUTH_*_WINDOW_SECONDS` | Rate limits for registration, login and email actions, including `AUTH_EMAIL_SOURCE_MAX_ATTEMPTS` per source across all addresses. |
| `BREVO_API_KEY` | A Brevo API key (`xkeysib-…`), not an SMTP key. |
| `EMAIL_FROM` | A sender verified in the Brevo account. |
| `APP_BASE_URL` | The frontend origin that links in emails point to. |
| `EMAIL_VERIFICATION_TTL_SECONDS`, `PASSWORD_RESET_TTL_SECONDS` | Link lifetimes; the email text states the same values. |

Provider credentials are needed only for the selected `LLM_PROVIDER`, and Langfuse keys only when `TRACE_EXPORT_ENABLED=true`.

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

## Scheduled maintenance

Rate-limit writes delete their own key's expired rows. Keys that are never written again (a one-off source) are removed by a daily sweep, intended for Heroku Scheduler. Run it from `backend/` as a module:

```bash
python -m scripts.purge_auth_attempts
```

Running the file directly fails with `No module named 'app'`.

## Telemetry

`TRACE_EXPORT_ENABLED=false` keeps spans local and performs no Langfuse export. When enabled with `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST`, the Langfuse client registers its exporter on the same OpenTelemetry provider. Export is restricted to the Vantage instrumentation scope after attributes, exception events, and status descriptions are redacted. Raw tokens, emails, user IDs, provider payloads, and exception strings are not exported. Stored rate-limit keys and user hashes are salted with `TELEMETRY_USER_SALT`, so they cannot be reversed to an address.

## Verification

Run from `backend/` with a PostgreSQL database whose name contains `vantage_test`:

```bash
uv run alembic upgrade head
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run mypy app/domain app/services app/providers app/repositories app/telemetry app/api
uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=85
```
