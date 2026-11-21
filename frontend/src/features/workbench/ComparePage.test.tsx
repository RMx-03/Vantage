import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as api from '../../api/experiments';
import { succeeded } from '../../test/experimentFixtures';
import { SURVIVORSHIP_LABEL } from '../../types/experiments';
import ComparePage from './ComparePage';

const other = {
  ...succeeded,
  id: 'exp-2',
  spec: { ...succeeded.spec, question: 'Same list, higher cost', cost_bps: 20 },
  result: {
    ...succeeded.result!,
    series: { ...succeeded.result!.series!, dates: ['2024-01-03', '2024-01-04', '2024-01-05'] },
  },
};

function renderCompare(query: string) {
  vi.spyOn(api, 'getExperiment').mockImplementation(async (id) =>
    id === 'exp-2' ? other : { ...succeeded, id }
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/app/workbench/compare${query}`]}>
        <Routes>
          <Route path="/app/workbench/compare" element={<ComparePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(() => vi.restoreAllMocks());

describe('ComparePage', () => {
  it.each(['', '?ids=exp-1', '?ids=a,b,c,d,e'])('asks for 2 to 4 ids (%s)', (query) => {
    renderCompare(query);
    expect(screen.getByText(/Choose 2 to 4 experiments/)).toBeVisible();
    expect(api.getExperiment).not.toHaveBeenCalled();
  });

  it('marks assumptions that differ and keeps the label visible', async () => {
    renderCompare('?ids=exp-1,exp-2');
    const table = await screen.findByRole('table', { name: /Assumptions/ });
    expect(await within(table).findByText('Same list, higher cost')).toBeVisible();
    const cost = within(table).getByRole('row', { name: /Cost per side/ });
    expect(cost).toHaveTextContent(/differs/i);
    expect(within(table).getByRole('row', { name: /Symbols/ })).not.toHaveTextContent(
      /differs/i
    );
    expect(screen.getByText(SURVIVORSHIP_LABEL)).toBeVisible();
    expect(screen.getByRole('table', { name: /Metrics/ })).toHaveTextContent('12.34%');
    expect(screen.getByRole('img', { name: /Value rebased to 100/ })).toBeVisible();
  });
});
