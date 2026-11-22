import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as experiments from '../api/experiments';
import * as researchRuns from '../api/researchRuns';
import App from '../App';
import { mockSignedIn } from './authHelpers';

beforeEach(() => {
  mockSignedIn();
  vi.spyOn(experiments, 'listExperiments').mockResolvedValue([]);
  vi.spyOn(researchRuns, 'listResearchRuns').mockResolvedValue({
    items: [],
    next_cursor: null,
  });
  window.history.pushState({}, '', '/app/workbench');
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  window.history.pushState({}, '', '/');
});

describe('workbench route', () => {
  it('exists when the flag is true', async () => {
    vi.stubEnv('VITE_RESEARCH_WORKBENCH_ENABLED', 'true');
    render(<App />);
    expect(
      await screen.findByRole('heading', { name: /Research workbench/i })
    ).toBeVisible();
  });

  it('does not exist while the flag is off', async () => {
    vi.stubEnv('VITE_RESEARCH_WORKBENCH_ENABLED', 'false');
    render(<App />);
    await screen.findByText('Vantage');
    expect(screen.queryByRole('heading', { name: /Research workbench/i })).toBeNull();
    expect(window.location.pathname).not.toBe('/app/workbench');
  });
});
