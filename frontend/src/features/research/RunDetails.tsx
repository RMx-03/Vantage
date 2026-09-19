import type { ResearchRun } from '../../types/research';
import { Panel, CopyButton } from '../../components/ui';

interface RunDetailsProps {
  run: ResearchRun;
}

export default function RunDetails({ run }: RunDetailsProps) {
  return (
    <Panel className="p-4">
      <details className="group cursor-pointer">
        <summary className="flex items-center justify-between font-headline text-xs uppercase tracking-widest text-primary hover:text-on-surface transition-colors list-none cursor-pointer">
          <div className="flex items-center gap-2">
            <span className="text-sm font-label text-outline group-open:rotate-90 transition-transform">
              ▶
            </span>
            <h2 className="inline">Run details</h2>
          </div>
          <span className="text-xs font-label text-outline">{run.run_id}</span>
        </summary>

        <div className="mt-4 pt-4 border-t border-outline-variant/30 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-label text-on-surface-variant">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-outline">Run ID: </span>
              <span className="select-all text-primary">{run.run_id}</span>
              <CopyButton value={run.run_id} label="Copy run ID" />
            </div>
            <div>
              <span className="text-outline">Symbol: </span>
              <span>{run.symbol}</span>
            </div>
            <div>
              <span className="text-outline">Workflow Status: </span>
              <span className="capitalize">{run.workflow_status}</span>
            </div>
            <div>
              <span className="text-outline">Research Status: </span>
              <span className="capitalize">{run.research_status ?? 'None'}</span>
            </div>
            <div>
              <span className="text-outline">Created At: </span>
              <span>{new Date(run.created_at).toISOString()}</span>
            </div>
            <div>
              <span className="text-outline">Completed At: </span>
              <span>
                {run.completed_at ? new Date(run.completed_at).toISOString() : 'Pending'}
              </span>
            </div>
            <div>
              <span className="text-outline">As Of (Market Close): </span>
              <span>
                {run.as_of ? new Date(run.as_of).toISOString() : 'Unavailable'}
              </span>
            </div>
          </div>

          <div className="space-y-2">
            <div>
              <span className="text-outline">Workflow Version: </span>
              <span>{run.versions.workflow}</span>
            </div>
            <div>
              <span className="text-outline">Schema Version: </span>
              <span>{run.versions.response_schema}</span>
            </div>
            <div>
              <span className="text-outline">Metrics Version: </span>
              <span>{run.versions.metrics}</span>
            </div>
            <div>
              <span className="text-outline">Policy Version: </span>
              <span>{run.versions.policy}</span>
            </div>
            <div>
              <span className="text-outline">Code Revision: </span>
              <span>{run.versions.code}</span>
            </div>
            {run.model_info && (
              <div>
                <span className="text-outline">Model Engine: </span>
                <span>
                  {run.model_info.provider} / {run.model_info.model} (
                  {run.model_info.prompt_version})
                </span>
              </div>
            )}
          </div>
        </div>
      </details>
    </Panel>
  );
}
