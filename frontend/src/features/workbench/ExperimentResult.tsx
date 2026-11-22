import type { ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  deleteExperiment,
  experimentPollInterval,
  exportExperiment,
  getExperiment,
  replayExperiment,
} from '../../api/experiments';
import { ApiError } from '../../api/researchRuns';
import { LineChart, MicroLabel, Panel, PanelHeader, StatusChip } from '../../components/ui';
import { useAuth } from '../../context/AuthContext';
import type {
  Experiment,
  ExportFormat,
  SimulationSeries,
  WalkForwardResult,
} from '../../types/experiments';
import FindingsPanel from './FindingsPanel';
import MetricsTable from './MetricsTable';
import TradesTable from './TradesTable';
import { describeStrategy, num, pct } from './format';

const ACTION =
  'px-4 py-2 text-xs font-bold font-label uppercase tracking-widest border border-outline-variant bg-surface-container text-on-surface hover:bg-surface-container-highest disabled:opacity-50';

const message = (error: unknown) =>
  error instanceof ApiError ? error.error.message : 'The request failed.';

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  // Revoking in the same task can cancel the download in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export default function ExperimentResult() {
  const { experimentId = '' } = useParams<{ experimentId: string }>();
  const ownerId = useAuth().user?.id ?? null;
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = ['experiment', ownerId, experimentId];

  const query = useQuery({
    queryKey: key,
    queryFn: () => getExperiment(experimentId),
    enabled: Boolean(experimentId),
    refetchInterval: (q) => experimentPollInterval(q.state.data, q.state.dataUpdateCount),
  });
  const done = () => void queryClient.invalidateQueries({ queryKey: ['experiments', ownerId] });
  const replay = useMutation({
    mutationFn: (id: string) => replayExperiment(id),
    onSuccess: (next) => {
      done();
      navigate(`/app/workbench/${next.id}`);
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteExperiment(id),
    onSuccess: () => {
      done();
      navigate('/app/workbench');
    },
  });
  const exporter = useMutation({
    mutationFn: (format: ExportFormat) => exportExperiment(experimentId, format),
    onSuccess: ({ blob, filename }) => download(blob, filename),
  });

  const experiment = query.data;
  if (query.isLoading) return <Shell><MicroLabel>Loading experiment…</MicroLabel></Shell>;
  if (!experiment)
    return (
      <Shell>
        <div role="alert" className="text-error font-body">
          {query.isError ? message(query.error) : 'Experiment not found.'}
        </div>
      </Shell>
    );

  const count = queryClient.getQueryState(key)?.dataUpdateCount ?? 0;
  const exhausted =
    experiment.status === 'running' && experimentPollInterval(experiment, count) === false;
  const actionError = replay.error ?? remove.error ?? exporter.error;

  return (
    <Shell>
      <Header experiment={experiment} />

      {experiment.status === 'running' && (
        <Panel className="flex flex-col gap-3">
          <p role="status" className="text-sm font-label uppercase tracking-widest text-outline">
            Simulation running…
          </p>
          {exhausted && (
            <button type="button" className={`${ACTION} self-start`} onClick={() => void query.refetch()}>
              Check again
            </button>
          )}
        </Panel>
      )}

      {experiment.status === 'failed' && (
        <div className="border border-error-container bg-error-container/30 p-4 text-error">
          <p className="text-sm font-body">{experiment.error_message}</p>
          <p className="mt-1 text-[10px] font-label uppercase tracking-widest">{experiment.error_code}</p>
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        {experiment.status === 'succeeded' && (
          <button
            type="button"
            className={ACTION}
            disabled={replay.isPending}
            onClick={() => replay.mutate(experiment.id)}
          >
            Replay from saved inputs
          </button>
        )}
        {experiment.status !== 'running' && (
          <>
            <button type="button" className={ACTION} onClick={() => exporter.mutate('csv')}>
              Export CSV
            </button>
            <button type="button" className={ACTION} onClick={() => exporter.mutate('json')}>
              Export JSON
            </button>
            <button
              type="button"
              className={ACTION}
              disabled={remove.isPending}
              onClick={() => {
                if (window.confirm('Delete this experiment? This cannot be undone.'))
                  remove.mutate(experiment.id);
              }}
            >
              Delete
            </button>
          </>
        )}
      </div>
      {actionError && (
        <p role="alert" className="text-sm text-error font-body">
          {message(actionError)}
        </p>
      )}

      {experiment.result && <ResultBody experiment={experiment} />}
    </Shell>
  );
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="w-full max-w-5xl mx-auto px-4 md:px-6 flex flex-col gap-6">
      <Link to="/app/workbench" className="text-xs font-label uppercase tracking-widest text-outline hover:text-on-surface">
        ← Workbench
      </Link>
      {children}
    </div>
  );
}

function Header({ experiment }: { experiment: Experiment }) {
  const { spec } = experiment;
  return (
    <header className="flex flex-col gap-3">
      <h1 className="text-2xl font-extrabold tracking-tight text-primary">{spec.question}</h1>
      <div className="flex flex-wrap items-center gap-3">
        <StatusChip
          status={experiment.research_status ?? (experiment.status === 'failed' ? 'failed' : 'unknown')}
          label={experiment.research_status ?? experiment.status}
        />
        <MicroLabel>{describeStrategy(spec.strategy)}</MicroLabel>
        <MicroLabel>
          {spec.start} → {spec.end ?? 'latest'}
        </MicroLabel>
        <MicroLabel>{spec.cost_bps ?? 10} bps per side</MicroLabel>
        {experiment.replay_of && (
          <Link to={`/app/workbench/${experiment.replay_of}`} className="text-xs font-label underline text-outline">
            replay of an earlier experiment
          </Link>
        )}
      </div>
      <p className="text-xs font-label text-on-surface-variant">
        {spec.symbols.join(', ')} · benchmark {spec.benchmark ?? 'SPY'}
      </p>
      {spec.hypothesis && <p className="text-sm text-on-surface-variant font-body">{spec.hypothesis}</p>}
      <p className="text-sm text-on-surface font-body border-l-2 border-outline pl-3">{experiment.label}</p>
    </header>
  );
}

function chartOf(title: string, series: SimulationSeries) {
  return (
    <LineChart
      title={title}
      dates={series.dates}
      format={(n) => num(n, 0)}
      series={[
        { name: 'Net', values: series.nav },
        { name: 'Gross', values: series.gross_nav },
        ...(series.benchmark_nav ? [{ name: 'Benchmark', values: series.benchmark_nav }] : []),
      ]}
    />
  );
}

function ResultBody({ experiment }: { experiment: Experiment }) {
  const result = experiment.result!;
  return (
    <>
      <FindingsPanel findings={result.findings} />

      <Panel className="flex flex-col gap-4">
        <PanelHeader icon="table_chart">Metrics</PanelHeader>
        <MetricsTable
          columns={[
            { name: 'Simulation', metrics: result.metrics },
            { name: `Benchmark ${experiment.spec.benchmark ?? 'SPY'}`, metrics: result.benchmark_metrics },
          ]}
        />
      </Panel>

      {result.series && (
        <Panel className="flex flex-col gap-4">
          <PanelHeader icon="show_chart">Simulated value</PanelHeader>
          {chartOf('Simulated value, net and gross of costs', result.series)}
        </Panel>
      )}

      {result.cost_stress.length > 0 && (
        <Panel className="flex flex-col gap-4">
          <PanelHeader icon="tune">Cost stress</PanelHeader>
          <table className="w-full text-left text-sm font-label">
            <caption className="sr-only">Cost stress</caption>
            <thead>
              <tr className="text-[10px] uppercase tracking-widest text-outline">
                <th scope="col" className="p-2">Cost multiple</th>
                <th scope="col" className="p-2">Bps per side</th>
                <th scope="col" className="p-2">Total return</th>
                <th scope="col" className="p-2">Sharpe</th>
              </tr>
            </thead>
            <tbody>
              {result.cost_stress.map((c) => (
                <tr key={c.multiplier} className="border-t border-outline-variant/40">
                  <td className="p-2">{c.multiplier}×</td>
                  <td className="p-2">{c.cost_bps}</td>
                  <td className="p-2">{pct(c.metrics.total_return)}</td>
                  <td className="p-2">{num(c.metrics.sharpe)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}

      {result.walk_forward && <WalkForward result={result.walk_forward} />}

      <Panel className="flex flex-col gap-4">
        <PanelHeader icon="swap_vert">Simulated trades</PanelHeader>
        <TradesTable trades={result.trades} total={result.trade_count ?? undefined} />
      </Panel>

      <Panel className="flex flex-col gap-3">
        <PanelHeader icon="fingerprint">Versions</PanelHeader>
        <dl className="grid gap-2 md:grid-cols-2">
          {Object.entries(experiment.versions).map(([k, v]) => (
            <div key={k} className="flex flex-col">
              <dt><MicroLabel>{k}</MicroLabel></dt>
              <dd className="font-label text-xs text-on-surface break-all">{v}</dd>
            </div>
          ))}
        </dl>
      </Panel>
    </>
  );
}

function WalkForward({ result }: { result: WalkForwardResult }) {
  return (
    <Panel className="flex flex-col gap-4">
      <PanelHeader icon="timeline">Walk-forward evaluation</PanelHeader>
      {result.status === 'insufficient_data' ? (
        <p className="text-sm text-on-surface-variant font-body">
          There was too little history for three walk-forward windows, so only the full-period
          simulation is shown.
        </p>
      ) : (
        <>
          <p className="text-sm text-on-surface-variant font-body">
            {result.trial_count} candidate trials. Each test window uses the candidate with the
            best training Sharpe; the curve below joins the test windows only.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm font-label">
              <caption className="sr-only">Walk-forward windows</caption>
              <thead>
                <tr className="text-[10px] uppercase tracking-widest text-outline">
                  <th scope="col" className="p-2">Training</th>
                  <th scope="col" className="p-2">Test</th>
                  <th scope="col" className="p-2">Candidate</th>
                  <th scope="col" className="p-2">Training Sharpe</th>
                </tr>
              </thead>
              <tbody>
                {result.windows.map((w) => (
                  <tr key={w.test_start} className="border-t border-outline-variant/40">
                    <td className="p-2">{w.train_start} → {w.train_end}</td>
                    <td className="p-2">{w.test_start} → {w.test_end}</td>
                    <td className="p-2">{w.selected === null ? 'none' : `#${w.selected + 1}`}</td>
                    <td className="p-2">{num(w.train_sharpe)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {result.oos_metrics && (
            <MetricsTable
              caption="Out-of-sample metrics"
              columns={[{ name: 'Out of sample', metrics: result.oos_metrics }]}
            />
          )}
          {result.oos_series && chartOf('Out-of-sample value', result.oos_series)}
        </>
      )}
    </Panel>
  );
}
