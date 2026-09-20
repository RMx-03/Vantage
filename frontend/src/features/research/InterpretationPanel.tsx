import type { AIInterpretation } from '../../types/research';
import { Panel, PanelHeader } from '../../components/ui';

interface InterpretationPanelProps {
  interpretation: AIInterpretation | null;
}

export default function InterpretationPanel({ interpretation }: InterpretationPanelProps) {
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <PanelHeader icon="smart_toy">AI interpretation</PanelHeader>
        <span className="text-[11px] uppercase tracking-wider text-outline font-label">
          Qualitative commentary
        </span>
      </div>

      {!interpretation ? (
        <p className="text-sm text-outline">
          Automated interpretation was not recorded for this run.
        </p>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex items-center border border-outline-variant bg-surface-container-highest text-on-surface-variant font-label text-[10px] uppercase tracking-widest px-2.5 py-1">
              {interpretation.sentiment_label}
            </span>
            <span className="text-xs font-label text-outline">
              Score:{' '}
              {interpretation.sentiment_score === null
                ? 'Unavailable'
                : interpretation.sentiment_score.toFixed(2)}
            </span>
            {interpretation.abstained && (
              <span className="text-xs font-label text-on-surface font-bold">
                Abstained{
                  interpretation.abstention_reason
                    ? `: ${interpretation.abstention_reason}`
                    : ''
                }
              </span>
            )}
          </div>

          <p className="text-sm text-on-surface-variant leading-relaxed max-w-3xl">
            {interpretation.summary}
          </p>

          <div>
            <div className="text-xs font-medium text-outline uppercase tracking-wider mb-2 font-label">
              Linked evidence
            </div>
            {interpretation.evidence_ids.length === 0 ? (
              <p className="text-xs text-outline">No evidence was cited.</p>
            ) : (
              <ul className="flex flex-wrap gap-2">
                {interpretation.evidence_ids.map((evidenceId) => (
                  <li
                    key={evidenceId}
                    className="border border-outline-variant/30 bg-surface-container-low px-2 py-1 text-[11px] font-label text-primary"
                  >
                    {evidenceId}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {interpretation.warnings.length > 0 && (
            <div>
              <div className="text-xs font-medium text-outline uppercase tracking-wider mb-2 font-label">
                Warnings
              </div>
              <ul className="space-y-1">
                {interpretation.warnings.map((warning) => (
                  <li key={warning} className="text-xs text-on-surface-variant font-label">
                    {warning}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <p className="mt-4 pt-3 border-t border-outline-variant/30 text-xs text-outline">
        Research context only — not investment advice. Deterministic metrics and policy
        remain authoritative.
      </p>
    </Panel>
  );
}
