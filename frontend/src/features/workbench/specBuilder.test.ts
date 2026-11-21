import { describe, expect, it } from 'vitest';
import { EMPTY_FORM, buildSpec, type ExperimentForm } from './specBuilder';

const form = (extra: Partial<ExperimentForm> = {}): ExperimentForm => ({
  ...EMPTY_FORM,
  question: 'How did an equal-weight hold do?',
  symbols: 'aapl, msft nvda',
  start: '2020-01-02',
  ...extra,
});

const errorsOf = (extra: Partial<ExperimentForm>) => {
  const built = buildSpec(form(extra));
  if (built.ok) throw new Error('expected errors');
  return built.errors;
};

describe('buildSpec', () => {
  it('builds a buy-and-hold spec with normalized symbols and defaults', () => {
    expect(buildSpec(form())).toEqual({
      ok: true,
      spec: {
        question: 'How did an equal-weight hold do?',
        hypothesis: '',
        notes: '',
        symbols: ['AAPL', 'MSFT', 'NVDA'],
        benchmark: 'SPY',
        start: '2020-01-02',
        end: null,
        strategy: { template: 'buy_and_hold' },
        cost_bps: 10,
        candidates: [],
      },
    });
  });

  it('builds SMA and momentum strategies with their candidates', () => {
    const sma = buildSpec(
      form({ template: 'sma_crossover', fast: '20', slow: '100', candidates: '10,50\n30, 200' })
    );
    expect(sma.ok && sma.spec.strategy).toEqual({
      template: 'sma_crossover',
      fast: 20,
      slow: 100,
    });
    expect(sma.ok && sma.spec.candidates).toEqual([
      { template: 'sma_crossover', fast: 10, slow: 50 },
      { template: 'sma_crossover', fast: 30, slow: 200 },
    ]);
    const mom = buildSpec(
      form({ template: 'momentum_top_k', lookback: '252', k: '2', candidates: '126,1' })
    );
    expect(mom.ok && mom.spec.strategy).toEqual({
      template: 'momentum_top_k',
      lookback: 252,
      k: 2,
    });
    expect(mom.ok && mom.spec.candidates).toEqual([
      { template: 'momentum_top_k', lookback: 126, k: 1 },
    ]);
  });

  it.each([
    [{ question: '  ' }, 'question', /Question/],
    [{ symbols: '' }, 'symbols', /Symbols/],
    [{ symbols: 'AAPL aapl' }, 'symbols', /AAPL.*twice/],
    [{ symbols: 'AAPL 1BAD' }, 'symbols', /1BAD/],
    [{ symbols: Array.from({ length: 51 }, (_, i) => `S${i}`).join(' ') }, 'symbols', /50/],
    [{ benchmark: 'spy!' }, 'benchmark', /Benchmark/],
    [{ start: '' }, 'start', /Start/],
    [{ end: '2019-01-01' }, 'end', /End.*after/],
    [{ end: '2031-01-03' }, 'end', /ten years/],
    [{ cost_bps: '101' }, 'cost_bps', /Cost/],
    [{ template: 'sma_crossover', fast: '50', slow: '40' }, 'slow', /Slow.*fast/],
    [{ template: 'sma_crossover', fast: '2', slow: '40' }, 'fast', /Fast/],
    [{ template: 'momentum_top_k', k: '4' }, 'k', /Top k.*symbols/],
    [{ template: 'sma_crossover', candidates: '10' }, 'candidates', /line 1/],
    [{ candidates: '10,50' }, 'candidates', /Candidates/],
  ] as const)('names the field in its error: %o', (extra, field, message) => {
    expect(errorsOf(extra)[field]).toMatch(message);
  });

  it('caps candidates at twelve', () => {
    const lines = Array.from({ length: 13 }, () => '10,50').join('\n');
    expect(errorsOf({ template: 'sma_crossover', candidates: lines }).candidates).toMatch(
      /12/
    );
  });
});
