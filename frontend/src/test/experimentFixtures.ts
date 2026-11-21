import type { Experiment, SimulationMetrics } from '../types/experiments';
import { SURVIVORSHIP_LABEL } from '../types/experiments';

export const metrics: SimulationMetrics = {
  sessions: 3,
  total_return: 0.1234,
  cagr: 0.0567,
  volatility: 0.18,
  sharpe: 0.91,
  max_drawdown: -0.152,
  max_drawdown_start: '2024-01-03',
  max_drawdown_end: '2024-01-04',
  turnover: 1.5,
  costs: 0.002,
  exposure: 0.98,
};

export const succeeded: Experiment = {
  id: 'exp-1',
  status: 'succeeded',
  research_status: 'review',
  created_at: '2026-11-22T10:00:00Z',
  started_at: '2026-11-22T10:00:00Z',
  completed_at: '2026-11-22T10:00:05Z',
  spec: {
    question: 'How did an equal-weight hold do?',
    hypothesis: '',
    notes: '',
    symbols: ['AAPL', 'MSFT'],
    benchmark: 'SPY',
    start: '2024-01-02',
    end: '2024-01-04',
    strategy: { template: 'buy_and_hold' },
    cost_bps: 10,
    candidates: [],
  },
  spec_hash: 'spec-hash',
  inputs_hash: 'inputs-hash-0123456789',
  inputs_bytes: 1024,
  result: {
    research_status: 'review',
    label: SURVIVORSHIP_LABEL,
    engine_version: 'backtest-engine-v1',
    metrics_version: 'backtest-metrics-v1',
    metrics,
    benchmark_metrics: { ...metrics, total_return: 0.08, sharpe: null, sharpe_note: 'zero variance' },
    series: {
      dates: ['2024-01-02', '2024-01-03', '2024-01-04'],
      nav: [100000, 101500, 99800],
      gross_nav: [100000, 101600, 99950],
      benchmark_nav: [100000, 100700, 100200],
    },
    trades: [
      { session: '2024-01-03', symbol: 'AAPL', shares: 250, price: 200, notional: 50000 },
    ],
    cost_stress: [
      { multiplier: 0.5, cost_bps: 5, metrics },
      { multiplier: 2, cost_bps: 20, metrics: { ...metrics, total_return: 0.11 } },
    ],
    walk_forward: null,
    findings: [{ code: 'MISSING_SESSIONS', message: 'MSFT is missing 2 sessions.', symbol: 'MSFT', count: 2 }],
    result_hash: 'result-hash',
  },
  versions: { engine: 'backtest-engine-v1', inputs_hash: 'inputs-hash-0123456789', provider: 'alpaca' },
  replay_of: null,
  label: SURVIVORSHIP_LABEL,
};
