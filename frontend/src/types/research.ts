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
  calculation_version: 'eod-metrics-v1';
  quality: ComponentQuality;
}

export interface Reason {
  code: string;
  label: string;
  severity: ReasonSeverity;
  description: string;
  metric_keys: string[];
  evidence_ids: string[];
  policy_version: 'research-policy-v1';
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

export interface ModelInfo {
  provider: string;
  model: string;
  prompt_version: 'research-interpretation-v1';
  failure_code?: string | null;
}

export interface VersionInfo {
  response_schema: 'research-run-response-v1';
  workflow: 'eod-research-v1';
  metrics: 'eod-metrics-v1';
  policy: 'research-policy-v1';
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
