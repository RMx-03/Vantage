// Mirrors backend/app/domain/experiments.py (ADR-0008).
import type { ResearchStatus, WorkflowStatus } from './research';

// Same text as SURVIVORSHIP_LABEL in the backend; every result carries it.
export const SURVIVORSHIP_LABEL =
  'Exploratory: list chosen today, survivorship bias possible';

export type Template = 'buy_and_hold' | 'sma_crossover' | 'momentum_top_k';

export const TEMPLATE_LABELS: Record<Template, string> = {
  buy_and_hold: 'Equal-weight hold',
  sma_crossover: 'MA crossover',
  momentum_top_k: 'Momentum top k',
};

export interface BuyAndHoldParams {
  template: 'buy_and_hold';
}

export interface SmaCrossoverParams {
  template: 'sma_crossover';
  fast: number;
  slow: number;
}

export interface MomentumTopKParams {
  template: 'momentum_top_k';
  lookback: 126 | 252;
  skip?: 21;
  k: number;
}

export type StrategyParams = BuyAndHoldParams | SmaCrossoverParams | MomentumTopKParams;

export interface ExperimentSpec {
  question: string;
  hypothesis?: string;
  notes?: string;
  symbols: string[];
  benchmark?: string;
  start: string;
  end?: string | null;
  strategy: StrategyParams;
  cost_bps?: number;
  candidates?: StrategyParams[];
}

export interface Finding {
  code: string;
  message: string;
  symbol?: string | null;
  count?: number | null;
}

export interface SimulationMetrics {
  sessions: number;
  total_return: number;
  cagr: number | null;
  volatility: number | null;
  sharpe: number | null;
  sharpe_note?: string | null;
  max_drawdown: number;
  max_drawdown_start?: string | null;
  max_drawdown_end?: string | null;
  turnover: number;
  costs: number;
  exposure: number;
}

export interface SimulationSeries {
  dates: string[];
  nav: number[];
  gross_nav: number[];
  benchmark_nav?: number[] | null;
}

export interface SimulatedTrade {
  session: string;
  symbol: string;
  shares: number;
  price: number;
  notional: number;
}

export interface CostStress {
  multiplier: number;
  cost_bps: number;
  metrics: SimulationMetrics;
}

export interface CandidateTrial {
  index: number;
  params: StrategyParams;
  status: 'succeeded' | 'failed' | 'not_run';
  error?: string | null;
}

export interface WalkForwardWindow {
  train_start: string;
  train_end: string;
  test_start: string;
  test_end: string;
  selected: number | null;
  train_sharpe: number | null;
}

export interface WalkForwardResult {
  status: 'complete' | 'insufficient_data';
  windows: WalkForwardWindow[];
  trials: CandidateTrial[];
  trial_count: number;
  oos_metrics?: SimulationMetrics | null;
  oos_series?: SimulationSeries | null;
}

export interface ExperimentResult {
  research_status: ResearchStatus;
  label: string;
  engine_version: string;
  metrics_version: string;
  metrics?: SimulationMetrics | null;
  benchmark_metrics?: SimulationMetrics | null;
  series?: SimulationSeries | null;
  trades: SimulatedTrade[]; // the first fills only
  trade_count?: number | null; // every fill the simulation made
  cost_stress: CostStress[];
  walk_forward?: WalkForwardResult | null;
  findings: Finding[];
  result_hash: string;
}

export interface ExperimentPlan {
  end: string;
  fetch_start: string;
  sessions: number;
  warmup_sessions: number;
  windows: number;
  candidates: number;
  engine_invocations: number;
  warnings: string[];
}

export interface Experiment {
  id: string;
  status: WorkflowStatus;
  research_status: ResearchStatus | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
  started_at: string;
  completed_at?: string | null;
  spec: ExperimentSpec;
  spec_hash: string;
  inputs_hash?: string | null;
  inputs_bytes: number;
  result?: ExperimentResult | null;
  versions: Record<string, string>;
  replay_of?: string | null;
  label: string;
}

export interface ExperimentSummary {
  id: string;
  status: WorkflowStatus;
  research_status: ResearchStatus | null;
  created_at: string;
  question: string;
  template: Template;
  symbols: string[];
  start: string;
  end: string | null;
  replay_of?: string | null;
}

export type ExportFormat = 'json' | 'csv';
