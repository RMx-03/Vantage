import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as api from '../../api/experiments';
import { succeeded } from '../../test/experimentFixtures';
import type { Experiment } from '../../types/experiments';
import { SURVIVORSHIP_LABEL } from '../../types/experiments';
import ExperimentResult from './ExperimentResult';

function renderResult(experiment: Experiment) {
  vi.spyOn(api, 'getExperiment').mockResolvedValue(experiment);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/app/workbench/${experiment.id}`]}>
        <Routes>
          <Route path="/app/workbench/:experimentId" element={<ExperimentResult />} />
          <Route path="/app/workbench" element={<span>workbench home</span>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(() => vi.restoreAllMocks());

describe('ExperimentResult', () => {
  it('shows metrics, chart, trades, findings and the label', async () => {
    renderResult(succeeded);
    expect(await screen.findByRole('heading', { name: succeeded.spec.question })).toBeVisible();
    expect(screen.getByText(SURVIVORSHIP_LABEL)).toBeVisible();
    expect(screen.getByText('MSFT is missing 2 sessions.')).toBeVisible();
    const metrics = screen.getByRole('table', { name: /Metrics/ });
    expect(within(metrics).getByRole('row', { name: /Total return/ })).toHaveTextContent(
      '12.34%'
    );
    expect(screen.getByRole('img', { name: /Simulated value/ })).toBeVisible();
    expect(screen.getByRole('table', { name: /Simulated trades/ })).toHaveTextContent('AAPL');
    expect(screen.getByRole('table', { name: /Cost stress/ })).toHaveTextContent('20');
  });

  it('shows the reason when Sharpe is not available', async () => {
    renderResult(succeeded);
    const metrics = await screen.findByRole('table', { name: /Metrics/ });
    expect(within(metrics).getByRole('row', { name: /Sharpe/ })).toHaveTextContent(
      /zero variance/
    );
  });

  it('keeps the label visible for a failed experiment and shows its code', async () => {
    renderResult({
      ...succeeded,
      status: 'failed',
      research_status: 'failed',
      error_code: 'INSTRUMENT_DATA_ENDED',
      error_message: 'XYZ has no data after 2023-05-01.',
      result: null,
    });
    expect(await screen.findByText('XYZ has no data after 2023-05-01.')).toBeVisible();
    expect(screen.getByText('INSTRUMENT_DATA_ENDED')).toBeVisible();
    expect(screen.getByText(SURVIVORSHIP_LABEL)).toBeVisible();
    expect(screen.queryByRole('button', { name: /Replay/ })).toBeNull();
  });

  it('explains a walk-forward that had too little history', async () => {
    renderResult({
      ...succeeded,
      result: {
        ...succeeded.result!,
        walk_forward: { status: 'insufficient_data', windows: [], trials: [], trial_count: 0 },
      },
    });
    expect(await screen.findByText(/too little history for three walk-forward windows/i)).toBeVisible();
  });

  it('lists the walk-forward windows and trial count when complete', async () => {
    renderResult({
      ...succeeded,
      result: {
        ...succeeded.result!,
        walk_forward: {
          status: 'complete',
          trial_count: 4,
          trials: [],
          windows: [
            {
              train_start: '2019-01-02',
              train_end: '2021-12-31',
              test_start: '2022-01-03',
              test_end: '2022-06-30',
              selected: 1,
              train_sharpe: 0.8,
            },
          ],
          oos_metrics: succeeded.result!.metrics,
          oos_series: succeeded.result!.series,
        },
      },
    });
    const table = await screen.findByRole('table', { name: /Walk-forward windows/ });
    expect(table).toHaveTextContent('2022-01-03');
    expect(screen.getByText(/4 candidate trials/)).toBeVisible();
  });

  it('polls while running and offers a manual check', async () => {
    renderResult({ ...succeeded, status: 'running', research_status: null, result: null });
    expect(await screen.findByText(/Simulation running/)).toBeVisible();
  });

  it('replays into a new experiment', async () => {
    const replay = vi
      .spyOn(api, 'replayExperiment')
      .mockResolvedValue({ ...succeeded, id: 'exp-2' });
    renderResult(succeeded);
    await userEvent.setup().click(await screen.findByRole('button', { name: /Replay/ }));
    expect(replay).toHaveBeenCalledWith('exp-1');
    await waitFor(() => expect(api.getExperiment).toHaveBeenCalledWith('exp-2'));
  });

  it('has research actions only, never trade actions', async () => {
    renderResult(succeeded);
    await screen.findByRole('heading', { name: succeeded.spec.question });
    const names = screen.getAllByRole('button').map((b) => b.textContent ?? '');
    expect(names.join(' ')).not.toMatch(/buy|sell|trade|order|execute|approve/i);
  });
});
