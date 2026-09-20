import type { Reason } from '../../types/research';
import { Panel, PanelHeader } from '../../components/ui';

interface ReasonsPanelProps {
  reasons: Reason[];
  warnings: string[];
}

export default function ReasonsPanel({ reasons, warnings }: ReasonsPanelProps) {
  return (
    <Panel>
      <div className="mb-4">
        <PanelHeader icon="help">Why this result?</PanelHeader>
      </div>

      {warnings.length > 0 && (
        <div className="mb-4 space-y-2">
          {warnings.map((warning, index) => (
            <div
              key={index}
              className="flex items-start gap-2 border border-outline bg-surface-container-highest p-3 text-sm text-on-surface"
            >
              <span className="font-medium font-label uppercase tracking-widest text-[10px]">
                Notice:
              </span>
              <span>{warning}</span>
            </div>
          ))}
        </div>
      )}

      {reasons.length === 0 ? (
        <p className="text-sm text-outline">No explicit policy reasons recorded for this run.</p>
      ) : (
        <div className="space-y-3">
          {reasons.map((reason, idx) => {
            const severityStyles =
              reason.severity === 'blocking'
                ? 'border-error-container bg-error-container/20 text-error'
                : reason.severity === 'warning'
                  ? 'border-outline bg-surface-container-highest text-on-surface'
                  : 'border-outline-variant/30 bg-surface-container-low text-on-surface-variant';

            const badgeStyles =
              reason.severity === 'blocking'
                ? 'border-error-container bg-error-container/30 text-error'
                : reason.severity === 'warning'
                  ? 'border-outline bg-surface-container text-on-surface font-bold font-label uppercase tracking-widest'
                  : 'border-outline-variant bg-surface-container text-on-surface-variant font-label uppercase tracking-widest';

            return (
              <div
                key={`${reason.code}-${idx}`}
                className={`border p-4 transition-colors ${severityStyles}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 text-xs font-medium uppercase tracking-wider border ${badgeStyles}`}
                    >
                      {reason.severity}
                    </span>
                    <span className="font-medium text-on-surface">{reason.label}</span>
                  </div>
                  <span className="text-xs font-label text-outline">{reason.code}</span>
                </div>
                <p className="text-sm text-on-surface-variant mt-1">{reason.description}</p>
                {reason.threshold !== null && reason.threshold !== undefined && (
                  <div className="mt-2 text-xs text-outline font-label">
                    Threshold:{' '}
                    <span className="text-on-surface-variant">{reason.threshold}</span>
                  </div>
                )}
                {reason.metric_keys.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1 text-xs text-outline font-label">
                    <span>Evaluated metrics:</span>
                    {reason.metric_keys.map((k) => (
                      <span
                        key={k}
                        className="bg-surface-container px-1.5 py-0.5 font-label text-on-surface-variant border border-outline-variant/30"
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
    </Panel>
  );
}
