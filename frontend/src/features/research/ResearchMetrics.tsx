import type { ResearchMetric } from '../../types/research';
import { Panel, PanelHeader } from '../../components/ui';

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
    default:
      return String(value);
  }
}

export default function ResearchMetrics({ metrics, version }: ResearchMetricsProps) {
  const hasVolatility = metrics.some((m) => m.key.includes('volatility'));

  return (
    <Panel>
      <div className="flex items-center justify-between mb-4">
        <PanelHeader icon="analytics">Metrics</PanelHeader>
        <span className="text-xs font-label text-outline">{version}</span>
      </div>

      {metrics.length === 0 ? (
        <p className="text-sm text-outline">No quantitative metrics computed for this run.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {metrics.map((metric) => {
            const formatted = formatMetricValue(metric.value, metric.unit);
            const isUnavailable = formatted === 'Unavailable';

            return (
              <div
                key={metric.key}
                className="flex flex-col justify-between border border-outline-variant/30 bg-surface-container-low p-4 transition-colors hover:border-outline-variant"
              >
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
                </div>

                <div className="mt-3 pt-2 border-t border-outline-variant/30 flex items-center justify-between text-[11px] text-outline font-label">
                  <span>
                    {metric.window_sessions ? `${metric.window_sessions} sessions` : 'Full snapshot'}
                  </span>
                  <span className="text-[10px]">{metric.key}</span>
                </div>
              </div>
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
