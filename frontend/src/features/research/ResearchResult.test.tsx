import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ResearchResult from './ResearchResult';
import {
  informationalRun,
  reviewRun,
  insufficientRun,
  historicalRun,
  failedMarketRun,
} from '../../test/fixtures';

describe('ResearchResult', () => {
  it('renders why, metrics, quality, sources, and run details in order', () => {
    render(<ResearchResult run={reviewRun} historical={false} />);
    const headings = screen.getAllByRole('heading').map((node) => node.textContent);
    expect(headings).toEqual(
      expect.arrayContaining([
        'Why this result?',
        'Metrics',
        'Data quality',
        'Sources',
        'Run details',
      ])
    );
    expect(screen.getByText('AI interpretation unavailable')).toBeVisible();
    expect(screen.queryByText(/approved|rejected/i)).not.toBeInTheDocument();
  });

  it('does not display missing values as zero', () => {
    render(<ResearchResult run={insufficientRun} historical={false} />);
    expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0);
    expect(screen.queryByText('0.00%')).not.toBeInTheDocument();
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument();
  });

  it('renders historical marker when historical is true', () => {
    render(<ResearchResult run={historicalRun} historical={true} />);
    expect(screen.getByText(/historical run/i)).toBeVisible();
  });

  it('renders volatility context note', () => {
    render(<ResearchResult run={informationalRun} historical={false} />);
    expect(
      screen.getByText(/20-session annualized single-security variability; not portfolio risk/i)
    ).toBeVisible();
  });

  it('renders neutral research status styling without trade approval', () => {
    render(<ResearchResult run={informationalRun} historical={false} />);
    expect(screen.getAllByText('informational').length).toBeGreaterThan(0);
    expect(screen.getAllByText('informational')[0]).toBeVisible();
    expect(screen.queryByText(/trade approved|buy|sell/i)).not.toBeInTheDocument();
  });

  it('renders failed run gracefully without fabricating results', () => {
    render(<ResearchResult run={failedMarketRun} historical={false} />);
    expect(screen.getByText('Market data provider returned an error.')).toBeVisible();
    expect(screen.getAllByText(failedMarketRun.run_id).length).toBeGreaterThan(0);
    expect(screen.getAllByText(failedMarketRun.run_id)[0]).toBeVisible();
  });
});
