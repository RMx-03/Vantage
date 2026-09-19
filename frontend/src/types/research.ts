export type WorkflowStatus = 'running' | 'succeeded' | 'failed';
export type ResearchStatus = 'informational' | 'review' | 'insufficient_data' | 'failed';
export type OverallQuality = 'sufficient' | 'degraded' | 'insufficient';
export type ComponentQuality = 'fresh' | 'partial' | 'stale' | 'missing' | 'failed';
export type ModelQuality = 'healthy' | 'degraded' | 'failed' | 'not_run';

export type MetricUnit = 'ratio' | 'percent' | 'usd' | 'count' | 'sessions';
export type ReasonSeverity = 'info' | 'warning' | 'blocking';

export interface ResearchMetric {
  key: string;
  label: string;
  value: number | null;
  unit: MetricUnit;
  window_sessions: number | null;
  as_of: string;
  calculation_version: string;
  quality: ComponentQuality;
}

export interface Reason {
  code: string;
  label: string;
  severity: ReasonSeverity;
  description: string;
  metric_keys: string[];
  evidence_ids: string[];
  policy_version: string;
  threshold?: number | null;
}

export interface DataQuality {
  overall: OverallQuality;
  prices: ComponentQuality;
  news: ComponentQuality;
  model: ModelQuality;
}

export interface EvidenceSource {
  evidence_id: string;
  provider: string;
  publisher?: string | null;
  title: string;
  url?: string | null;
  event_time?: string | null;
  retrieved_at: string;
  content_hash?: string | null;
  source_type: 'news';
}

export type SentimentLabel = 'positive' | 'mixed' | 'neutral' | 'negative' | 'unavailable';

export interface AIInterpretation {
  sentiment_label: SentimentLabel;
  sentiment_score: number | null;
  summary: string;
  evidence_ids: string[];
  warnings: string[];
  abstained: boolean;
  abstention_reason: string | null;
}

export interface SnapshotProvenance {
  snapshot_id: string;
  content_hash: string;
  market_provider: string;
  market_content_hash: string;
  market_as_of: string;
  market_retrieved_at: string;
  window_start: string;
  window_end: string;
  news_provider: string;
  news_retrieved_at: string;
  news_coverage_start: string | null;
  news_coverage_end: string | null;
  news_quality: ComponentQuality;
}

export interface ModelInfo {
  provider: string;
  model: string;
  prompt_version: string;
  failure_code?: string | null;
}

export interface VersionInfo {
  response_schema: string;
  workflow: string;
  metrics: string;
  policy: string;
  code: string;
}

export interface ResearchRun {
  run_id: string;
  symbol: string;
  created_at: string;
  completed_at: string | null;
  as_of: string | null;
  workflow_status: WorkflowStatus;
  research_status: ResearchStatus | null;
  summary: string | null;
  reasons: Reason[];
  metrics: ResearchMetric[];
  data_quality: DataQuality | null;
  sources: EvidenceSource[];
  warnings: string[];
  model_info: ModelInfo | null;
  interpretation: AIInterpretation | null;
  snapshot: SnapshotProvenance | null;
  versions: VersionInfo;
  error_code?: string | null;
  error_message_safe?: string | null;
}

export interface ResearchRunPage {
  items: ResearchRun[];
  next_cursor: string | null;
}

export interface SafeError {
  code: string;
  message: string;
  run_id?: string | null;
  request_id?: string | null;
  retryable?: boolean;
}
