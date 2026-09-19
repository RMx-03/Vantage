import type { ResearchRun } from '../../types/research';
import { formatUtcDate } from './dateFormatters';
import { StatusChip } from '../../components/ui';
import ReasonsPanel from './ReasonsPanel';
import ResearchMetrics from './ResearchMetrics';
import DataQualityPanel from './DataQualityPanel';
import InterpretationPanel from './InterpretationPanel';
import SnapshotProvenancePanel from './SnapshotProvenancePanel';
import SourcesPanel from './SourcesPanel';
import RunDetails from './RunDetails';

interface ResearchResultProps {
  run: ResearchRun;
  historical?: boolean;
}

export default function ResearchResult({ run, historical = false }: ResearchResultProps) {
  const isWorkflowFailed = run.workflow_status === 'failed';

  return (
    <div className="space-y-6 w-full max-w-5xl mx-auto">
      {/* Historical Marker */}
      {historical && (
        <div className="flex items-center justify-between border border-primary/30 bg-primary/5 px-4 py-2 font-label text-[10px] uppercase tracking-widest text-primary">
          <span className="font-semibold uppercase tracking-wider">Historical run result</span>
          <span>
            Original as of:{' '}
            {run.as_of ? formatUtcDate(run.as_of) : 'Unavailable'}
          </span>
        </div>
      )}

      {/* Level 1: Symbol, Research Status & Summary */}
      <header className="border border-outline-variant bg-surface-container-low p-6">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-3">
          <div className="flex items-baseline gap-3">
            <h1 className="text-4xl font-label font-bold tracking-tight text-on-surface">
              {run.symbol}
            </h1>
            <span className="text-xs font-label text-outline">
              EOD Research Analysis
            </span>
          </div>

          <div className="flex items-center gap-2">
            <StatusChip status={run.research_status} />
          </div>
        </div>

        {isWorkflowFailed ? (
          <div className="mt-4 border border-error-container bg-error-container/30 p-4 text-error">
            <div className="font-semibold text-error mb-1">
              Research run execution failed
            </div>
            <p className="text-sm">
              {run.error_message_safe || 'An unexpected error occurred during execution.'}
            </p>
            {run.error_code && (
              <div className="mt-2 text-xs font-label text-error">
                Code: {run.error_code}
              </div>
            )}
            <div className="mt-1 text-xs font-label text-outline">
              Run ID: <span className="text-on-surface-variant">{run.run_id}</span>
            </div>
          </div>
        ) : (
          <p className="text-base text-on-surface-variant leading-relaxed max-w-3xl">
            {run.summary || 'Summary unavailable for this run.'}
          </p>
        )}

        <div className="mt-4 pt-3 border-t border-outline-variant/30 flex flex-wrap items-center justify-between gap-2 text-xs text-outline">
          <span>
            Market As-Of:{' '}
            <strong className="text-on-surface-variant font-label">
              {run.as_of ? formatUtcDate(run.as_of) : 'Unavailable'}
            </strong>
          </span>
          <span>
            Workflow status:{' '}
            <strong className="capitalize text-on-surface-variant font-label">
              {run.workflow_status}
            </strong>
          </span>
        </div>
      </header>

      {/* Level 2: Reasons Panel */}
      <ReasonsPanel reasons={run.reasons} warnings={run.warnings} />

      {/* Level 3: Metrics */}
      <ResearchMetrics metrics={run.metrics} version={run.versions.metrics} />

      {/* Level 4: AI Interpretation (qualitative commentary only) */}
      <InterpretationPanel interpretation={run.interpretation} />

      {/* Level 5: Data Quality */}
      <DataQualityPanel dataQuality={run.data_quality} modelInfo={run.model_info} />

      {/* Level 6: Evidence Sources */}
      <SourcesPanel sources={run.sources} />

      {/* Level 7: Snapshot Provenance */}
      <SnapshotProvenancePanel snapshot={run.snapshot} />

      {/* Level 8: Run Details */}
      <RunDetails run={run} />
    </div>
  );
}
