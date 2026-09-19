import type { AIInterpretation } from '../../types/research';

interface InterpretationPanelProps {
  interpretation: AIInterpretation | null;
}

function getSentimentBadgeClass(label: AIInterpretation['sentiment_label']) {
  switch (label) {
    case 'positive':
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300';
    case 'negative':
      return 'border-rose-500/30 bg-rose-500/10 text-rose-300';
    case 'mixed':
      return 'border-amber-500/30 bg-amber-500/10 text-amber-300';
    case 'neutral':
    case 'unavailable':
    default:
      return 'border-slate-700 bg-slate-800 text-slate-400';
  }
}

export default function InterpretationPanel({ interpretation }: InterpretationPanelProps) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <h2 className="text-xl font-semibold text-slate-100">AI interpretation</h2>
        <span className="text-[11px] uppercase tracking-wider text-slate-500">
          Qualitative commentary
        </span>
      </div>

      {!interpretation ? (
        <p className="text-sm text-slate-400">
          Automated interpretation was not recorded for this run.
        </p>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={`inline-flex items-center rounded-md px-2.5 py-1 text-sm font-semibold capitalize border ${getSentimentBadgeClass(
                interpretation.sentiment_label
              )}`}
            >
              {interpretation.sentiment_label}
            </span>
            <span className="text-xs font-mono text-slate-400">
              Score:{' '}
              {interpretation.sentiment_score === null
                ? 'Unavailable'
                : interpretation.sentiment_score.toFixed(2)}
            </span>
            {interpretation.abstained && (
              <span className="text-xs font-mono text-amber-400">
                Abstained{
                  interpretation.abstention_reason
                    ? `: ${interpretation.abstention_reason}`
                    : ''
                }
              </span>
            )}
          </div>

          <p className="text-sm text-slate-300 leading-relaxed max-w-3xl">
            {interpretation.summary}
          </p>

          <div>
            <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
              Linked evidence
            </div>
            {interpretation.evidence_ids.length === 0 ? (
              <p className="text-xs text-slate-500">No evidence was cited.</p>
            ) : (
              <ul className="flex flex-wrap gap-2">
                {interpretation.evidence_ids.map((evidenceId) => (
                  <li
                    key={evidenceId}
                    className="rounded-md border border-slate-800 bg-slate-950/40 px-2 py-1 text-[11px] font-mono text-indigo-300"
                  >
                    {evidenceId}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {interpretation.warnings.length > 0 && (
            <div>
              <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
                Warnings
              </div>
              <ul className="space-y-1">
                {interpretation.warnings.map((warning) => (
                  <li key={warning} className="text-xs text-amber-300">
                    {warning}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <p className="mt-4 pt-3 border-t border-slate-800/60 text-xs text-slate-400">
        Research context only — not investment advice. Deterministic metrics and policy
        remain authoritative.
      </p>
    </section>
  );
}
