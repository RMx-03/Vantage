import type { DataQuality, ModelInfo } from '../../types/research';

interface DataQualityPanelProps {
  dataQuality: DataQuality | null;
  modelInfo: ModelInfo | null;
}

function getQualityBadgeClass(status: string) {
  switch (status) {
    case 'sufficient':
    case 'fresh':
    case 'healthy':
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300';
    case 'degraded':
    case 'partial':
    case 'stale':
      return 'border-amber-500/30 bg-amber-500/10 text-amber-300';
    case 'insufficient':
    case 'missing':
    case 'failed':
      return 'border-rose-500/30 bg-rose-500/10 text-rose-300';
    case 'not_run':
    default:
      return 'border-slate-700 bg-slate-800 text-slate-400';
  }
}

export default function DataQualityPanel({ dataQuality, modelInfo }: DataQualityPanelProps) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm">
      <h2 className="text-xl font-semibold text-slate-100 mb-4">Data quality</h2>

      {!dataQuality ? (
        <p className="text-sm text-slate-400">Data quality metrics unavailable for this run.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
            <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
              Overall Quality
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center rounded-md px-2.5 py-1 text-sm font-semibold capitalize border ${getQualityBadgeClass(
                  dataQuality.overall
                )}`}
              >
                {dataQuality.overall}
              </span>
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
            <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
              Prices Component
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center rounded-md px-2.5 py-1 text-sm font-semibold capitalize border ${getQualityBadgeClass(
                  dataQuality.prices
                )}`}
              >
                {dataQuality.prices}
              </span>
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
            <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
              News Component
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center rounded-md px-2.5 py-1 text-sm font-semibold capitalize border ${getQualityBadgeClass(
                  dataQuality.news
                )}`}
              >
                {dataQuality.news}
              </span>
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
            <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
              Model Quality
            </div>
            <div className="flex flex-col gap-1">
              <span
                className={`inline-flex items-center rounded-md px-2.5 py-1 text-sm font-semibold capitalize border w-fit ${getQualityBadgeClass(
                  dataQuality.model
                )}`}
              >
                {dataQuality.model.replace('_', ' ')}
              </span>
              {modelInfo?.failure_code && (
                <span className="text-[11px] font-mono text-rose-400 mt-1">
                  Code: {modelInfo.failure_code}
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
