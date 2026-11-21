import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../../api/experiments';
import { ApiError } from '../../api/researchRuns';
import type { Experiment, ExperimentPlan, ExperimentSummary } from '../../types/experiments';
import { SURVIVORSHIP_LABEL } from '../../types/experiments';
import WorkbenchPage from './WorkbenchPage';

const plan: ExperimentPlan = {
  end: '2024-12-31',
  fetch_start: '2019-12-31',
  sessions: 1258,
  warmup_sessions: 1,
  windows: 3,
  candidates: 2,
  engine_invocations: 7,
  warnings: ['NVDA starts after the start date.'],
};

const summary: ExperimentSummary = {
  id: 'exp-old',
  status: 'succeeded',
  research_status: 'informational',
  created_at: '2026-11-21T10:00:00Z',
  question: 'Earlier question',
  template: 'buy_and_hold',
  symbols: ['AAPL', 'MSFT'],
  start: '2020-01-02',
  end: '2024-12-31',
};

function ResultProbe() {
  return <span>result {useParams().experimentId}</span>;
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/workbench']}>
        <Routes>
          <Route path="/app/workbench" element={<WorkbenchPage />} />
          <Route path="/app/workbench/:experimentId" element={<ResultProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function fillValidForm() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/^Question/), 'How did a hold do?');
  await user.type(screen.getByLabelText(/^Symbols/), 'AAPL MSFT');
  await user.type(screen.getByLabelText(/^Start/), '2020-01-02');
  return user;
}

beforeEach(() => {
  vi.spyOn(api, 'listExperiments').mockResolvedValue([summary]);
});

afterEach(() => vi.restoreAllMocks());

describe('WorkbenchPage', () => {
  it('always shows the survivorship label and the owner history', async () => {
    renderPage();
    expect(screen.getAllByText(SURVIVORSHIP_LABEL).length).toBeGreaterThan(0);
    const link = await screen.findByRole('link', { name: /Earlier question/ });
    expect(link).toHaveAttribute('href', '/app/workbench/exp-old');
  });

  it('shows field errors that name the field and calls nothing', async () => {
    const planSpy = vi.spyOn(api, 'planExperiment');
    renderPage();
    await userEvent.setup().click(screen.getByRole('button', { name: /Preview/ }));
    expect(screen.getByText(/Question: /)).toBeVisible();
    expect(screen.getByLabelText(/^Question/)).toHaveAttribute('aria-invalid', 'true');
    expect(planSpy).not.toHaveBeenCalled();
  });

  it('previews sessions, windows and candidates without submitting', async () => {
    const planSpy = vi.spyOn(api, 'planExperiment').mockResolvedValue(plan);
    const createSpy = vi.spyOn(api, 'createExperiment');
    renderPage();
    const user = await fillValidForm();
    await user.click(screen.getByRole('button', { name: /Preview/ }));
    const preview = await screen.findByRole('region', { name: /Plan preview/ });
    expect(preview).toHaveTextContent('1,258');
    expect(preview).toHaveTextContent(/Walk-forward windows\s*3/);
    expect(preview).toHaveTextContent(/Candidates\s*2/);
    expect(preview).toHaveTextContent('NVDA starts after the start date.');
    expect(preview).toHaveTextContent(SURVIVORSHIP_LABEL);
    expect(planSpy).toHaveBeenCalledTimes(1);
    expect(createSpy).not.toHaveBeenCalled();
  });

  it('blocks a duplicate submit and opens the result when accepted', async () => {
    let accept: (value: Experiment) => void = () => {};
    const createSpy = vi
      .spyOn(api, 'createExperiment')
      .mockReturnValue(new Promise((resolve) => (accept = resolve)));
    renderPage();
    const user = await fillValidForm();
    const run = screen.getByRole('button', { name: /Run simulation/ });
    await user.click(run);
    await user.click(run);
    expect(createSpy).toHaveBeenCalledTimes(1);
    expect(run).toBeDisabled();
    accept({ id: 'exp-new' } as Experiment);
    expect(await screen.findByText('result exp-new')).toBeVisible();
  });

  it('explains a refusal with its code', async () => {
    vi.spyOn(api, 'createExperiment').mockRejectedValue(
      new ApiError(409, {
        code: 'EXPERIMENT_IN_FLIGHT',
        message: 'An experiment is already running. Wait for it to finish.',
        retryable: false,
      })
    );
    renderPage();
    const user = await fillValidForm();
    await user.click(screen.getByRole('button', { name: /Run simulation/ }));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/already running/)
    );
    expect(screen.getByRole('alert')).toHaveTextContent('EXPERIMENT_IN_FLIGHT');
  });
});
