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
});
