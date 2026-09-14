import type { EvidenceSource } from '../../types/research';

interface SourcesPanelProps {
  sources: EvidenceSource[];
}

export default function SourcesPanel({ sources }: SourcesPanelProps) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm">
      <h2 className="text-xl font-semibold text-slate-100 mb-4">Sources</h2>

      {sources.length === 0 ? (
        <p className="text-sm text-slate-400">No external evidence sources attached to this run.</p>
      ) : (
        <div className="space-y-3">
          {sources.map((source) => (
            <div
              key={source.evidence_id}
              className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 transition-all hover:border-slate-700"
            >
              <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 mb-1">
                <div className="font-medium text-slate-200">
                  {source.url ? (
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-indigo-400 hover:text-indigo-300 hover:underline inline-flex items-center gap-1"
                    >
                      {source.title}
                      <span className="text-xs">↗</span>
                    </a>
                  ) : (
                    <span>{source.title}</span>
                  )}
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 shrink-0">
                  {source.publisher && <span>{source.publisher}</span>}
                  <span>•</span>
                  <span>{source.provider}</span>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3 mt-2 text-[11px] text-slate-500 font-mono">
                <span>ID: {source.evidence_id}</span>
                {source.event_time && (
                  <span>
                    Published: {new Date(source.event_time).toLocaleString()}
                  </span>
                )}
                <span>
                  Retrieved: {new Date(source.retrieved_at).toLocaleString()}
                </span>
                {source.content_hash && (
                  <span title={source.content_hash}>
                    Hash: {source.content_hash.slice(0, 10)}...
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
