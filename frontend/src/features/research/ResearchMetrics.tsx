import type { ResearchMetric } from '../../types/research';
import { Panel, PanelHeader } from '../../components/ui';
import { formatUtcDate } from './dateFormatters';
import { METRIC_GROUP_ORDER, metricGroupOf } from './metricGroups';

const FRED_NOTICE =
  'This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.';
const CBOE_NOTICE = 'VIX close: © Cboe, via FRED.';

interface ResearchMetricsProps {
  metrics: ResearchMetric[];
  version: string;
}

function formatMetricValue(value: number | null, unit: ResearchMetric['unit']): string {
  if (value === null || value === undefined || isNaN(value)) {
    return 'Unavailable';
  }

  switch (unit) {
    case 'ratio':
      return new Intl.NumberFormat('en-US', {
        style: 'percent',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(value);
    case 'percent':
      return (
        new Intl.NumberFormat('en-US', {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        }).format(value) + '%'
      );
    case 'usd':
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        notation: value >= 1_000_000 ? 'compact' : 'standard',
        maximumFractionDigits: 2,
      }).format(value);
    case 'count':
    case 'sessions':
      return new Intl.NumberFormat('en-US', {
        maximumFractionDigits: 0,
      }).format(value);
    case 'index':
      return new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(value);
    default:
      return String(value);
  }
}

function MetricTile({ metric }: { metric: ResearchMetric }) {
  const formatted = formatMetricValue(metric.value, metric.unit);
  const isUnavailable = formatted === 'Unavailable';
  const showAsOf = metricGroupOf(metric.key) === 'macro' && !isUnavailable;

  return (
    <div className="flex flex-col justify-between border border-outline-variant/30 bg-surface-container-low p-4 transition-colors hover:border-outline-variant">
      <div>
        <div className="flex items-center justify-between gap-2 mb-1">
          <span
            className="text-xs font-medium text-outline truncate font-label"
            title={metric.label}
          >
            {metric.label}
          </span>
          <span
            className={`text-[10px] uppercase font-label px-1.5 py-0.5 border ${
              metric.quality === 'fresh'
                ? 'border-outline-variant bg-surface-container-highest text-on-surface'
                : metric.quality === 'stale'
                  ? 'border-outline bg-surface-container-highest text-on-surface-variant font-bold'
                  : 'border-outline-variant/30 bg-surface-container text-outline'
            }`}
          >
            {metric.quality}
          </span>
        </div>
        <div
          className={`text-2xl font-bold font-label tracking-tight mt-1 ${
            isUnavailable ? 'text-outline text-lg font-body' : 'text-on-surface'
          }`}
        >
          {formatted}
        </div>
        {showAsOf && (
          <div className="mt-1 text-[11px] text-outline font-label">
            As of {formatUtcDate(metric.as_of)}
          </div>
        )}
      </div>

      <div className="mt-3 pt-2 border-t border-outline-variant/30 flex items-center justify-between text-[11px] text-outline font-label">
        <span>
          {metric.window_sessions ? `${metric.window_sessions} sessions` : 'Full snapshot'}
        </span>
        <span className="text-[10px]">{metric.key}</span>
      </div>
    </div>
  );
}

export default function ResearchMetrics({ metrics, version }: ResearchMetricsProps) {
  const hasVolatility = metrics.some((m) => m.key.includes('volatility'));

  const groups = METRIC_GROUP_ORDER.map(({ group, heading }) => ({
    group,
    heading,
    items: metrics.filter((m) => metricGroupOf(m.key) === group),
  })).filter((g) => g.items.length > 0);

  return (
    <Panel>
      <div className="flex items-center justify-between mb-4">
        <PanelHeader icon="analytics">Metrics</PanelHeader>
        <span className="text-xs font-label text-outline">{version}</span>
      </div>

      {metrics.length === 0 ? (
        <p className="text-sm text-outline">No quantitative metrics computed for this run.</p>
      ) : (
        <div className="space-y-6">
          {groups.map(({ group, heading, items }) => {
            const valued = items.filter((m) => m.value !== null && m.value !== undefined);
            const fiscalYearEnd =
              group === 'fundamentals' && valued.length > 0 ? valued[0].as_of : null;

            return (
              <section key={group}>
                <h3 className="mb-2 text-xs font-medium text-outline uppercase tracking-wider font-label">
                  {heading}
                </h3>
                {fiscalYearEnd && (
                  <p className="mb-2 text-[11px] text-outline font-label">
                    Fiscal year ending {formatUtcDate(fiscalYearEnd)}
                  </p>
                )}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  {items.map((metric) => (
                    <MetricTile key={metric.key} metric={metric} />
                  ))}
                </div>
                {group === 'macro' && valued.length > 0 && (
                  <div className="mt-2 space-y-1 text-[11px] text-outline font-body">
                    <p>{FRED_NOTICE}</p>
                    <p>{CBOE_NOTICE}</p>
                  </div>
                )}
              </section>
            );
          })}
        </div>
      )}

      {hasVolatility && (
        <p className="mt-4 text-xs text-outline italic font-body">
          * Volatility: 20-session annualized single-security variability; not portfolio risk.
        </p>
      )}
    </Panel>
  );
}
