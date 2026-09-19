import type { SnapshotProvenance } from '../../types/research';

interface SnapshotProvenancePanelProps {
  snapshot: SnapshotProvenance | null;
}

function formatInstant(value: string | null) {
  return value ? new Date(value).toISOString() : 'Unavailable';
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">
        {label}
      </dt>
      <dd className="mt-1 break-all font-mono text-xs text-slate-200">{value}</dd>
    </div>
  );
}

export default function SnapshotProvenancePanel({
  snapshot,
}: SnapshotProvenancePanelProps) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm">
      <h2 className="text-xl font-semibold text-slate-100 mb-4">Snapshot provenance</h2>

      {!snapshot ? (
        <p className="text-sm text-slate-400">
          Snapshot provenance was not recorded for this run.
        </p>
      ) : (
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
          <Field
            label="News retrieved at"
            value={formatInstant(snapshot.news_retrieved_at)}
          />
          <Field
            label="News coverage window"
            value={`${formatInstant(snapshot.news_coverage_start)} → ${formatInstant(
              snapshot.news_coverage_end
            )}`}
          />
          <Field label="News quality" value={snapshot.news_quality} />
        </dl>
      )}
    </section>
  );
}
