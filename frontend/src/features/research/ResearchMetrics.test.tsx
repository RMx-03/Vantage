import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ResearchMetrics from './ResearchMetrics';
import type { ResearchMetric } from '../../types/research';
import { informationalRun, informationalRunV3, keylessRunV3 } from '../../test/fixtures';

const baseMetric: ResearchMetric = {
  key: 'metric',
  label: 'Metric',
  value: 1,
  unit: 'count',
  window_sessions: null,
  as_of: '2026-09-11T20:00:00Z',
  calculation_version: 'eod-metrics-v1',
  quality: 'fresh',
};

describe('ResearchMetrics', () => {
  it('formats native values without converting unavailable data to zero', () => {
    const metrics: ResearchMetric[] = [
      { ...baseMetric, key: 'ratio', label: 'Ratio', value: 0.125, unit: 'ratio' },
      { ...baseMetric, key: 'percent', label: 'Percent', value: 12.5, unit: 'percent' },
      { ...baseMetric, key: 'usd', label: 'Liquidity', value: 2_500_000, unit: 'usd' },
      { ...baseMetric, key: 'sessions', label: 'Sessions', value: 21, unit: 'sessions' },
      {
        ...baseMetric,
        key: 'missing',
        label: 'Missing',
        value: null,
        quality: 'missing',
      },
    ];

    render(<ResearchMetrics metrics={metrics} version="eod-metrics-v1" />);

    expect(screen.getAllByText('12.50%')).toHaveLength(2);
    expect(screen.getByText('$2.50M')).toBeVisible();
    expect(screen.getByText('21')).toBeVisible();
    expect(screen.getByText('Unavailable')).toBeVisible();
    expect(screen.getAllByText('Full snapshot')).toHaveLength(metrics.length);
  });

  it('renders the empty state without a volatility claim', () => {
    render(<ResearchMetrics metrics={[]} version="historical-metrics-v0" />);

    expect(screen.getByText(/No quantitative metrics computed/i)).toBeVisible();
    expect(screen.getByText('historical-metrics-v0')).toBeVisible();
    expect(screen.queryByText(/single-security variability/i)).not.toBeInTheDocument();
  });

  it('groups a v3 run under five headings with the FRED and Cboe lines', () => {
    render(<ResearchMetrics metrics={informationalRunV3.metrics} version="eod-metrics-v3" />);

    const headings = screen.getAllByRole('heading', { level: 3 }).map((n) => n.textContent);
    expect(headings).toEqual([
      'Price',
      'Relative',
      'Fundamentals',
      'Macro',
      'Evidence and checks',
    ]);
    expect(screen.getByText('Fiscal year ending Jun 27, 2026')).toBeVisible();
    expect(screen.getAllByText('As of Sep 10, 2026')).toHaveLength(4);
    expect(
      screen.getByText(
        'This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.'
      )
    ).toBeVisible();
    expect(screen.getByText('VIX close: © Cboe, via FRED.')).toBeVisible();
    expect(screen.getByText('16.00')).toBeVisible();
  });

  it('renders a v2 run with no new groups, role rows or fabricated zeros', () => {
    render(<ResearchMetrics metrics={informationalRun.metrics} version="eod-metrics-v2" />);

    const headings = screen.getAllByRole('heading', { level: 3 }).map((n) => n.textContent);
    expect(headings).toEqual(['Other']);
    for (const name of ['Relative', 'Fundamentals', 'Macro']) {
      expect(screen.queryByRole('heading', { name })).not.toBeInTheDocument();
    }
    expect(screen.queryByText(/FRED/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/via FRED/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Fiscal year ending/)).not.toBeInTheDocument();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
    expect(screen.queryByText('0.00%')).not.toBeInTheDocument();
  });

  it('shows Unavailable, with no dates or attribution, when optional roles are absent', () => {
    render(<ResearchMetrics metrics={keylessRunV3.metrics} version="eod-metrics-v3" />);

    expect(screen.getByRole('heading', { name: 'Macro' })).toBeVisible();
    expect(screen.getAllByText('Unavailable')).toHaveLength(9);
    expect(screen.queryByText(/Fiscal year ending/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^As of /)).not.toBeInTheDocument();
    expect(screen.queryByText(/FRED/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/via FRED/)).not.toBeInTheDocument();
    expect(screen.queryByText('16.00')).not.toBeInTheDocument();
  });

  it('shows a real zero as zero, not Unavailable', () => {
    const metrics = informationalRunV3.metrics.filter((m) =>
      ['filing_count_30d', 'yield_curve_10y_2y'].includes(m.key)
    );
    expect(metrics).toHaveLength(2);
    render(
      <ResearchMetrics metrics={metrics.map((m) => ({ ...m, value: 0 }))} version="eod-metrics-v3" />
    );
    expect(screen.getByText('0')).toBeVisible();
    expect(screen.getByText('0.00%')).toBeVisible();
    expect(screen.queryByText('Unavailable')).not.toBeInTheDocument();
  });
});
