import { useQueries } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { getExperiment } from '../../api/experiments';
import { LineChart, MicroLabel, Panel, PanelHeader } from '../../components/ui';
import { useAuth } from '../../context/AuthContext';
import { SURVIVORSHIP_LABEL, type Experiment } from '../../types/experiments';
import MetricsTable from './MetricsTable';
import { describeStrategy, num } from './format';

const ASSUMPTIONS: [string, (e: Experiment) => string][] = [
  ['Research status', (e) => e.research_status ?? e.status],
  [
    'Findings',
    (e) =>
      !e.result ? '—' : e.result.findings.map((f) => f.message).join(' ') || 'None',
  ],
  ['Template', (e) => describeStrategy(e.spec.strategy)],
  ['Symbols', (e) => e.spec.symbols.join(', ')],
  ['Benchmark', (e) => e.spec.benchmark ?? 'SPY'],
  ['Start', (e) => e.spec.start],
  ['End', (e) => e.spec.end ?? 'latest'],
  ['Cost per side', (e) => `${e.spec.cost_bps ?? 10} bps`],
  ['Candidates', (e) => String(e.spec.candidates?.length ?? 0)],
  ['Engine', (e) => e.result?.engine_version ?? e.versions.engine ?? '—'],
];

/** Each experiment's net value rebased to 100, aligned on the union of dates. */
function rebased(experiments: Experiment[]) {
  const dates = [...new Set(experiments.flatMap((e) => e.result?.series?.dates ?? []))].sort();
  const series = experiments.map((e, i) => {
    const s = e.result?.series;
    const byDate = new Map<string, number>();
    if (s && s.nav.length > 0) s.dates.forEach((d, j) => byDate.set(d, (s.nav[j] / s.nav[0]) * 100));
    return { name: `Experiment ${i + 1}`, values: dates.map((d) => byDate.get(d) ?? null) };
  });
  return { dates, series };
}

export default function ComparePage() {
  const [params] = useSearchParams();
  const ownerId = useAuth().user?.id ?? null;
  const ids = [...new Set((params.get('ids') ?? '').split(',').filter(Boolean))];
  const valid = ids.length >= 2 && ids.length <= 4;
  const queries = useQueries({
    queries: (valid ? ids : []).map((id) => ({
      queryKey: ['experiment', ownerId, id],
      queryFn: () => getExperiment(id),
    })),
  });

  const back = (
    <Link to="/app/workbench" className="text-xs font-label uppercase tracking-widest text-outline hover:text-on-surface">
      ← Workbench
    </Link>
  );
  const shell = (body: React.ReactNode) => (
    <div className="w-full max-w-5xl mx-auto px-4 md:px-6 flex flex-col gap-6">
      {back}
      <h1 className="text-2xl font-extrabold tracking-tight text-primary">Compare experiments</h1>
      <p className="text-sm text-on-surface font-body border-l-2 border-outline pl-3">{SURVIVORSHIP_LABEL}</p>
      {body}
    </div>
  );

  if (!valid) return shell(<p className="text-sm font-body">Choose 2 to 4 experiments to compare.</p>);
  if (queries.some((q) => q.isError))
    return shell(<p role="alert" className="text-sm text-error font-body">One of the experiments could not be loaded.</p>);
  const experiments = queries.map((q) => q.data).filter((e): e is Experiment => Boolean(e));
  if (experiments.length < ids.length) return shell(<MicroLabel>Loading…</MicroLabel>);

  const names = experiments.map((_, i) => `Experiment ${i + 1}`);
  const chart = rebased(experiments);
  return shell(
    <>
      <Panel className="flex flex-col gap-4">
        <PanelHeader icon="rule">Assumptions</PanelHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm font-label">
            <caption className="sr-only">Assumptions</caption>
            <thead>
              <tr className="text-[10px] uppercase tracking-widest text-outline">
                <th scope="col" className="p-2">Assumption</th>
                {names.map((n) => (
                  <th key={n} scope="col" className="p-2">{n}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-outline-variant/40">
                <th scope="row" className="p-2 font-normal text-on-surface-variant">Question</th>
                {experiments.map((e) => (
                  <td key={e.id} className="p-2 font-body">
                    <Link to={`/app/workbench/${e.id}`} className="underline">{e.spec.question}</Link>
                  </td>
                ))}
              </tr>
              {ASSUMPTIONS.map(([label, value]) => {
                const values = experiments.map(value);
                const differs = new Set(values).size > 1;
                return (
                  <tr key={label} className={`border-t border-outline-variant/40 ${differs ? 'bg-surface-container-high' : ''}`}>
                    <th scope="row" className="p-2 font-normal text-on-surface-variant">
                      {label}
                      {differs && <MicroLabel className="ml-2 text-primary">differs</MicroLabel>}
                    </th>
                    {values.map((v, i) => (
                      <td key={experiments[i].id} className="p-2">{v}</td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel className="flex flex-col gap-4">
        <PanelHeader icon="table_chart">Metrics</PanelHeader>
        <MetricsTable
          columns={experiments.map((e, i) => ({ name: names[i], metrics: e.result?.metrics }))}
        />
      </Panel>

      <Panel className="flex flex-col gap-4">
        <PanelHeader icon="show_chart">Net value</PanelHeader>
        <LineChart title="Value rebased to 100" dates={chart.dates} series={chart.series} format={(n) => num(n, 1)} />
      </Panel>
    </>
  );
}
