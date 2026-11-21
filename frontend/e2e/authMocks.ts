import type { Page } from '@playwright/test';

/** Route-mock first-party auth so every journey starts signed in. */
export async function mockAuth(page: Page) {
  await page.route('**/api/v1/auth/refresh', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'e2e-access-token',
        token_type: 'bearer',
        expires_in: 900,
      }),
    })
  );

  await page.route('**/api/v1/auth/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: '00000000-0000-4000-8000-000000000001',
        email: 'operator@example.com',
        email_verified: true,
      }),
    })
  );

  await page.route('**/api/v1/auth/login', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'e2e-access-token',
        token_type: 'bearer',
        expires_in: 900,
      }),
    })
  );
}
