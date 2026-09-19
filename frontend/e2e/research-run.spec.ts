import { test, expect, type Page } from '@playwright/test';
import { informationalRun, reviewRun } from '../src/test/fixtures';

async function installAuthAndApiMocks(page: Page) {
  // Return an authenticated session for the Supabase storage key selected by
  // the build-time project URL. This keeps the journey portable across CI,
  // local Vite, and the production container image.
  await page.addInitScript(() => {
    const mockSession = {
      access_token: 'mock-access-token-123',
      token_type: 'bearer',
      expires_in: 3600,
      expires_at: Math.floor(Date.now() / 1000) + 3600,
      refresh_token: 'mock-refresh-token-123',
      user: {
        id: '11111111-1111-1111-1111-111111111111',
        email: 'operator@example.com',
        role: 'authenticated',
        aud: 'authenticated',
      },
    };
    const storedSession = JSON.stringify(mockSession);
    const originalGetItem = Storage.prototype.getItem;
    Storage.prototype.getItem = function (key: string) {
      if (key.startsWith('sb-') && key.endsWith('-auth-token')) {
        return storedSession;
      }
      return originalGetItem.call(this, key);
    };
  });

  // Mock Supabase Auth API
  await page.route('**/auth/v1/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: '11111111-1111-1111-1111-111111111111',
        email: 'operator@example.com',
        role: 'authenticated',
        aud: 'authenticated',
      }),
    });
  });

  // Mock Individual Research Run API
  await page.route('**/api/v1/research-runs/*', async (route) => {
    const url = route.request().url();
    if (url.includes('DEGRADED') || url.includes(reviewRun.run_id)) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...reviewRun,
          symbol: 'DEGRADED',
        }),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(informationalRun),
      });
    }
  });

  // Mock Research Runs API
  await page.route('**/api/v1/research-runs*', async (route) => {
    const req = route.request();
    if (req.method() === 'POST') {
      const data = JSON.parse(req.postData() || '{}');
      if (data.symbol === 'DEGRADED') {
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            ...reviewRun,
            symbol: 'DEGRADED',
          }),
        });
      } else {
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(informationalRun),
        });
      }
    } else {
      // GET list or get run
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [informationalRun],
          next_cursor: null,
        }),
      });
    }
  });
}

test.describe('Research Run Browser Journey (Supabase and API route-mocked)', () => {
  test('creates, inspects, and reopens transparent research runs', async ({ page }) => {
    await installAuthAndApiMocks(page);

    // Direct deep-link navigation, then a reload. Against the production
    // frontend container both requests are served by the Nginx SPA fallback
    // (`try_files ... /index.html`); against the dev server they are served by
    // Vite. Supabase and the research API stay route-mocked either way, so this
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

    // 2. Verify all six levels of information hierarchy
    await expect(page.getByRole('heading', { name: 'AAPL', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Why this result?' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Metrics' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Data quality' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Sources' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Run details' })).toBeVisible();

    // Confirm no forbidden language
    await expect(page.getByText(/trade approved|trade rejected/i)).not.toBeVisible();

    // Deep link assertion: url became addressable and reloading it restores the run
    await expect(page).toHaveURL(/\/app\/research\/[0-9a-f-]+/i);

    const runUrl = page.url();
    await page.reload();
    await expect(page.getByText(informationalRun.summary!)).toBeVisible();
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
