# Vantage Backend — Transparent Research Runs

The backend executes durable, end-of-day research runs (accepted with `202` and polled until finished) for supported US-listed equities. It returns deterministic metrics, typed quality states, registered reasons, evidence provenance, version identifiers, and an optional bounded AI interpretation. It does not place trades or provide investment advice.

## Stack and boundaries

- FastAPI on Python 3.12, managed with `uv`
- PostgreSQL 17 through SQLAlchemy 2 and psycopg 3; Alembic owns schema changes
- First-party email/password identity: Argon2id password hashes, 15-minute HS256 access tokens, rotating refresh tokens in an HttpOnly cookie, email verification and password reset. Accounts and research data are stored in PostgreSQL
- Transactional email through any SMTP server (Gmail with an app password), Brevo's API, or a no-op sender for development and tests
- Provider protocols in `app/providers/contracts.py`; adapters live beside it in `app/providers/` (Alpaca, Finnhub, SEC EDGAR, FRED, Tiingo and a fixture provider)
- LangGraph for the deterministic metrics → optional interpretation → policy workflow
- OpenTelemetry spans with allowlisted attributes and optional Langfuse v4 export

The market role needs Alpaca keys (`ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`), or `MARKET_PROVIDER=fixture` for a keyless local stack with invented demo data.

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

- `POST /api/v1/research-runs` accepts the run and returns `202` with a `running` run and a `Location` header; the run executes in the background. A client that sends `Prefer: respond-async` also gets `Preference-Applied: respond-async`, but the header is not required
- `GET /api/v1/research-runs/{run_id}` retrieves an owner-scoped run
- `GET /api/v1/research-runs?limit=20&before=...` lists owner-scoped history

Poll `GET /api/v1/research-runs/{run_id}` until `workflow_status` is no longer `running`. A run still `running` past `RUN_DEADLINE_SECONDS` is finalized as failed the next time its owner reads it.

Four error codes belong to asynchronous runs. Two are HTTP errors in the `SafeError` envelope, both with `Retry-After: 5` and `retryable: true`; no run is created:

- `RUN_CAPACITY_EXCEEDED` (`429`): all run slots are busy
- `SERVICE_DRAINING` (`503`): the service is restarting

The other two appear as `error_code` on a failed run, which is still read with HTTP 200:

- `RUN_DEADLINE_EXCEEDED`: a run did not finish within its time limit
- `RUN_INTERRUPTED`: a run was interrupted by a server restart

Errors use the shared `SafeError` envelope. The incompatible legacy `/api/v1/analyze` route is intentionally absent.

### Research simulations — `/api/v1/experiments`

Off by default. Every route returns `404` until `RESEARCH_WORKBENCH_ENABLED=true`, so the feature can be switched off again without touching saved data. ADR-0008 sets the boundary: long-only, unlevered simulations of three fixed templates (`buy_and_hold`, `sma_crossover`, `momentum_top_k`) over at most 50 symbols and a benchmark ETF, end of day, at most ten years.

- `POST /api/v1/experiments/plan` sizes an experiment (sessions, warm-up, walk-forward windows, engine invocations). It calls no provider and saves nothing
- `POST /api/v1/experiments` returns `202` with a `running` experiment and a `Location` header. Needs a verified email address
- `GET /api/v1/experiments/{id}` returns the spec, result, findings and versions
- `GET /api/v1/experiments?limit=1..50` lists the owner's experiments, newest first, as summaries
- `POST /api/v1/experiments/{id}/replay` returns `202`; it re-runs a finished experiment from its saved inputs with no provider call, linked by `replay_of`. Needs a verified email address
- `GET /api/v1/experiments/{id}/export?format=json|csv` downloads derived data only: spec, metrics, daily NAV series, trades, findings and versions, never provider bars. CSV text cells that start with `=`, `+`, `-` or `@` are prefixed with `'`
- `DELETE /api/v1/experiments/{id}` deletes one experiment and frees its quota

Every route is owner-scoped; another account's experiment is `404`. Experiments run on their own one-slot executor, so they never take capacity from research runs.

How a simulation is computed:

- Decisions are taken at a session's close and filled at the next session's open, on total-return adjusted prices (`adjustment=all`). Raw close × volume measures liquidity.
- Costs are a flat `cost_bps` per side (default 10). Every result also shows the metrics at 0.5×, 1× and 2× that cost.
- With candidate parameters, a walk-forward evaluation (756 training, 126 test sessions, at least three windows) picks by training Sharpe and reports one continuous out-of-sample curve. Sharpe uses a 0% risk-free rate.
- Every result carries the label "Exploratory: list chosen today, survivorship bias possible". The symbol list is chosen today, so delisted names are missing from history. The label is part of the payload and cannot be dismissed.

Failures are saved on the experiment as `error_code`, read with HTTP 200:

- `SYMBOL_NOT_FOUND`, `INSTRUMENT_DATA_ENDED` (a name's history ends before the end date; the engine never exits at a last quote) and `INSUFFICIENT_HISTORY` (more than 5% of sessions missing)
- the provider's own typed failure, for example `MARKET_DATA_PROVIDER_FAILED`
- `EXPERIMENT_DEADLINE_EXCEEDED`, `EXPERIMENT_INTERRUPTED` (restart) and `EXPERIMENT_FAILED`

Starting or replaying can be refused with an HTTP error, and no experiment is created:

- `409`: `EXPERIMENT_IN_FLIGHT` (one running experiment per owner), `EXPERIMENT_QUOTA_REACHED`, `EXPERIMENT_STORAGE_FULL`, `EXPERIMENT_NOT_REPLAYABLE`
- `429` `RUN_CAPACITY_EXCEEDED` and `503` `SERVICE_DRAINING`, with `Retry-After: 5`
- `503` `PROVIDER_NOT_CONFIGURED`: the market provider cannot serve daily history

A finished experiment stores its inputs (compressed, hashed) in Postgres so replay is exact. The `versions` map records the engine, metrics and template versions, code revision, provider, retrieval time and both hashes. The question, hypothesis and notes never reach logs, traces or a model.

## Deterministic results

The metrics registry currently emits one-, five-, and twenty-session return; twenty-session annualized volatility; twenty-session maximum drawdown; twenty-session average dollar volume; accepted, missing, and duplicate price counts; accepted news count; and distinct publisher count.

Stale, invalid, or insufficient price series produce a typed `insufficient_data` result and skip the model (`model=not_run`). News or model failures degrade an otherwise usable run to `review` without discarding the deterministic metrics. Model-authored text may reference accepted evidence IDs but may not introduce numeric claims.

## Local configuration

Copy `.env.example` to `.env` when running the backend outside Docker Compose. Under Compose, configuration comes from the repository root's `.env` instead (see the root README).

The application refuses to start on a configuration that cannot work safely, and names the setting at fault:

- `AUTH_JWT_SECRET` and `TELEMETRY_USER_SALT` must each be at least 32 bytes and not look like a placeholder. Generate each with `openssl rand -hex 32`.
- `AUTH_COOKIE_SAMESITE` must be `lax`, `strict` or `none`, and `none` requires `AUTH_COOKIE_SECURE=true`.
- `EMAIL_PROVIDER` must be `noop`, `smtp` or `brevo`. `smtp` requires `SMTP_HOST`, `SMTP_USERNAME` and `SMTP_PASSWORD`; `brevo` requires `BREVO_API_KEY`. Both require an `EMAIL_FROM` that is not the shipped placeholder.

Other settings that matter in a deployment:

| Setting | Purpose |
|---|---|
| `AUTH_COOKIE_SECURE` | `true` in production; `false` only for plain-HTTP local development. |
| `TRUSTED_PROXY_HOPS` | How many proxies append to `X-Forwarded-For`. `0` (default) ignores the header. Production behind Vercel and Heroku is `2`; a wrong value puts every user in one rate-limit bucket. |
| `ARGON2_MAX_CONCURRENCY` | Concurrent password hashes (19 MiB each); bounds memory on a small dyno. |
| `AUTH_*_MAX_ATTEMPTS`, `AUTH_*_WINDOW_SECONDS` | Rate limits for registration, login and email actions, including `AUTH_EMAIL_SOURCE_MAX_ATTEMPTS` per source across all addresses. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` | SMTP delivery. For Gmail: `smtp.gmail.com`, `587` (STARTTLS; `465` uses implicit TLS), the account address and a Google app password. TLS is always negotiated before the password is sent. |
| `BREVO_API_KEY` | A Brevo API key (`xkeysib-…`), not an SMTP key. |
| `EMAIL_FROM` | The sender. With Gmail, the account address or a verified alias; with Brevo, a sender verified there. |
| `MARKET_PROVIDER`, `NEWS_PROVIDERS`, `FILINGS_PROVIDER`, `MACRO_PROVIDER`, `PRICE_CROSSCHECK_PROVIDER` | Which provider serves each data role. Defaults: `alpaca`, `alpaca,finnhub` (comma list), `edgar`, `fred`, `none`. Allowed values are listed in `.env.example`; see Data providers below. |
| `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`, `FINNHUB_API_KEY`, `FRED_API_KEY`, `TIINGO_API_KEY` | Provider credentials, empty by default and redacted. A missing key leaves that role not configured; it does not stop startup. |
| `SEC_USER_AGENT` | User-Agent for SEC EDGAR; the SEC requires it and a contact in it. No default; redacted. |
| `PROVIDER_TIMEOUT_SECONDS` | Time budget for one provider call, covering all of its requests and the retry (default `6`). |
| `APP_BASE_URL` | The frontend origin that links in emails point to. |
| `EMAIL_VERIFICATION_TTL_SECONDS`, `PASSWORD_RESET_TTL_SECONDS` | Link lifetimes; the email text states the same values. |
| `RESEARCH_WORKBENCH_ENABLED` | Turns on the `/api/v1/experiments` routes. Default `false`. The frontend has its own `VITE_RESEARCH_WORKBENCH_ENABLED`. |
| `EXPERIMENT_EXECUTOR_MAX_WORKERS`, `EXPERIMENT_DEADLINE_SECONDS` | Concurrent simulations per process (default `1`) and the time limit for one (default `300`). |
| `EXPERIMENT_MAX_PER_OWNER`, `EXPERIMENT_STORAGE_LIMIT_MB` | Saved experiments per account (default `25`) and the total stored inputs across all accounts (default `300` MB, sized for a 1 GB Postgres plan). |

Provider credentials are needed only for the selected `LLM_PROVIDER`, and Langfuse keys only when `TRACE_EXPORT_ENABLED=true`.

The database split is intentional:

- `MIGRATION_DATABASE_URL` connects as the DDL owner and is preferred for migrations.
- `DATABASE_URL` connects as the runtime role and remains the migration fallback when a separate owner URL is unavailable.
- `VANTAGE_RUNTIME_DB_ROLE` names the existing role that receives schema usage, table `SELECT`/`INSERT`/`UPDATE`, and sequence usage during migration.

Heroku's `postgres://` database URLs are normalized to SQLAlchemy's `postgresql+psycopg://` dialect. Heroku deployments run `alembic upgrade head` in a release phase using the built web image, before the new web process starts. Configure `MIGRATION_DATABASE_URL` with the DDL owner whenever possible; fallback migrations using `DATABASE_URL` require that role to have the necessary DDL privileges.

The initial migration revokes `PUBLIC` access. Its downgrade deliberately raises an error because research history is immutable. Roll back application code by deploying the prior application version; use a reviewed forward migration for schema corrections.

### Production database

Heroku Postgres Essential-tier plans (`essential-0`) expose exactly one database credential. In production:
- `MIGRATION_DATABASE_URL` is left unset, so Alembic migrations fall back to `DATABASE_URL`. The owner/runtime role separation exists only in Compose and CI.
- Connecting to remote hosts requires TLS (`sslmode=require` is enforced automatically by `normalize_database_url` for all non-local hosts).
- The connection pool is sized with `POOL_SIZE = 5` and `MAX_OVERFLOW = 2` (plus `pool_recycle = 280`), allocating at most 7 connections for the single web process. This leaves headroom under Essential-0's 20-connection ceiling for release-phase migrations, scheduled maintenance jobs, and administrative `heroku pg:psql` sessions.
- `WEB_CONCURRENCY` must stay unset (single web process) unless the connection pool bounds are re-sized to prevent exhausting database connection limits and dyno memory.


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

## Data providers

Each data role names its provider in configuration. The defaults are the free providers:

| Setting | Default | Supplies |
|---|---|---|
| `MARKET_PROVIDER` | `alpaca` | End-of-day prices, plus the benchmark and context series used for relative metrics |
| `NEWS_PROVIDERS` | `alpaca,finnhub` | Cited news evidence, merged and de-duplicated across both |
| `FILINGS_PROVIDER` | `edgar` | SEC filings and fundamentals |
| `MACRO_PROVIDER` | `fred` | Macro series and the VIX close |
| `PRICE_CROSSCHECK_PROVIDER` | `none` | Optional second price source (`tiingo`) used to cross-check the first |

Keys are read from the environment only. Never commit them. A missing key never stops startup. The role is reported as not configured on the run, and the affected metrics show as missing with a reason. The market role is the exception: without an Alpaca key there is no market provider, so the run fails with "Market data provider is not configured.".

### Keyless quick start

To try Vantage without any keys, select the built-in fixture provider for each role:

```bash
MARKET_PROVIDER=fixture
NEWS_PROVIDERS=fixture
FILINGS_PROVIDER=fixture
MACRO_PROVIDER=fixture
```

Fixture data is invented demo data. It is for development and CI, not for research.

| Provider | Role | Where the free key comes from |
|---|---|---|
| Alpaca | Market data and news | A free-tier account at alpaca.markets gives `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY`. |
| Finnhub | News | A free-tier account at finnhub.io gives `FINNHUB_API_KEY`. |
| SEC EDGAR | Filings and fundamentals | No key. Set `SEC_USER_AGENT`. |
| FRED | Macro series | A free API key from the St. Louis Fed's FRED site (fred.stlouisfed.org) gives `FRED_API_KEY`. |
| Tiingo | Price cross-check | A free-tier account at tiingo.com gives `TIINGO_API_KEY`. |

SEC EDGAR's fair-access policy requires every request to identify the caller. Set `SEC_USER_AGENT` to a name and a contact email, for example `Vantage-research admin@example.com` (use your own contact details).

Alpaca's free market data uses the SIP feed, which excludes the most recent 15 minutes. The provider clamps its end time to that boundary, so a session that has only just closed can come back incomplete and is shown as stale until the data catches up.

This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.

The VIX close is © Cboe and is shown with that label.

## Telemetry

`TRACE_EXPORT_ENABLED=false` keeps spans local and performs no Langfuse export. When enabled with `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST`, the Langfuse client registers its exporter on the same OpenTelemetry provider. Each `provider_request` span also carries `vantage.provider.role` (`market` or `news`) and `vantage.provider.name`; no other provider detail is exported. Export is restricted to the Vantage instrumentation scope after attributes, exception events, and status descriptions are redacted. Raw tokens, emails, user IDs, provider payloads, and exception strings are not exported. Stored rate-limit keys and user hashes are salted with `TELEMETRY_USER_SALT`, so they cannot be reversed to an address.

## Verification

Run from `backend/` with a PostgreSQL database whose name contains `vantage_test`:

```bash
uv run alembic upgrade head
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run mypy app/domain app/services app/providers app/repositories app/telemetry app/api
uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=85
```
