import { describe, expect, it } from 'vitest';
import config from '../../vercel.json';

describe('Vercel routing', () => {
  it('serves the SPA entry point for direct requests to client routes', () => {
    expect(config.rewrites).toContainEqual({
      source: '/(.*)',
      destination: '/index.html',
    });
  });
});
