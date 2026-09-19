import type { EvidenceSource } from '../../types/research';
import { Panel, PanelHeader } from '../../components/ui';

/**
 * Only absolute web URLs may become an href. The provider now drops every other
 * scheme at ingestion, but rows persisted before that guard existed are replayed
 * here, so the renderer refuses a hostile stored value instead of trusting it.
 */
const ALLOWED_URL_SCHEMES = ['http:', 'https:'];

function safeHref(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    return ALLOWED_URL_SCHEMES.includes(new URL(url).protocol) ? url : null;
  } catch {
    return null;
  }
}

function SourceTitle({ source }: { source: EvidenceSource }) {
  const href = safeHref(source.url);
  return href ? (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-primary hover:text-primary-dim hover:underline inline-flex items-center gap-1"
    >
      {source.title}
      <span className="text-xs">↗</span>
    </a>
  ) : (
    <span>{source.title}</span>
  );
}

interface SourcesPanelProps {
  sources: EvidenceSource[];
}

export default function SourcesPanel({ sources }: SourcesPanelProps) {
  return (
    <Panel>
      <div className="mb-4">
        <PanelHeader icon="link">Sources</PanelHeader>
      </div>

      {sources.length === 0 ? (
        <p className="text-sm text-outline">No external evidence sources attached to this run.</p>
      ) : (
        <div className="space-y-3">
          {sources.map((source) => (
            <div
              key={source.evidence_id}
              className="border border-outline-variant/30 bg-surface-container-low p-4 transition-all hover:border-outline-variant"
            >
              <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 mb-1">
                <div className="font-medium text-on-surface-variant">
                  <SourceTitle source={source} />
                </div>
                <div className="flex items-center gap-2 text-xs text-outline shrink-0">
                  {source.publisher && <span>{source.publisher}</span>}
                  <span>•</span>
                  <span>{source.provider}</span>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3 mt-2 text-[11px] text-outline font-label">
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
    </Panel>
  );
}
