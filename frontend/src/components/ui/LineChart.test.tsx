import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import LineChart from './LineChart';

const props = {
  title: 'Simulated value',
  dates: ['2024-01-02', '2024-01-03', '2024-01-04'],
  series: [
    { name: 'Net', values: [100, 110, 105] },
    { name: 'Gross', values: [100, 111, 107] },
    { name: 'Benchmark', values: [100, null, 102] },
  ],
  format: (n: number) => n.toFixed(1),
};

const moves = (d: string | null) => (d ?? '').match(/M/g)?.length ?? 0;

describe('LineChart', () => {
  it('draws one labelled path per series and never bridges a gap', () => {
    const { container } = render(<LineChart {...props} />);
    expect(screen.getByRole('img', { name: 'Simulated value' })).toBeVisible();
    const path = (name: string) =>
      container.querySelector(`path[data-series="${name}"]`)?.getAttribute('d') ?? null;
    expect(moves(path('Net'))).toBe(1);
    expect(moves(path('Gross'))).toBe(1);
    expect(moves(path('Benchmark'))).toBe(2);
  });

  it('offers a data table with the same numbers', async () => {
    render(<LineChart {...props} />);
    expect(screen.queryByRole('table')).toBeNull();
    await userEvent.setup().click(screen.getByRole('button', { name: /data table/i }));
    const table = screen.getByRole('table', { name: 'Simulated value' });
    const headers = within(table).getAllByRole('columnheader').map((h) => h.textContent);
    expect(headers).toEqual(['Date', 'Net', 'Gross', 'Benchmark']);
    const second = within(table).getAllByRole('row')[2];
    expect(second).toHaveTextContent('2024-01-03');
    expect(second).toHaveTextContent('110.0');
    expect(second).toHaveTextContent('111.0');
    expect(second).toHaveTextContent('—');
  });
});
