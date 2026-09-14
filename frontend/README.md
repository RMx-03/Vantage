# Vantage Frontend — Transparent Research Workspace

The React workspace creates and inspects synchronous US-equity end-of-day research runs. It shows deterministic metrics, data/model quality, registered reasons, evidence sources, version information, owner-scoped history, and safe actionable error states.

## Stack

- React 19 and TypeScript 6
- Vite 8 and Tailwind CSS 4
- TanStack Query for server state
- Supabase Auth for the browser session
- Vitest, Testing Library, and Playwright
- Node.js `>=22.22 <23`

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Purpose |
|---|---|
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Public Supabase anon/publishable key |
| `VITE_API_URL` | Backend origin, such as `http://localhost:8000` |

Vite values are build-time configuration. The Docker image accepts the same three values as build arguments through Docker Compose.

## Run and verify

```bash
npm ci
npm run dev
npm test -- --run --coverage
npm run lint
npm run build
npm run test:e2e -- --project=chromium
```

Coverage is measured over the Phase 1 research feature and its API client with an 80% line/function gate.

## User-visible states

The UI shows one current result or one selected historical result. Starting a request shows a bounded loading state; a failed newer request suppresses any older result so stale output cannot be mistaken for the latest run. Authentication failures offer “Sign in again”; retryable provider/server failures offer “Retry research.”

Results use only the backend contract states: `informational`, `review`, `insufficient_data`, and `failed`, with model quality `healthy`, `degraded`, `failed`, or `not_run`. The Phase 1 UI does not claim real-time progress, latency, node counts, valuation metrics, SMA/RSI indicators, forecasts, confidence scores, or trade approval.
