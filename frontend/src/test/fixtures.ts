import type { ProviderRecord, ResearchMetric, ResearchRun } from '../types/research';

const baseVersions = {
  response_schema: 'research-run-response-v2' as const,
  workflow: 'eod-research-v1' as const,
  metrics: 'eod-metrics-v2' as const,
  policy: 'research-policy-v1' as const,
  code: 'git-commit-hash-test',
};

export const informationalRun: ResearchRun = {
  run_id: 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  symbol: 'AAPL',
  created_at: '2026-09-14T10:00:00Z',
  completed_at: '2026-09-14T10:00:02Z',
  as_of: '2026-09-11T20:00:00Z',
  workflow_status: 'succeeded',
  research_status: 'informational',
  summary: 'All required EOD price and news criteria are satisfied with sufficient quality.',
  reasons: [
    {
      code: 'EOD_COMPLETE',
      label: 'Sufficient Data & Signals',
      severity: 'info',
      description: 'All 21 trading sessions verified with fresh market and news coverage.',
      metric_keys: ['return_20d', 'volatility_20d', 'avg_dollar_volume_20d'],
      evidence_ids: ['ev-001'],
      policy_version: 'research-policy-v1',
      threshold: null,
    },
  ],
  metrics: [
    {
      key: 'return_20d',
      label: '20-Session Return',
      value: 0.0452,
      unit: 'ratio',
      window_sessions: 20,
      as_of: '2026-09-11T20:00:00Z',
      calculation_version: 'eod-metrics-v2',
      quality: 'fresh',
    },
    {
      key: 'volatility_20d',
      label: '20-Session Volatility',
      value: 0.2215,
      unit: 'ratio',
      window_sessions: 20,
      as_of: '2026-09-11T20:00:00Z',
      calculation_version: 'eod-metrics-v2',
      quality: 'fresh',
    },
    {
      key: 'avg_dollar_volume_20d',
      label: '20-Session Avg Dollar Volume',
      value: 12500000000,
      unit: 'usd',
      window_sessions: 20,
      as_of: '2026-09-11T20:00:00Z',
      calculation_version: 'eod-metrics-v2',
      quality: 'fresh',
    },
    {
      key: 'session_count',
      label: 'Completed Sessions Evaluated',
      value: 21,
      unit: 'count',
      window_sessions: 21,
      as_of: '2026-09-11T20:00:00Z',
      calculation_version: 'eod-metrics-v2',
      quality: 'fresh',
    },
  ],
  data_quality: {
    overall: 'sufficient',
    prices: 'fresh',
    news: 'fresh',
    model: 'healthy',
  },
  sources: [
    {
      evidence_id: 'ev-001',
      provider: 'yfinance',
      publisher: 'Reuters',
      title: 'Apple Expands Services Revenue in Recent Quarter',
      url: 'https://example.com/news/apple-services',
      event_time: '2026-09-11T14:30:00Z',
      retrieved_at: '2026-09-14T10:00:01Z',
      content_hash: 'abc123hash',
      source_type: 'news',
    },
  ],
  warnings: [],
  model_info: {
    provider: 'google',
    model: 'gemini-2.5-flash',
    prompt_version: 'research-interpretation-v1',
    failure_code: null,
  },
  interpretation: {
    sentiment_label: 'positive',
    sentiment_score: 0.42,
    summary:
      'Recent coverage describes steady services growth alongside an unchanged product mix.',
    evidence_ids: ['ev-001'],
    warnings: [],
    abstained: false,
    abstention_reason: null,
  },
  snapshot: {
    snapshot_id: 'f1eebc99-9c0b-4ef8-bb6d-6bb9bd380a66',
    content_hash: '4f0c1d2e3a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5',
    market_provider: 'yfinance',
    market_content_hash:
      '9a8b7c6d5e4f30291a0b1c2d3e4f5061728394a5b6c7d8e9f0a1b2c3d4e5f607',
    market_as_of: '2026-09-11T20:00:00Z',
    market_retrieved_at: '2026-09-14T10:00:00Z',
    window_start: '2026-08-13T00:00:00Z',
    window_end: '2026-09-11T23:59:59Z',
    news_provider: 'yfinance-news',
    news_retrieved_at: '2026-09-14T10:00:01Z',
    news_coverage_start: '2026-09-07T20:00:00Z',
    news_coverage_end: '2026-09-11T20:00:00Z',
    news_quality: 'fresh',
  },
  versions: baseVersions,
  error_code: null,
  error_message_safe: null,
};

export const reviewRun: ResearchRun = {
  run_id: 'b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a22',
  symbol: 'AAPL',
  created_at: '2026-09-14T10:05:00Z',
  completed_at: '2026-09-14T10:05:02Z',
  as_of: '2026-09-11T20:00:00Z',
  workflow_status: 'succeeded',
  research_status: 'review',
  summary: 'Research status is review due to AI interpretation failure.',
  reasons: [
    {
      code: 'MODEL_FAILED',
      label: 'Model Failure',
      severity: 'warning',
      description: 'AI interpretation unavailable',
      metric_keys: [],
      evidence_ids: [],
      policy_version: 'research-policy-v1',
      threshold: null,
    },
  ],
  metrics: [
    {
      key: 'return_20d',
      label: '20-Session Return',
      value: -0.0123,
      unit: 'ratio',
      window_sessions: 20,
      as_of: '2026-09-11T20:00:00Z',
      calculation_version: 'eod-metrics-v2',
      quality: 'fresh',
    },
    {
      key: 'volatility_20d',
      label: '20-Session Volatility',
      value: 0.185,
      unit: 'ratio',
      window_sessions: 20,
      as_of: '2026-09-11T20:00:00Z',
      calculation_version: 'eod-metrics-v2',
      quality: 'fresh',
    },
  ],
  data_quality: {
    overall: 'degraded',
    prices: 'fresh',
    news: 'fresh',
    model: 'failed',
  },
  sources: [
    {
      evidence_id: 'ev-002',
      provider: 'yfinance',
      publisher: 'Bloomberg',
      title: 'Tech Stocks Mixed Ahead of Fed Decision',
      url: 'https://example.com/news/tech-mixed',
      event_time: '2026-09-11T16:00:00Z',
      retrieved_at: '2026-09-14T10:05:01Z',
      content_hash: 'def456hash',
      source_type: 'news',
    },
  ],
  warnings: ['AI interpretation unavailable; showing quantitative metrics only.'],
  model_info: {
    provider: 'google',
    model: 'gemini-2.5-flash',
    prompt_version: 'research-interpretation-v1',
    failure_code: 'MODEL_UNAVAILABLE',
  },
  interpretation: {
    sentiment_label: 'unavailable',
    sentiment_score: null,
    summary: 'AI interpretation was unavailable for this research run.',
    evidence_ids: [],
    warnings: ['AI interpretation failed or was unavailable.'],
    abstained: true,
    abstention_reason: 'MODEL_UNAVAILABLE',
  },
  snapshot: {
    snapshot_id: 'f2eebc99-9c0b-4ef8-bb6d-6bb9bd380a77',
    content_hash: '1122334455667788990011223344556677889900112233445566778899001122',
    market_provider: 'yfinance',
    market_content_hash:
      '2233445566778899001122334455667788990011223344556677889900112233',
    market_as_of: '2026-09-11T20:00:00Z',
    market_retrieved_at: '2026-09-14T10:05:00Z',
    window_start: '2026-08-13T00:00:00Z',
    window_end: '2026-09-11T23:59:59Z',
    news_provider: 'yfinance-news',
    news_retrieved_at: '2026-09-14T10:05:01Z',
    news_coverage_start: '2026-09-07T20:00:00Z',
    news_coverage_end: '2026-09-11T20:00:00Z',
    news_quality: 'fresh',
  },
  versions: baseVersions,
  error_code: null,
  error_message_safe: null,
};

export const insufficientRun: ResearchRun = {
  run_id: 'c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a33',
  symbol: 'AAPL',
  created_at: '2026-09-14T10:10:00Z',
  completed_at: '2026-09-14T10:10:02Z',
  as_of: '2026-09-11T20:00:00Z',
  workflow_status: 'succeeded',
  research_status: 'insufficient_data',
  summary: 'Research status is insufficient_data because required price history is missing or stale.',
  reasons: [
    {
      code: 'PRICE_INSUFFICIENT',
      label: 'Insufficient Price History',
      severity: 'blocking',
      description: 'Required 21 valid completed closes could not be retrieved.',
      metric_keys: ['return_20d', 'volatility_20d'],
      evidence_ids: [],
      policy_version: 'research-policy-v1',
      threshold: 21,
    },
  ],
  metrics: [
    {
      key: 'return_20d',
      label: '20-Session Return',
      value: null,
      unit: 'ratio',
      window_sessions: 20,
      as_of: '2026-09-11T20:00:00Z',
      calculation_version: 'eod-metrics-v2',
      quality: 'missing',
    },
    {
      key: 'volatility_20d',
      label: '20-Session Volatility',
      value: null,
      unit: 'ratio',
      window_sessions: 20,
      as_of: '2026-09-11T20:00:00Z',
      calculation_version: 'eod-metrics-v2',
      quality: 'missing',
    },
  ],
  data_quality: {
    overall: 'insufficient',
    prices: 'missing',
    news: 'missing',
    model: 'not_run',
  },
  sources: [],
  warnings: ['Missing required price history.'],
  model_info: null,
  interpretation: null,
  snapshot: {
    snapshot_id: 'f3eebc99-9c0b-4ef8-bb6d-6bb9bd380a88',
    content_hash: '3344556677889900112233445566778899001122334455667788990011223344',
    market_provider: 'yfinance',
    market_content_hash:
      '4455667788990011223344556677889900112233445566778899001122334455',
    market_as_of: '2026-09-11T20:00:00Z',
    market_retrieved_at: '2026-09-14T10:10:00Z',
    window_start: '2026-08-13T00:00:00Z',
    window_end: '2026-09-11T23:59:59Z',
    news_provider: 'yfinance-news',
    news_retrieved_at: '2026-09-14T10:10:01Z',
    news_coverage_start: null,
    news_coverage_end: null,
    news_quality: 'missing',
  },
  versions: baseVersions,
  error_code: null,
  error_message_safe: null,
};

export const failedMarketRun: ResearchRun = {
  run_id: 'd0eebc99-9c0b-4ef8-bb6d-6bb9bd380a44',
  symbol: 'AAPL',
  created_at: '2026-09-14T10:15:00Z',
  completed_at: '2026-09-14T10:15:01Z',
  as_of: null,
  workflow_status: 'failed',
  research_status: 'failed',
  summary: null,
  reasons: [],
  metrics: [],
  data_quality: null,
  sources: [],
  warnings: [],
  model_info: null,
  interpretation: null,
  snapshot: null,
  versions: baseVersions,
  error_code: 'MARKET_DATA_PROVIDER_FAILED',
  error_message_safe: 'Market data provider returned an error.',
};

// A run persisted before the v2 contract: the mapper returns null for both new
// fields and the stored schema version keeps its original value.
export const historicalRun: ResearchRun = {
  ...informationalRun,
  run_id: 'e0eebc99-9c0b-4ef8-bb6d-6bb9bd380a55',
  created_at: '2026-08-01T15:30:00Z',
  as_of: '2026-07-31T20:00:00Z',
  interpretation: null,
  snapshot: null,
  versions: { ...baseVersions, response_schema: 'research-run-response-v1' },
};

// A v3 run: relative returns, fundamentals, macro levels, filing counts, a price
// cross-check gap, quality for the four optional roles and a provider list.
const v3Versions = {
  response_schema: 'research-run-response-v3' as const,
  workflow: 'eod-research-v1' as const,
  metrics: 'eod-metrics-v3' as const,
  policy: 'research-policy-v2' as const,
  code: 'git-commit-hash-test',
};

const V3_AS_OF = '2026-09-11T20:00:00Z';
const FISCAL_YEAR_END = '2026-06-27T00:00:00Z';
const MACRO_AS_OF = '2026-09-10T00:00:00Z';

type V3Spec = [
  key: string,
  label: string,
  value: number,
  unit: ResearchMetric['unit'],
  window: number | null,
  asOf?: string,
];

const v3MetricSpecs: V3Spec[] = [
  ['return_1_session', '1-session return', 0.0061, 'ratio', 1],
  ['return_5_sessions', '5-session return', 0.0214, 'ratio', 5],
  ['return_20_sessions', '20-session return', 0.0452, 'ratio', 20],
  ['annualized_volatility_20', '20-session annualized volatility', 0.2215, 'ratio', 20],
  ['max_drawdown_20', '20-session maximum drawdown', -0.0381, 'ratio', 20],
  ['average_dollar_volume_20', '20-session average dollar volume', 12500000000, 'usd', 20],
  ['price_observation_count', 'Accepted price observations', 21, 'count', null],
  ['price_missing_value_count', 'Rejected missing price values', 0, 'count', null],
  ['price_duplicate_session_count', 'Duplicate price sessions', 0, 'count', null],
  ['news_item_count', 'Accepted news items', 7, 'count', null],
  ['news_publisher_count', 'Distinct news publishers', 4, 'count', null],
  ['excess_return_5_vs_spy', '5-session excess return vs SPY', 0.0052, 'ratio', 5],
  ['excess_return_20_vs_spy', '20-session excess return vs SPY', 0.0147, 'ratio', 20],
  ['excess_return_20_vs_sector', '20-session excess return vs XLK', -0.0033, 'ratio', 20],
  ['revenue_growth_fy_yoy', 'Fiscal-year revenue growth', 0.0612, 'ratio', null, FISCAL_YEAR_END],
  ['net_margin_fy', 'Fiscal-year net margin', 0.2431, 'ratio', null, FISCAL_YEAR_END],
  ['us10y_yield', 'US 10-year Treasury yield', 4.21, 'percent', null, MACRO_AS_OF],
  ['fed_funds_rate', 'Effective federal funds rate', 4.33, 'percent', null, MACRO_AS_OF],
  [
    'yield_curve_10y_2y',
    '10-year minus 2-year Treasury spread',
    0.52,
    'percent',
    null,
    MACRO_AS_OF,
  ],
  ['vix_close', 'VIX close (Cboe)', 16, 'index', null, MACRO_AS_OF],
  ['filing_count_30d', 'SEC filings in the last 30 days', 3, 'count', null],
  ['insider_filing_count_90d', 'Form 4 filings in the last 90 days', 5, 'count', null],
  [
    'price_crosscheck_max_deviation',
    'Largest adjusted-close gap vs the cross-check source',
    0.0008,
    'ratio',
    null,
  ],
];

const OPTIONAL_ROLE_KEYS = new Set([
  'revenue_growth_fy_yoy',
  'net_margin_fy',
  'us10y_yield',
  'fed_funds_rate',
  'yield_curve_10y_2y',
  'vix_close',
  'filing_count_30d',
  'insider_filing_count_90d',
  'price_crosscheck_max_deviation',
]);

function buildV3Metrics(optionalRolesConfigured: boolean): ResearchMetric[] {
  return v3MetricSpecs.map(([key, label, value, unit, window, asOf]) => {
    const absent = !optionalRolesConfigured && OPTIONAL_ROLE_KEYS.has(key);
    return {
      key,
      label,
      value: absent ? null : value,
      unit,
      window_sessions: window,
      as_of: asOf ?? V3_AS_OF,
      calculation_version: 'eod-metrics-v3',
      quality: absent ? ('missing' as const) : ('fresh' as const),
    };
  });
}

function providerRecord(
  role: ProviderRecord['role'],
  provider: string | null,
  quality: ProviderRecord['quality']
): ProviderRecord {
  return {
    role,
    provider,
    retrieved_at: provider ? '2026-09-14T10:00:01Z' : null,
    quality,
    error_code: null,
    content_hash: provider ? `${role}-hash` : null,
  };
}

export const informationalRunV3: ResearchRun = {
  ...informationalRun,
  run_id: 'a1eebc99-9c0b-4ef8-bb6d-6bb9bd380b11',
  summary:
    'Price, news, filings, fundamentals and macro inputs are available at sufficient quality.',
  reasons: [
    {
      code: 'EOD_COMPLETE',
      label: 'Sufficient Data & Signals',
      severity: 'info',
      description: 'All required inputs are available with fresh coverage.',
      metric_keys: ['return_20_sessions', 'excess_return_20_vs_spy'],
      evidence_ids: ['ev-101'],
      policy_version: 'research-policy-v2',
      threshold: null,
    },
  ],
  metrics: buildV3Metrics(true),
  data_quality: {
    overall: 'sufficient',
    prices: 'fresh',
    news: 'fresh',
    filings: 'fresh',
    fundamentals: 'fresh',
    macro: 'fresh',
    crosscheck: 'fresh',
    model: 'healthy',
  },
  sources: [
    {
      evidence_id: 'ev-101',
      provider: 'alpaca',
      publisher: 'Reuters',
      title: 'Apple Expands Services Revenue in Recent Quarter',
      url: 'https://example.com/news/apple-services',
      event_time: '2026-09-11T14:30:00Z',
      retrieved_at: '2026-09-14T10:00:01Z',
      content_hash: 'abc123hash',
      source_type: 'news',
      details: { providers: ['alpaca', 'finnhub'], company_specific: true },
    },
    {
      evidence_id: 'ev-102',
      provider: 'sec_edgar',
      publisher: 'SEC EDGAR',
      title: 'Form 8-K: Results of Operations and Financial Condition',
      url: 'https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/index.htm',
      event_time: '2026-09-09T20:05:00Z',
      retrieved_at: '2026-09-14T10:00:01Z',
      content_hash: 'filinghash',
      source_type: 'filing',
      details: { form_type: '8-K', item_codes: ['2.02', '9.01'], parse_state: 'parsed' },
    },
    {
      evidence_id: 'ev-103',
      provider: 'sec_edgar',
      publisher: 'SEC EDGAR',
      title: 'Form 4: statement of changes in beneficial ownership',
      url: 'https://www.sec.gov/Archives/edgar/data/320193/000032019326000002/index.htm',
      event_time: '2026-09-08T21:00:00Z',
      retrieved_at: '2026-09-14T10:00:01Z',
      content_hash: 'insiderhash',
      source_type: 'insider_transaction',
      details: { form_type: '4', transaction_code: 'S', direction: 'disposed' },
    },
  ],
  model_info: {
    provider: 'google',
    model: 'gemini-2.5-flash',
    prompt_version: 'research-interpretation-v3',
    failure_code: null,
  },
  interpretation: {
    ...informationalRun.interpretation!,
    evidence_ids: ['ev-101'],
    attribution: 'company',
  },
  snapshot: {
    ...informationalRun.snapshot!,
    market_provider: 'alpaca',
    news_provider: 'alpaca+finnhub',
    providers: [
      providerRecord('market', 'alpaca', 'fresh'),
      providerRecord('news', 'alpaca+finnhub', 'fresh'),
      providerRecord('filings', 'sec_edgar', 'fresh'),
      providerRecord('fundamentals', 'sec_edgar', 'fresh'),
      providerRecord('macro', 'fred', 'fresh'),
      providerRecord('crosscheck', 'tiingo', 'fresh'),
    ],
  },
  versions: v3Versions,
};

// The optional roles are not configured: their metrics are absent, never zero.
export const keylessRunV3: ResearchRun = {
  ...informationalRunV3,
  run_id: 'a2eebc99-9c0b-4ef8-bb6d-6bb9bd380b22',
  metrics: buildV3Metrics(false),
  data_quality: {
    overall: 'sufficient',
    prices: 'fresh',
    news: 'fresh',
    filings: 'not_configured',
    fundamentals: 'not_configured',
    macro: 'not_configured',
    crosscheck: 'not_configured',
    model: 'healthy',
  },
  sources: [informationalRunV3.sources[0]],
  snapshot: {
    ...informationalRunV3.snapshot!,
    providers: [
      providerRecord('market', 'alpaca', 'fresh'),
      providerRecord('news', 'alpaca+finnhub', 'fresh'),
      providerRecord('filings', null, 'not_configured'),
      providerRecord('fundamentals', null, 'not_configured'),
      providerRecord('macro', null, 'not_configured'),
      providerRecord('crosscheck', null, 'not_configured'),
    ],
  },
};
