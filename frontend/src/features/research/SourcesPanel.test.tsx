import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SourcesPanel from './SourcesPanel';
import type { EvidenceSource } from '../../types/research';

const newsSource: EvidenceSource = {
  evidence_id: 'ev-001',
  provider: 'yfinance',
  publisher: 'Reuters',
  title: 'Apple Expands Services Revenue in Recent Quarter',
  url: 'https://example.com/news/apple-services',
  event_time: '2026-09-11T14:30:00Z',
  retrieved_at: '2026-09-14T10:00:01Z',
  content_hash: 'abc123hash',
  source_type: 'news',
};

describe('SourcesPanel', () => {
  it('renders a filing source by its title', () => {
    const filing: EvidenceSource = {
      ...newsSource,
      evidence_id: 'ev-002',
      provider: 'sec_edgar',
      publisher: null,
      title: 'Form 8-K current report',
      url: 'https://www.sec.gov/Archives/edgar/data/320193/example.htm',
      source_type: 'filing',
      summary: 'Item 2.02 results of operations',
      details: {
        providers: ['sec_edgar'],
        company_specific: true,
        form_type: '8-K',
        item_codes: ['2.02'],
        transaction_code: null,
        direction: null,
        parse_state: 'parsed',
      },
    };
    render(<SourcesPanel sources={[filing]} />);
    expect(screen.getByRole('link', { name: /Form 8-K current report/ })).toBeInTheDocument();
  });

  it('renders an old source without summary or details', () => {
    render(<SourcesPanel sources={[newsSource]} />);
    expect(screen.getByRole('link', { name: /Apple Expands Services/ })).toBeInTheDocument();
  });

  it('shows the News badge and nothing else for a v2 source', () => {
    const { container } = render(<SourcesPanel sources={[newsSource]} />);
    expect(screen.getByText('News')).toBeInTheDocument();
    expect(screen.queryByText('SEC filing')).not.toBeInTheDocument();
    expect(screen.queryByText('Insider filing')).not.toBeInTheDocument();
    expect(screen.queryByText('Company-specific')).not.toBeInTheDocument();
    expect(screen.queryByText(/Reported by/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Details not parsed/)).not.toBeInTheDocument();
    expect(container.querySelectorAll('p')).toHaveLength(0);
    expect(screen.getByText('ID: ev-001')).toBeInTheDocument();
  });

  it('falls back to the News badge for an unknown source type', () => {
    const odd = { ...newsSource, source_type: 'podcast' } as unknown as EvidenceSource;
    render(<SourcesPanel sources={[odd]} />);
    expect(screen.getByText('News')).toBeInTheDocument();
  });

  it('renders a filing with its badge, form type and item codes', () => {
    const filing: EvidenceSource = {
      ...newsSource,
      evidence_id: 'ev-002',
      provider: 'sec_edgar',
      source_type: 'filing',
      title: 'Quarterly report',
      details: { form_type: '8-K', item_codes: ['2.02', '9.01'], parse_state: 'parsed' },
    };
    render(<SourcesPanel sources={[filing]} />);
    expect(screen.getByText('SEC filing')).toBeInTheDocument();
    expect(screen.getByText('8-K')).toBeInTheDocument();
    expect(screen.getByText('Items 2.02, 9.01')).toBeInTheDocument();
    expect(screen.queryByText('Company-specific')).not.toBeInTheDocument();
  });

  it('renders an insider filing with its code and direction', () => {
    const insider: EvidenceSource = {
      ...newsSource,
      evidence_id: 'ev-003',
      source_type: 'insider_transaction',
      details: { form_type: '4', transaction_code: 'S', direction: 'disposed' },
    };
    render(<SourcesPanel sources={[insider]} />);
    expect(screen.getByText('Insider filing')).toBeInTheDocument();
    expect(screen.getByText('Transaction code S')).toBeInTheDocument();
    expect(screen.getByText('disposed')).toBeInTheDocument();
  });

  it('says when an insider filing was not parsed', () => {
    const insider: EvidenceSource = {
      ...newsSource,
      source_type: 'insider_transaction',
      details: { parse_state: 'unparsed' },
    };
    render(<SourcesPanel sources={[insider]} />);
    expect(screen.getByText('Details not parsed')).toBeInTheDocument();
    expect(screen.queryByText(/Transaction code/)).not.toBeInTheDocument();
  });

  it('marks company-specific sources and multiple reporting providers', () => {
    const src: EvidenceSource = {
      ...newsSource,
      details: { providers: ['alpaca', 'finnhub'], company_specific: true },
    };
    render(<SourcesPanel sources={[src]} />);
    expect(screen.getByText('Company-specific')).toBeInTheDocument();
    expect(screen.getByText('Reported by alpaca, finnhub')).toBeInTheDocument();
  });

  it('omits the providers line for one provider and the marker when false', () => {
    const src: EvidenceSource = {
      ...newsSource,
      details: { providers: ['alpaca'], company_specific: false },
    };
    render(<SourcesPanel sources={[src]} />);
    expect(screen.queryByText(/Reported by/)).not.toBeInTheDocument();
    expect(screen.queryByText('Company-specific')).not.toBeInTheDocument();
  });

  it('renders a summary containing markup as text', () => {
    const src: EvidenceSource = {
      ...newsSource,
      summary: 'Results <script>window.__pwned = 1</script> <b>bold</b>',
    };
    const { container } = render(<SourcesPanel sources={[src]} />);
    const p = screen.getByText(/Results <script>/);
    expect(p.tagName).toBe('P');
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('b')).toBeNull();
  });

  it('does not render an empty summary', () => {
    const { container } = render(<SourcesPanel sources={[{ ...newsSource, summary: '' }]} />);
    expect(container.querySelectorAll('p')).toHaveLength(0);
  });
});
