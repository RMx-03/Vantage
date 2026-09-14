import type { Reason } from '../../types/research';

interface ReasonsPanelProps {
  reasons: Reason[];
  warnings: string[];
}

export default function ReasonsPanel({ reasons, warnings }: ReasonsPanelProps) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm">
      <h2 className="text-xl font-semibold text-slate-100 mb-4">Why this result?</h2>

      {warnings.length > 0 && (
        <div className="mb-4 space-y-2">
          {warnings.map((warning, index) => (
            <div
              key={index}
              className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200"
            >
              <span className="font-medium">Notice:</span>
              <span>{warning}</span>
            </div>
          ))}
        </div>
      )}

      {reasons.length === 0 ? (
        <p className="text-sm text-slate-400">No explicit policy reasons recorded for this run.</p>
      ) : (
        <div className="space-y-3">
          {reasons.map((reason, idx) => {
            const severityStyles =
              reason.severity === 'blocking'
                ? 'border-rose-500/30 bg-rose-950/20 text-rose-200'
                : reason.severity === 'warning'
                  ? 'border-amber-500/30 bg-amber-950/20 text-amber-200'
                  : 'border-slate-700/50 bg-slate-800/40 text-slate-200';

            const badgeStyles =
              reason.severity === 'blocking'
                ? 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                : reason.severity === 'warning'
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                  : 'bg-slate-700/40 text-slate-300 border-slate-600/40';

            return (
              <div
                key={`${reason.code}-${idx}`}
                className={`rounded-lg border p-4 transition-colors ${severityStyles}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium uppercase tracking-wider border ${badgeStyles}`}
                    >
                      {reason.severity}
                    </span>
                    <span className="font-medium text-slate-100">{reason.label}</span>
                  </div>
                  <span className="text-xs font-mono text-slate-400">{reason.code}</span>
                </div>
                <p className="text-sm text-slate-300 mt-1">{reason.description}</p>
                {reason.threshold !== null && reason.threshold !== undefined && (
                  <div className="mt-2 text-xs text-slate-400">
                    Threshold:{' '}
                    <span className="font-mono text-slate-300">{reason.threshold}</span>
                  </div>
                )}
                {reason.metric_keys.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1 text-xs text-slate-400">
                    <span>Evaluated metrics:</span>
                    {reason.metric_keys.map((k) => (
                      <span
                        key={k}
                        className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-slate-300 border border-slate-700/50"
                      >
                        {k}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
