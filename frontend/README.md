# Vantage Frontend — Transparent Research Workspace

A modern, responsive React + TypeScript web application for running and inspecting transparent equity research analyses on US markets.

---

## Overview

The Vantage Research Workspace enables analysts and researchers to:
- **Execute Transparent Research Runs**: Trigger asynchronous, observable market research pipelines for US equities.
- **Inspect Real-time Execution**: Track pipeline status across steps (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`).
- **Review Market Snapshot Metrics**: View end-of-day pricing, technical indicators (SMA-20, SMA-50, RSI-14, annualized volatility), and valuation metrics with full provenance.
- **Assess Data Quality**: Review automated quality audit badges (complete, partial, or stale data flags).
- **Inspect Structured AI Interpretations**: Read thesis statements, key drivers, risk assessments, and confidence scores.
- **Graceful Degraded State Handling**: If AI synthesis is unavailable (e.g. provider timeout or offline service), the UI clearly indicates the degraded state while preserving access to all computed market metrics.

---

## Architecture & Technology Stack

- **Framework**: [React 19](https://react.dev/) + [TypeScript](https://www.typescriptlang.org/)
- **Bundler & Dev Server**: [Vite](https://vitejs.dev/)
- **Styling**: Vanilla CSS / CSS Modules with bespoke design tokens and dark mode
- **Authentication**: [Supabase Auth](https://supabase.com/docs/guides/auth)
- **Unit & Component Testing**: [Vitest](https://vitest.dev/) + [Testing Library](https://testing-library.com/)
- **End-to-End Testing**: [Playwright](https://playwright.dev/)

---

## Getting Started

### 1. Prerequisites

- Node.js 20+ (Node.js 22 LTS recommended)
- npm 10+

### 2. Environment Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Configure the following environment variables:

| Variable | Description | Example / Default |
|---|---|---|
| `VITE_SUPABASE_URL` | Your Supabase project URL | `https://xyzcompany.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | Public anon key from Supabase Dashboard | `eyJhbGciOi...` |
| `VITE_API_URL` | Backend API base URL | `http://localhost:8000` |
| `VITE_API_BASE_URL` | Alternate alias for backend API base URL | `http://localhost:8000` |

### 3. Install Dependencies

```bash
npm install
```

### 4. Start Development Server

```bash
npm run dev
```

The application will be accessible at `http://localhost:5173`.

---

## Verification & Testing

### Unit & Component Tests

Run the Vitest test suite with coverage tracking:

```bash
npm test -- --run --coverage
```

### Linting & Formatting

Check code quality and TypeScript types:

```bash
npm run lint
```

### Production Build

Verify production bundle compilation:

```bash
npm run build
```

### End-to-End Browser Tests

Run the Playwright user journey test in headless Chromium:

```bash
npx playwright test --project=chromium
```

---

## User Journey & Degraded States

1. **Authenticated Session**: The workspace validates user sessions via Supabase. All API calls inject the Supabase JWT in the `Authorization: Bearer <token>` header.
2. **Launch Run**: Users enter a US equity ticker (e.g. `AAPL`, `MSFT`) and initiate research.
3. **Execution Inspection**: The run detail view displays the step timeline, duration, and error details (if any).
4. **Degraded Interpretation Handling**: If the backend encounters an AI provider failure, the run still succeeds with market snapshot data, and the workspace displays an informational warning with the degradation reason code (e.g. `PROVIDER_UNAVAILABLE`), preventing any loss of quantitative market context.
