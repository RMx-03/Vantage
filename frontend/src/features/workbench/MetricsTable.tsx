import type { SimulationMetrics } from '../../types/experiments';
import { num, pct } from './format';

type Metrics = SimulationMetrics | null | undefined;

const ROWS: [string, (m: SimulationMetrics) => string][] = [
  ['Total return', (m) => pct(m.total_return)],
  ['CAGR', (m) => pct(m.cagr)],
  ['Volatility', (m) => pct(m.volatility)],
  ['Sharpe (0% risk-free)', (m) =>
    m.sharpe === null ? `Not available: ${m.sharpe_note ?? 'no reason given'}` : num(m.sharpe)],
  ['Max drawdown', (m) =>
    m.max_drawdown_start
      ? `${pct(m.max_drawdown)} (${m.max_drawdown_start} to ${m.max_drawdown_end ?? '—'})`
      : pct(m.max_drawdown)],
  ['Turnover', (m) => `${num(m.turnover)}×`],
  ['Costs', (m) => pct(m.costs)],
  ['Exposure', (m) => pct(m.exposure)],
  ['Sessions', (m) => m.sessions.toLocaleString('en-US')],
];

export default function MetricsTable({
  caption = 'Metrics',
  columns,
}: {
  caption?: string;
  columns: { name: string; metrics: Metrics }[];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm font-label">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="text-[10px] uppercase tracking-widest text-outline">
            <th scope="col" className="p-2">Measure</th>
            {columns.map((c) => (
              <th key={c.name} scope="col" className="p-2">
                {c.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map(([label, show]) => (
            <tr key={label} className="border-t border-outline-variant/40">
              <th scope="row" className="p-2 font-normal text-on-surface-variant">
                {label}
              </th>
              {columns.map((c) => (
                <td key={c.name} className="p-2 text-on-surface">
                  {c.metrics ? show(c.metrics) : '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
