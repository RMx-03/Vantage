import type { ResearchRun } from '../../types/research';

interface RunDetailsProps {
  run: ResearchRun;
}

export default function RunDetails({ run }: RunDetailsProps) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
      <details className="group cursor-pointer">
        <summary className="flex items-center justify-between font-semibold text-slate-300 hover:text-slate-100 transition-colors list-none">
          <div className="flex items-center gap-2">
            <span className="text-sm font-mono text-slate-400 group-open:rotate-90 transition-transform">
              ▶
            </span>
            <h2 className="text-base font-semibold inline">Run details</h2>
          </div>
          <span className="text-xs font-mono text-slate-500">{run.run_id}</span>
        </summary>

        <div className="mt-4 pt-4 border-t border-slate-800/80 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono text-slate-300">
          <div className="space-y-2">
            <div>
              <span className="text-slate-500">Run ID: </span>
              <span className="select-all text-indigo-300">{run.run_id}</span>
            </div>
            <div>
              <span className="text-slate-500">Symbol: </span>
              <span>{run.symbol}</span>
            </div>
            <div>
              <span className="text-slate-500">Workflow Status: </span>
              <span className="capitalize">{run.workflow_status}</span>
            </div>
            <div>
              <span className="text-slate-500">Research Status: </span>
              <span className="capitalize">{run.research_status ?? 'None'}</span>
            </div>
            <div>
              <span className="text-slate-500">Created At: </span>
              <span>{new Date(run.created_at).toISOString()}</span>
            </div>
            <div>
              <span className="text-slate-500">Completed At: </span>
              <span>
                {run.completed_at ? new Date(run.completed_at).toISOString() : 'Pending'}
              </span>
            </div>
            <div>
              <span className="text-slate-500">As Of (Market Close): </span>
              <span>
                {run.as_of ? new Date(run.as_of).toISOString() : 'Unavailable'}
              </span>
            </div>
          </div>

          <div className="space-y-2">
            <div>
              <span className="text-slate-500">Workflow Version: </span>
              <span>{run.versions.workflow}</span>
            </div>
            <div>
              <span className="text-slate-500">Schema Version: </span>
              <span>{run.versions.response_schema}</span>
            </div>
            <div>
              <span className="text-slate-500">Metrics Version: </span>
              <span>{run.versions.metrics}</span>
            </div>
            <div>
              <span className="text-slate-500">Policy Version: </span>
              <span>{run.versions.policy}</span>
            </div>
            <div>
              <span className="text-slate-500">Code Revision: </span>
              <span>{run.versions.code}</span>
            </div>
            {run.model_info && (
              <div>
                <span className="text-slate-500">Model Engine: </span>
                <span>
                  {run.model_info.provider} / {run.model_info.model} (
                  {run.model_info.prompt_version})
                </span>
              </div>
            )}
          </div>
        </div>
      </details>
    </section>
  );
}
