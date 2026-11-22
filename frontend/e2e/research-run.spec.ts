import { test, expect, type Page } from '@playwright/test';
import { informationalRunV3, reviewRun } from '../src/test/fixtures';
import { mockAuth } from './authMocks';

async function installAuthAndApiMocks(page: Page, postHeaders: string[] = []) {
  await mockAuth(page);

  // A run is accepted as running; the first single-run read still reports it
  // running, and every later read returns the finished run.
  const runningOf = (run: typeof informationalRunV3, symbol?: string) => ({
    ...run,
    ...(symbol ? { symbol } : {}),
    workflow_status: 'running',
    research_status: null,
  });
  const reads = new Map<string, number>();

  // Mock Individual Research Run API
  await page.route('**/api/v1/research-runs/*', async (route) => {
    const url = route.request().url();
    const degraded = url.includes('DEGRADED') || url.includes(reviewRun.run_id);
    const finished = degraded ? { ...reviewRun, symbol: 'DEGRADED' } : informationalRunV3;
    const count = (reads.get(finished.run_id) ?? 0) + 1;
    reads.set(finished.run_id, count);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        count === 1 ? runningOf(finished, degraded ? 'DEGRADED' : undefined) : finished
      ),
    });
  });

  // Mock Research Runs API
  await page.route('**/api/v1/research-runs*', async (route) => {
    const req = route.request();
    if (req.method() === 'POST') {
      postHeaders.push(req.headers()['prefer'] ?? '');
      const data = JSON.parse(req.postData() || '{}');
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify(
          data.symbol === 'DEGRADED'
            ? runningOf(reviewRun, 'DEGRADED')
            : runningOf(informationalRunV3)
        ),
      });
    } else {
      // GET list or get run
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [informationalRunV3],
          next_cursor: null,
        }),
      });
    }
  });
}

test.describe('Research Run Browser Journey (first-party auth and API route-mocked)', () => {
  test('creates, inspects, and reopens transparent research runs', async ({ page }) => {
    const postHeaders: string[] = [];
    await installAuthAndApiMocks(page, postHeaders);

    // Direct deep-link navigation, then a reload. Against the production
    // frontend container both requests are served by the Nginx SPA fallback
    // (`try_files ... /index.html`); against the dev server they are served by
    // Vite. Auth and the research API stay route-mocked either way, so this
    // exercises static routing only — not the backend.
    const directResponse = await page.goto('/app');
    expect(directResponse?.status()).toBe(200);
    await expect(page.getByLabel(/US equity symbol/i)).toBeVisible();

    const reloadResponse = await page.reload();
    expect(reloadResponse?.status()).toBe(200);

    // Verify workspace loaded
    await expect(page.getByLabel(/US equity symbol/i)).toBeVisible();

    // 1. Submit valid symbol
    await page.getByLabel(/US equity symbol/i).fill('AAPL');
    await page.getByRole('button', { name: /Run research/i }).click();

    // The run is accepted asynchronously and shows a running state first
    await expect(page.getByRole('status')).toContainText('Running research analysis');
    expect(postHeaders[0]).toContain('respond-async');

    // 2. Verify all six levels of information hierarchy
    await expect(page.getByRole('heading', { name: 'AAPL', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Why this result?' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Metrics' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Data quality' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Sources' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Macro' })).toBeVisible();
    await expect(page.getByText('SEC filing', { exact: true })).toBeVisible();
    await expect(page.getByText('Attribution: company')).toBeVisible();
    await expect(page.getByText('Company-specific evidence explains the move.')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Run details' })).toBeVisible();

    // Confirm no forbidden language
    await expect(page.getByText(/trade approved|trade rejected/i)).not.toBeVisible();

    // Deep link assertion: url became addressable and reloading it restores the run
    await expect(page).toHaveURL(/\/app\/research\/[0-9a-f-]+/i);

    const runUrl = page.url();
    await page.reload();
    await expect(page.getByText(informationalRunV3.summary!)).toBeVisible();
    expect(page.url()).toBe(runUrl);

    // 3. Reopen historical run from history drawer
    await page.getByRole('button', { name: /View History/i }).click();
    const historyLink = page.getByRole('link', { name: /AAPL.*Sep 11, 2026/i });
    await expect(historyLink).toBeVisible();
    await historyLink.click();

    await expect(page.getByText(/Historical/i)).toBeVisible();
    await expect(page.getByText(/Original as of/i)).toBeVisible();

    // 4. Exercise degraded model run without losing quantitative metrics
    await page.getByLabel(/US equity symbol/i).fill('DEGRADED');
    await page.getByRole('button', { name: /Run research/i }).click();

    await expect(page.getByRole('status')).toContainText('Running research analysis');
    await expect(page.getByRole('heading', { name: 'DEGRADED', exact: true })).toBeVisible();
    await expect(page.getByText('AI interpretation unavailable', { exact: true })).toBeVisible();
    await expect(page.getByText('20-Session Return')).toBeVisible();

    // 5. Settings run-log regression assertion
    await page.goto('/app/settings/runs');
    const row = page.getByRole('link', { name: /AAPL/i }).first();
    await row.click();
    await expect(page).toHaveURL(/\/app\/research\/[0-9a-f-]+/i);
  });
});
