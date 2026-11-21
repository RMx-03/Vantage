import { test, expect, type Page } from '@playwright/test';
import { succeeded } from '../src/test/experimentFixtures';
import { SURVIVORSHIP_LABEL, type Experiment } from '../src/types/experiments';
import { mockAuth } from './authMocks';

const QUESTION = 'How did an equal-weight hold of two names do?';

const plan = {
  end: '2024-01-04',
  fetch_start: '2019-12-31',
  sessions: 1258,
  warmup_sessions: 1,
  windows: 0,
  candidates: 0,
  engine_invocations: 4,
  warnings: [],
};

/** A small in-memory experiments API: each experiment reads once as running. */
async function mockExperiments(page: Page) {
  const store = new Map<string, Experiment>();
  const reads = new Map<string, number>();
  const make = (id: string, extra: Partial<Experiment> = {}): Experiment => ({
    ...succeeded,
    id,
    spec: { ...succeeded.spec, question: QUESTION },
    ...extra,
  });
  const running = (e: Experiment): Experiment => ({
    ...e,
    status: 'running',
    research_status: null,
    result: null,
  });
  const json = (body: unknown, status = 200) => ({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });

  await page.route('**/api/v1/experiments**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const parts = url.pathname.replace(/^\/api\/v1\/experiments\/?/, '').split('/');
    const [id, action] = parts;
    if (request.method() === 'POST' && id === 'plan') return route.fulfill(json(plan));
    if (request.method() === 'POST' && !id) {
      expect(JSON.parse(request.postData() ?? '{}').question).toBe(QUESTION);
      const created = make(`exp-${store.size + 1}`);
      store.set(created.id, created);
      return route.fulfill(json(running(created), 202));
    }
    if (request.method() === 'POST' && action === 'replay') {
      const replay = make(`exp-${store.size + 1}`, { replay_of: id });
      store.set(replay.id, replay);
      return route.fulfill(json(running(replay), 202));
    }
    if (action === 'export')
      return route.fulfill({
        status: 200,
        contentType: 'text/csv; charset=utf-8',
        body: 'section,date,symbol,field,value\n',
      });
    if (!id)
      return route.fulfill(
        json(
          [...store.values()].reverse().map((e) => ({
            id: e.id,
            status: e.status,
            research_status: e.research_status,
            created_at: e.created_at,
            question: e.spec.question,
            template: e.spec.strategy.template,
            symbols: e.spec.symbols,
            start: e.spec.start,
            end: e.spec.end,
            replay_of: e.replay_of,
          }))
        )
      );
    const found = store.get(id);
    if (!found) return route.fulfill(json({ detail: { code: 'NOT_FOUND', message: 'Experiment not found.' } }, 404));
    const count = (reads.get(id) ?? 0) + 1;
    reads.set(id, count);
    return route.fulfill(json(count === 1 ? running(found) : found));
  });
}

async function press(page: Page, name: RegExp, role: 'button' | 'link' = 'button') {
  await page.getByRole(role, { name }).focus();
  await page.keyboard.press('Enter');
}

async function typeInto(page: Page, label: RegExp, text: string) {
  await page.getByLabel(label).focus();
  await page.keyboard.type(text);
}

test.describe('Research workbench journey (route-mocked, keyboard only, 360 px)', () => {
  // The production image is built with the workbench flag off.
  test.skip(
    process.env.PLAYWRIGHT_EXTERNAL_SERVER === 'true',
    'the workbench ships dark in the production container'
  );
  test.use({ viewport: { width: 360, height: 800 } });

  test('preview, run, reopen, replay, compare and export', async ({ page }) => {
    await mockAuth(page);
    await mockExperiments(page);

    await page.goto('/app/workbench');
    await expect(page.getByRole('heading', { name: 'Research workbench' })).toBeVisible();
    await expect(page.getByText(SURVIVORSHIP_LABEL).first()).toBeVisible();

    await typeInto(page, /^Question/, QUESTION);
    await typeInto(page, /^Symbols/, 'AAPL MSFT');
    await page.getByLabel(/^Start date/).focus();
    await page.keyboard.type('01022020');

    await page.getByLabel(/^Notes/).focus();
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: /Preview plan/ })).toBeFocused();
    await page.keyboard.press('Enter');
    const preview = page.getByRole('region', { name: 'Plan preview' });
    await expect(preview).toContainText('1,258');
    await expect(preview).toContainText(SURVIVORSHIP_LABEL);

    await press(page, /Run simulation/);
    await expect(page).toHaveURL(/\/app\/workbench\/exp-1$/);
    await expect(page.getByRole('heading', { name: QUESTION })).toBeVisible();
    await expect(page.getByRole('table', { name: /Metrics/ })).toBeVisible({ timeout: 10_000 });

    // Leave and come back through the history list.
    await page.goto('/app/research');
    await page.goto('/app/workbench');
    await press(page, new RegExp(QUESTION), 'link');
    await expect(page).toHaveURL(/\/app\/workbench\/exp-1$/);
    await expect(page.getByText('MSFT is missing 2 sessions.')).toBeVisible();

    await press(page, /Replay from saved inputs/);
    await expect(page).toHaveURL(/\/app\/workbench\/exp-2$/);
    await expect(page.getByRole('link', { name: /replay of an earlier experiment/ })).toBeVisible();

    await page.goto('/app/workbench');
    const boxes = page.getByRole('checkbox', { name: /Pick for comparison/ });
    await expect(boxes).toHaveCount(2);
    for (const box of await boxes.all()) {
      await box.focus();
      await page.keyboard.press('Space');
    }
    await press(page, /Compare 2/, 'link');
    await expect(page.getByRole('table', { name: 'Assumptions' })).toBeVisible();
    await expect(page.getByText(SURVIVORSHIP_LABEL)).toBeVisible();

    await page.goto('/app/workbench/exp-1');
    const download = page.waitForEvent('download');
    await press(page, /Export CSV/);
    expect((await download).suggestedFilename()).toBe('experiment-exp-1.csv');

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
