import { MicroLabel, Panel, PanelHeader } from '../../components/ui';
import { SURVIVORSHIP_LABEL, type ExperimentPlan } from '../../types/experiments';

const number = (n: number) => n.toLocaleString('en-US');

export default function PlanPreview({ plan }: { plan: ExperimentPlan }) {
  const rows: [string, string][] = [
    ['Sessions', number(plan.sessions)],
    ['Warm-up sessions', number(plan.warmup_sessions)],
    ['Walk-forward windows', number(plan.windows)],
    ['Candidates', number(plan.candidates)],
    ['Engine runs', number(plan.engine_invocations)],
    ['Data from', plan.fetch_start],
    ['End', plan.end],
  ];
  return (
    <div role="region" aria-label="Plan preview">
      <Panel className="flex flex-col gap-4">
        <PanelHeader icon="fact_check">Plan preview</PanelHeader>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-4">
          {rows.map(([term, value]) => (
            <div key={term} className="flex flex-col gap-1">
              <dt>
                <MicroLabel>{term}</MicroLabel>
              </dt>
              <dd className="font-label text-on-surface">{value}</dd>
            </div>
          ))}
        </dl>
        {plan.warnings.length > 0 && (
          <ul className="flex flex-col gap-1 text-sm text-on-surface-variant font-body">
            {plan.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
        <p className="text-sm text-on-surface-variant font-body">{SURVIVORSHIP_LABEL}</p>
        <MicroLabel className="normal-case tracking-normal">
          A preview fetches no data and starts nothing.
        </MicroLabel>
      </Panel>
    </div>
  );
}
