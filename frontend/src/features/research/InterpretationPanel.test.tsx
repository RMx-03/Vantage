import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import InterpretationPanel from './InterpretationPanel';
import { informationalRun, informationalRunV3 } from '../../test/fixtures';
import type { AIInterpretation } from '../../types/research';

const base = informationalRunV3.interpretation as AIInterpretation;

describe('InterpretationPanel attribution', () => {
  const cases: Array<[NonNullable<AIInterpretation['attribution']>, string]> = [
    ['market', 'The move tracked the broad market.'],
    ['sector', 'The move tracked the sector more than the broad market.'],
    ['company', 'Company-specific evidence explains the move.'],
    ['mixed', 'Both company evidence and market or sector movement are involved.'],
    ['unclear', 'The evidence does not support an attribution.'],
  ];

  it.each(cases)('shows %s with its meaning', (value, meaning) => {
    render(<InterpretationPanel interpretation={{ ...base, attribution: value }} />);
    expect(screen.getByText(`Attribution: ${value}`)).toBeInTheDocument();
    expect(screen.getByText(meaning)).toBeInTheDocument();
  });

  it('shows an unknown value raw with no meaning line', () => {
    const odd = { ...base, attribution: 'macro' } as unknown as AIInterpretation;
    render(<InterpretationPanel interpretation={odd} />);
    expect(screen.getByText('Attribution: macro')).toBeInTheDocument();
    expect(screen.queryByTestId('attribution-meaning')).not.toBeInTheDocument();
  });

  it('shows nothing new for an old interpretation', () => {
    render(<InterpretationPanel interpretation={informationalRun.interpretation} />);
    expect(screen.queryByText(/Attribution/)).not.toBeInTheDocument();
  });

  it('shows nothing for a null or empty attribution', () => {
    const { rerender } = render(
      <InterpretationPanel interpretation={{ ...base, attribution: null }} />
    );
    expect(screen.queryByText(/Attribution/)).not.toBeInTheDocument();
    rerender(
      <InterpretationPanel
        interpretation={{ ...base, attribution: '' as unknown as AIInterpretation['attribution'] }}
      />
    );
    expect(screen.queryByText(/Attribution/)).not.toBeInTheDocument();
  });
});
