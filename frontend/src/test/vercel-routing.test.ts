import { describe, expect, it } from 'vitest';
import config from '../../vercel.json';

describe('Vercel routing', () => {
  it('serves the SPA entry point for direct requests to client routes', () => {
    expect(config.rewrites).toContainEqual({
      source: '/(.*)',
      destination: '/index.html',
    });
  });

  it('proxies API paths to the backend before the SPA catch-all', () => {
    const rewrites = config.rewrites as { source: string; destination: string }[];
    const apiIndex = rewrites.findIndex((r) => r.source.startsWith('/api'));
    const spaIndex = rewrites.findIndex((r) => r.source === '/(.*)');

    expect(apiIndex).toBeGreaterThanOrEqual(0);
    // Order matters: the catch-all would swallow /api and serve index.html.
    expect(apiIndex).toBeLessThan(spaIndex);
    expect(rewrites[apiIndex].destination).toMatch(/^https:\/\/.+\/api\/:path\*$/);
  });

  it('still serves the SPA for deep links', () => {
    const rewrites = config.rewrites as { source: string }[];
    expect(rewrites.some((r) => r.source === '/(.*)')).toBe(true);
  });
});

