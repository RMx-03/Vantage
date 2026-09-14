import type { ResearchMetric } from '../../types/research';

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
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold text-slate-100">Metrics</h2>
        <span className="text-xs font-mono text-slate-500">{version}</span>
      </div>

      {metrics.length === 0 ? (
        <p className="text-sm text-slate-400">No quantitative metrics computed for this run.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {metrics.map((metric) => {
            const formatted = formatMetricValue(metric.value, metric.unit);
            const isUnavailable = formatted === 'Unavailable';

            return (
              <div
                key={metric.key}
                className="flex flex-col justify-between rounded-lg border border-slate-800 bg-slate-950/40 p-4 transition-all hover:border-slate-700"
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="text-xs font-medium text-slate-400 truncate" title={metric.label}>
                      {metric.label}
                    </span>
                    <span
                      className={`text-[10px] uppercase font-mono px-1.5 py-0.5 rounded border ${
                        metric.quality === 'fresh'
                          ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                          : metric.quality === 'stale'
                            ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                            : 'border-slate-700 bg-slate-800 text-slate-400'
                      }`}
                    >
                      {metric.quality}
                    </span>
                  </div>
                  <div
                    className={`text-2xl font-bold font-mono tracking-tight mt-1 ${
                      isUnavailable ? 'text-slate-500 text-lg font-sans' : 'text-slate-100'
                    }`}
                  >
                    {formatted}
                  </div>
                </div>

                <div className="mt-3 pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px] text-slate-400">
                  <span>
                    {metric.window_sessions ? `${metric.window_sessions} sessions` : 'Full snapshot'}
                  </span>
                  <span className="font-mono text-[10px]">{metric.key}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {hasVolatility && (
        <p className="mt-4 text-xs text-slate-400 italic">
          * Volatility: 20-session annualized single-security variability; not portfolio risk.
        </p>
      )}
    </section>
  );
}
