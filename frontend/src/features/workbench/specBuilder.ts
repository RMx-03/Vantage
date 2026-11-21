// Client-side mirror of ExperimentSpec's rules, so every error names its field.
// The server re-validates; its 422 carries no field detail.
import type { ExperimentSpec, StrategyParams, Template } from '../../types/experiments';

export interface ExperimentForm {
  question: string;
  hypothesis: string;
  notes: string;
  symbols: string;
  benchmark: string;
  start: string;
  end: string;
  template: Template;
  fast: string;
  slow: string;
  lookback: string;
  k: string;
  cost_bps: string;
  candidates: string;
}

export type FormField = keyof ExperimentForm;
export type FormErrors = Partial<Record<FormField, string>>;
export type BuiltSpec =
  | { ok: true; spec: ExperimentSpec }
  | { ok: false; errors: FormErrors };

export const EMPTY_FORM: ExperimentForm = {
  question: '',
  hypothesis: '',
  notes: '',
  symbols: '',
  benchmark: 'SPY',
  start: '',
  end: '',
  template: 'buy_and_hold',
  fast: '50',
  slow: '200',
  lookback: '252',
  k: '3',
  cost_bps: '10',
  candidates: '',
};

const SYMBOL = /^[A-Z][A-Z0-9.]{0,9}$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const MAX_SYMBOLS = 50;
const MAX_CANDIDATES = 12;
const MAX_RANGE_DAYS = 3653;
const DAY_MS = 86_400_000;

const int = (raw: string): number | null => (/^\s*\d+\s*$/.test(raw) ? Number(raw) : null);
const between = (n: number | null, lo: number, hi: number): n is number =>
  n !== null && n >= lo && n <= hi;

/** Template parameters from two numbers; returns the params or an error message. */
function params(
  template: Template,
  a: number | null,
  b: number | null,
  symbolCount: number
): StrategyParams | { field: FormField; message: string } {
  if (template === 'sma_crossover') {
    if (!between(a, 5, 100)) return { field: 'fast', message: 'Fast: 5 to 100 sessions.' };
    if (!between(b, 20, 250)) return { field: 'slow', message: 'Slow: 20 to 250 sessions.' };
    if (a >= b) return { field: 'slow', message: 'Slow: must be longer than fast.' };
    return { template, fast: a, slow: b };
  }
  if (template === 'momentum_top_k') {
    if (a !== 126 && a !== 252)
      return { field: 'lookback', message: 'Lookback: 126 or 252 sessions.' };
    if (!between(b, 1, 10)) return { field: 'k', message: 'Top k: 1 to 10.' };
    if (b > symbolCount)
      return { field: 'k', message: 'Top k: cannot exceed the number of symbols.' };
    return { template, lookback: a, k: b };
  }
  return { template: 'buy_and_hold' };
}

export function buildSpec(form: ExperimentForm): BuiltSpec {
  const errors: FormErrors = {};
  const question = form.question.trim();
  if (!question || question.length > 500)
    errors.question = 'Question: required, up to 500 characters.';
  if (form.hypothesis.length > 1000)
    errors.hypothesis = 'Hypothesis: up to 1,000 characters.';
  if (form.notes.length > 4000) errors.notes = 'Notes: up to 4,000 characters.';

  const symbols = form.symbols.toUpperCase().split(/[\s,]+/).filter(Boolean);
  const duplicate = symbols.find((s, i) => symbols.indexOf(s) !== i);
  const invalid = symbols.find((s) => !SYMBOL.test(s));
  if (symbols.length === 0 || symbols.length > MAX_SYMBOLS)
    errors.symbols = `Symbols: enter 1 to ${MAX_SYMBOLS} tickers.`;
  else if (invalid) errors.symbols = `Symbols: ${invalid} is not a valid ticker.`;
  else if (duplicate) errors.symbols = `Symbols: ${duplicate} is listed twice.`;

  const benchmark = form.benchmark.trim().toUpperCase();
  if (!SYMBOL.test(benchmark)) errors.benchmark = 'Benchmark: enter one valid ticker.';

  if (!DATE.test(form.start)) errors.start = 'Start: choose a date.';
  if (form.end && !DATE.test(form.end)) errors.end = 'End: choose a valid date.';
  else if (form.end && DATE.test(form.start)) {
    const days = (Date.parse(form.end) - Date.parse(form.start)) / DAY_MS;
    if (days <= 0) errors.end = 'End: must be after the start date.';
    else if (days > MAX_RANGE_DAYS) errors.end = 'End: the range is limited to ten years.';
  }

  const cost = Number(form.cost_bps);
  if (form.cost_bps.trim() === '' || !(cost >= 0 && cost <= 100))
    errors.cost_bps = 'Cost: 0 to 100 basis points per side.';

  const [a, b] =
    form.template === 'sma_crossover'
      ? [int(form.fast), int(form.slow)]
      : [int(form.lookback), int(form.k)];
  const strategy = params(form.template, a, b, symbols.length);
  if ('field' in strategy) errors[strategy.field] = strategy.message;

  const lines = form.candidates.split('\n').map((l) => l.trim()).filter(Boolean);
  const candidates: StrategyParams[] = [];
  if (lines.length > 0 && form.template === 'buy_and_hold')
    errors.candidates = 'Candidates: buy and hold has no parameters to compare.';
  else if (lines.length > MAX_CANDIDATES)
    errors.candidates = `Candidates: at most ${MAX_CANDIDATES} lines.`;
  else {
    for (const [i, line] of lines.entries()) {
      const parts = line.split(',').map(int);
      const built =
        parts.length === 2 ? params(form.template, parts[0], parts[1], symbols.length) : null;
      if (!built || 'field' in built) {
        errors.candidates = `Candidates: line ${i + 1} needs two numbers in range, e.g. ${
          form.template === 'sma_crossover' ? '20,100' : '126,3'
        }.`;
        break;
      }
      candidates.push(built);
    }
  }

  if (Object.keys(errors).length > 0 || 'field' in strategy) return { ok: false, errors };
  return {
    ok: true,
    spec: {
      question,
      hypothesis: form.hypothesis.trim(),
      notes: form.notes.trim(),
      symbols,
      benchmark,
      start: form.start,
      end: form.end || null,
      strategy,
      cost_bps: cost,
      candidates,
    },
  };
}
