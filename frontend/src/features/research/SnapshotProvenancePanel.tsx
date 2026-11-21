import type { SnapshotProvenance } from '../../types/research';
import { Panel, PanelHeader } from '../../components/ui';

interface SnapshotProvenancePanelProps {
  snapshot: SnapshotProvenance | null;
}

function formatInstant(value: string | null) {
  if (!value) return 'Unavailable';
  const parsed = new Date(value);
  // Never let one unparsable timestamp throw and blank the whole result page.
  return Number.isNaN(parsed.getTime()) ? 'Unavailable' : parsed.toISOString();
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] font-medium text-outline uppercase tracking-wider">{label}</dt>
      <dd className="mt-1 break-all font-label text-xs text-on-surface-variant">{value}</dd>
    </div>
  );
}

export default function SnapshotProvenancePanel({ snapshot }: SnapshotProvenancePanelProps) {
  return (
    <Panel>
      <div className="mb-4">
        <PanelHeader icon="snapshot">Snapshot provenance</PanelHeader>
      </div>

      {!snapshot ? (
        <p className="text-sm text-outline">Snapshot provenance was not recorded for this run.</p>
      ) : (
        <>
          <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div className="sm:col-span-2 lg:col-span-3">
              <Field label="Snapshot content hash" value={snapshot.content_hash} />
            </div>
            <Field label="Snapshot ID" value={snapshot.snapshot_id} />
            <Field label="Market provider" value={snapshot.market_provider} />
            <Field label="Market content hash" value={snapshot.market_content_hash} />
            <Field label="Market as-of" value={formatInstant(snapshot.market_as_of)} />
            <Field
              label="Market retrieved at"
              value={formatInstant(snapshot.market_retrieved_at)}
            />
            <Field
              label="Price session window"
              value={`${formatInstant(snapshot.window_start)} → ${formatInstant(
                snapshot.window_end
              )}`}
            />
            <Field label="News provider" value={snapshot.news_provider} />
            <Field label="News retrieved at" value={formatInstant(snapshot.news_retrieved_at)} />
            <Field
              label="News coverage window"
              value={`${formatInstant(snapshot.news_coverage_start)} → ${formatInstant(
                snapshot.news_coverage_end
              )}`}
            />
            <Field label="News quality" value={snapshot.news_quality} />
          </dl>
          {snapshot.providers && snapshot.providers.length > 0 && (
            <div className="mt-6">
              <h3 className="text-[11px] font-medium text-outline uppercase tracking-wider">
                Providers by role
              </h3>
              <ul
                aria-label="Providers by role"
                className="mt-2 divide-y divide-outline-variant/30 border border-outline-variant/30"
              >
                {snapshot.providers.map((record) => (
                  <li
                    key={record.role}
                    className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 font-label text-xs text-on-surface-variant"
                  >
                    <span className="w-28 capitalize text-outline">{record.role}</span>
                    <span className="text-on-surface">{record.provider ?? 'none'}</span>
                    <span>{record.quality.replace('_', ' ')}</span>
                    {record.error_code && <span className="text-error">{record.error_code}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
