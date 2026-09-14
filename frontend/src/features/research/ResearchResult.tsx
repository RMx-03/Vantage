import type { ResearchRun } from '../../types/research';
import ReasonsPanel from './ReasonsPanel';
import ResearchMetrics from './ResearchMetrics';
import DataQualityPanel from './DataQualityPanel';
import SourcesPanel from './SourcesPanel';
import RunDetails from './RunDetails';

interface ResearchResultProps {
  run: ResearchRun;
  historical?: boolean;
}

function getResearchStatusBadge(status: ResearchRun['research_status']) {
  switch (status) {
    case 'informational':
      return {
        label: 'informational',
        containerClass: 'border-slate-600 bg-slate-800/80 text-slate-200',
      };
    case 'review':
      return {
        label: 'review',
        containerClass: 'border-amber-500/40 bg-amber-500/20 text-amber-200',
      };
    case 'insufficient_data':
      return {
        label: 'insufficient data',
        containerClass: 'border-rose-500/40 bg-rose-500/20 text-rose-200',
      };
    case 'failed':
      return {
        label: 'failed',
        containerClass: 'border-rose-600/50 bg-rose-950/40 text-rose-300',
      };
    default:
      return {
        label: 'unknown',
        containerClass: 'border-slate-700 bg-slate-800 text-slate-400',
      };
  }
}

export default function ResearchResult({ run, historical = false }: ResearchResultProps) {
  const statusBadge = getResearchStatusBadge(run.research_status);
  const isWorkflowFailed = run.workflow_status === 'failed';

  return (
    <div className="space-y-6 w-full max-w-5xl mx-auto">
      {/* Historical Marker */}
      {historical && (
        <div className="flex items-center justify-between rounded-lg border border-indigo-500/30 bg-indigo-950/30 px-4 py-2 text-xs text-indigo-300">
          <span className="font-semibold uppercase tracking-wider">Historical run result</span>
          <span>
            Original as of:{' '}
            {run.as_of
              ? new Date(run.as_of).toLocaleDateString('en-US', {
                  timeZone: 'UTC',
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })
              : 'Unavailable'}
          </span>
        </div>
      )}

      {/* Level 1: Symbol, Research Status & Summary */}
      <header className="rounded-xl border border-slate-800 bg-slate-900/80 p-6 backdrop-blur-sm">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-3">
          <div className="flex items-baseline gap-3">
            <h1 className="text-3xl font-extrabold tracking-tight text-white font-mono">
              {run.symbol}
            </h1>
            <span className="text-xs font-mono text-slate-400">
              EOD Research Analysis
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium uppercase tracking-wider border ${statusBadge.containerClass}`}
            >
              {statusBadge.label}
            </span>
          </div>
        </div>

        {isWorkflowFailed ? (
          <div className="mt-4 rounded-lg border border-rose-500/40 bg-rose-950/30 p-4 text-rose-200">
            <div className="font-semibold text-rose-100 mb-1">
              Research run execution failed
            </div>
            <p className="text-sm">
              {run.error_message_safe || 'An unexpected error occurred during execution.'}
            </p>
            {run.error_code && (
              <div className="mt-2 text-xs font-mono text-rose-300">
                Code: {run.error_code}
              </div>
            )}
            <div className="mt-1 text-xs font-mono text-slate-400">
              Run ID: <span className="text-slate-200">{run.run_id}</span>
            </div>
          </div>
        ) : (
          <p className="text-base text-slate-300 leading-relaxed max-w-3xl">
            {run.summary || 'Summary unavailable for this run.'}
          </p>
        )}

        <div className="mt-4 pt-3 border-t border-slate-800/60 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
          <span>
            Market As-Of:{' '}
            <strong className="text-slate-200 font-mono">
              {run.as_of ? new Date(run.as_of).toLocaleDateString() : 'Unavailable'}
            </strong>
          </span>
          <span>
            Workflow status:{' '}
            <strong className="capitalize text-slate-200 font-mono">
              {run.workflow_status}
            </strong>
          </span>
        </div>
      </header>

      {/* Level 2: Reasons Panel */}
      <ReasonsPanel reasons={run.reasons} warnings={run.warnings} />

      {/* Level 3: Metrics */}
      <ResearchMetrics metrics={run.metrics} />

      {/* Level 4: Data Quality */}
      <DataQualityPanel dataQuality={run.data_quality} modelInfo={run.model_info} />

      {/* Level 5: Evidence Sources */}
      <SourcesPanel sources={run.sources} />

      {/* Level 6: Run Details */}
      <RunDetails run={run} />
    </div>
  );
}
