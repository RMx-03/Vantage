import type { StrategyParams } from '../../types/experiments';

export const pct = (n: number | null | undefined): string =>
  n === null || n === undefined ? '—' : `${(n * 100).toFixed(2)}%`;

export const num = (n: number | null | undefined, digits = 2): string =>
  n === null || n === undefined ? '—' : n.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

export function describeStrategy(params: StrategyParams): string {
  if (params.template === 'sma_crossover')
    return `MA crossover ${params.fast}/${params.slow}`;
  if (params.template === 'momentum_top_k')
    return `Momentum top ${params.k}, ${params.lookback}-session lookback`;
  return 'Buy and hold, equal weight';
}
