import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ResearchMetrics from './ResearchMetrics';
import type { ResearchMetric } from '../../types/research';

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
});
