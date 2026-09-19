import { render, screen, within } from '@testing-library/react';
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

  it('renders the metrics version stored with a historical run', () => {
    const versionedRun = {
      ...historicalRun,
      versions: { ...historicalRun.versions, metrics: 'eod-metrics-v0' },
    };

    render(<ResearchResult run={versionedRun} historical />);

    const metricsSection = screen.getByRole('heading', { name: 'Metrics' }).closest('section');
    expect(metricsSection).not.toBeNull();
    expect(within(metricsSection!).getByText('eod-metrics-v0')).toBeVisible();
    expect(screen.queryByText('eod-metrics-v1')).not.toBeInTheDocument();
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

  it('renders interpretation and provenance', () => {
    render(<ResearchResult run={informationalRun} />);

    expect(screen.getByText(/AI interpretation/i)).toBeInTheDocument();
    expect(screen.getByText(informationalRun.snapshot!.content_hash)).toBeInTheDocument();
    expect(screen.getByText(/Not investment advice/i)).toBeInTheDocument();
    expect(screen.getByText(informationalRun.interpretation!.summary)).toBeVisible();
    expect(screen.getByText('positive')).toBeVisible();

    const provenance = screen
      .getByRole('heading', { name: 'Snapshot provenance' })
      .closest('section');
    expect(provenance).not.toBeNull();
    expect(within(provenance!).getByText('yfinance')).toBeVisible();
    expect(within(provenance!).getByText('yfinance-news')).toBeVisible();
    expect(within(provenance!).getByText('fresh')).toBeVisible();
  });

  it('labels model interpretation as qualitative commentary, not a recommendation', () => {
    render(<ResearchResult run={informationalRun} />);

    const interpretation = screen
      .getByRole('heading', { name: 'AI interpretation' })
      .closest('section');
    expect(interpretation).not.toBeNull();
    expect(within(interpretation!).getByText(/qualitative/i)).toBeVisible();
    expect(within(interpretation!).getByText('ev-001')).toBeVisible();
    expect(
      within(interpretation!).queryByText(/buy|sell|trade approved|price target/i)
    ).not.toBeInTheDocument();
  });

  it('renders a legacy v1 run without fabricating interpretation or provenance', () => {
    render(<ResearchResult run={historicalRun} historical />);

    expect(screen.getByText('research-run-response-v1')).toBeInTheDocument();
    expect(
      screen.getByText('Automated interpretation was not recorded for this run.')
    ).toBeVisible();
    expect(
      screen.getByText('Snapshot provenance was not recorded for this run.')
    ).toBeVisible();
  });

  it('renders absent optional run and source fields as unavailable, never fabricated', () => {
    const incompleteRun = {
      ...informationalRun,
      completed_at: null,
      as_of: null,
      research_status: null,
      summary: null,
      model_info: null,
      sources: [
        {
          ...informationalRun.sources[0],
          publisher: null,
          url: null,
          event_time: null,
          content_hash: null,
          title: 'Source with limited metadata',
        },
      ],
    };

    render(<ResearchResult run={incompleteRun} historical />);

    expect(screen.getByText('Summary unavailable for this run.')).toBeVisible();
    expect(screen.getByText('Source with limited metadata')).toBeVisible();
    expect(
      screen.queryByRole('link', { name: /Source with limited metadata/i })
    ).not.toBeInTheDocument();
    expect(screen.getByText('Pending')).toBeInTheDocument();
    expect(screen.getByText('None')).toBeInTheDocument();
  });
});
