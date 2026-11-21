export type MetricGroup = 'price' | 'relative' | 'fundamentals' | 'macro' | 'evidence' | 'other';

export const METRIC_GROUP_ORDER: { group: MetricGroup; heading: string }[] = [
  { group: 'price', heading: 'Price' },
  { group: 'relative', heading: 'Relative' },
  { group: 'fundamentals', heading: 'Fundamentals' },
  { group: 'macro', heading: 'Macro' },
  { group: 'evidence', heading: 'Evidence and checks' },
  { group: 'other', heading: 'Other' },
];

/** The group of every metric key the backend emits (eod-metrics-v3). */
export const METRIC_KEY_GROUPS: Record<string, MetricGroup> = {
  return_1_session: 'price',
  return_5_sessions: 'price',
  return_20_sessions: 'price',
  annualized_volatility_20: 'price',
  max_drawdown_20: 'price',
  average_dollar_volume_20: 'price',
  price_observation_count: 'price',
  price_missing_value_count: 'price',
  price_duplicate_session_count: 'price',
  excess_return_5_vs_spy: 'relative',
  excess_return_20_vs_spy: 'relative',
  excess_return_20_vs_sector: 'relative',
  revenue_growth_fy_yoy: 'fundamentals',
  net_margin_fy: 'fundamentals',
  us10y_yield: 'macro',
  fed_funds_rate: 'macro',
  yield_curve_10y_2y: 'macro',
  vix_close: 'macro',
  news_item_count: 'evidence',
  news_publisher_count: 'evidence',
  filing_count_30d: 'evidence',
  insider_filing_count_90d: 'evidence',
  price_crosscheck_max_deviation: 'evidence',
};

export function metricGroupOf(key: string): MetricGroup {
  if (key in METRIC_KEY_GROUPS) return METRIC_KEY_GROUPS[key];
  return key.startsWith('excess_return_') ? 'relative' : 'other';
}
