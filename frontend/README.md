# Vantage Frontend — Transparent Research Workspace

The React workspace handles sign-in and account flows, and starts, polls and inspects US-equity end-of-day research runs. It shows deterministic metrics, data/model quality, registered reasons, evidence sources, version information, owner-scoped history, and safe actionable error states.

## Stack

- React 19 and TypeScript 6
- Vite 8 and Tailwind CSS 4
- TanStack Query for server state
- First-party auth with in-memory tokens and HttpOnly refresh cookies
- Vitest, Testing Library, and Playwright
- Node.js `>=22.22 <23`

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Purpose |
|---|---|
| `VITE_API_URL` | Backend origin, such as `http://localhost:8000` (local dev only) |
| `VITE_RESEARCH_WORKBENCH_ENABLED` | `true` shows the Workbench nav item and its routes. Default off; the backend needs `RESEARCH_WORKBENCH_ENABLED=true` as well |

Leave `VITE_API_URL` unset for the Vercel build. API calls then go to the same origin, and the rewrite in `vercel.json` proxies `/api/*` to the Heroku backend.

Vite values are build-time configuration. The Docker image accepts `VITE_API_URL` and `VITE_RESEARCH_WORKBENCH_ENABLED` as build arguments through Docker Compose. On Vercel, set the flag in the project's environment variables and redeploy.

## Run and verify

```bash
npm ci
npm run dev
npm test -- --run --coverage
npm run lint
npm run check:design
npm run build
npm run test:e2e -- --project=chromium
```

Coverage is measured over the Phase 1 research feature and its API client with an 80% line/function gate.

`npm run test:e2e` runs the browser journey with the auth and research APIs replaced by Playwright route mocks, so it verifies UI behaviour rather than a full stack. Setting `PLAYWRIGHT_EXTERNAL_SERVER=true` skips the development server and runs the same mocked journey against an already-running server, which is how CI replays it against the production Nginx container image.

## Sessions

The access token lives only in memory, never in `localStorage`. The refresh token is an HttpOnly cookie the page cannot read. `src/context/AuthContext.tsx` refreshes on load and again shortly before the access token expires; an API call that still gets a `401` refreshes once and retries. Refreshes are single-flight within a tab and serialized across tabs with the Web Locks API, so two tabs never spend the same rotating refresh token.

An account whose email is not verified can sign in and read its history, but cannot start research. The workspace shows a banner with a resend action, and the sign-in page offers "Resend verification email" for the address entered, so a user whose first email never arrived can ask again without signing in.

## User-visible states

The UI shows one current result or one selected historical result. Starting a request shows a bounded loading state; a failed newer request suppresses any older result so stale output cannot be mistaken for the latest run. Authentication failures offer “Sign in again”; retryable provider/server failures offer “Retry research.”

Results use only the backend contract states: `informational`, `review`, `insufficient_data`, and `failed`, with model quality `healthy`, `degraded`, `failed`, or `not_run`. The Phase 1 UI does not claim real-time progress, latency, node counts, valuation metrics, SMA/RSI indicators, forecasts, confidence scores, or trade approval.

## Routes

| Path | View |
|---|---|
| `/` | Landing |
| `/auth` | Sign in / register; forgot password and resend verification |
| `/verify-email` | Confirms the token from a verification email |
| `/reset-password` | Sets a new password from a reset email |
| `/app` | redirects to `/app/research` |
| `/app/research` | Research terminal, empty |
| `/app/research/:runId` | A specific run — shareable |
| `/app/workbench` | Research workbench: experiment form, plan preview, history (flag only) |
| `/app/workbench/:id` | One simulation result, with replay and CSV/JSON export (flag only) |
| `/app/workbench/compare?ids=` | 2 to 4 results side by side (flag only) |
| `/app/settings` | redirects to `/app/settings/profile` |
| `/app/settings/profile` | Operator profile |
| `/app/settings/runs` | Durable research run log |

Navigation destinations live in one place: `src/components/nav/navItems.ts`.
Add a destination there and both the sidebar and the mobile bottom bar pick it
up. Items with `to: null` render as disabled placeholders for destinations not built yet.

## Research workbench

Behind `VITE_RESEARCH_WORKBENCH_ENABLED`. The form mirrors the backend spec rules in `src/features/workbench/specBuilder.ts`, so each error names its field; the server checks again. Preview calls the plan route only. A running experiment is polled on the research-run schedule (`runPolling.ts`); after about 150 seconds polling stops and the page offers "Check again". Exports are fetched with the access token and saved as a file. The chart is a hand-written SVG (`src/components/ui/LineChart.tsx`) with a data table of the same numbers; a missing value leaves a gap rather than a joined line. Every workbench page shows the survivorship label.

## Design system

All UI uses the `@theme` tokens defined in `src/index.css` — never stock
Tailwind palette classes (`slate-*`, `indigo-*`, `rose-*`, …), never a border
radius, never a shadow or blur, and `font-label` (Space Grotesk) rather than
`font-mono`.

`npm run check:design` enforces this and runs in CI.
