import { MicroLabel } from '../../components/ui';
import type { SimulatedTrade } from '../../types/experiments';
import { num } from './format';

const SHOWN = 200;

export default function TradesTable({
  trades,
  total = trades.length,
}: {
  trades: SimulatedTrade[];
  total?: number;
}) {
  const shown = Math.min(SHOWN, trades.length);
  if (trades.length === 0)
    return <p className="text-sm text-outline font-body">The simulation made no position changes.</p>;
  return (
    <div className="flex flex-col gap-2">
      <div className="max-h-96 overflow-auto">
        <table className="w-full text-left text-sm font-label">
          <caption className="sr-only">Simulated trades</caption>
          <thead>
            <tr className="text-[10px] uppercase tracking-widest text-outline">
              <th scope="col" className="p-2">Session</th>
              <th scope="col" className="p-2">Symbol</th>
              <th scope="col" className="p-2">Share change</th>
              <th scope="col" className="p-2">Fill price</th>
              <th scope="col" className="p-2">Notional</th>
            </tr>
          </thead>
          <tbody>
            {trades.slice(0, SHOWN).map((t, i) => (
              <tr key={`${t.session}-${t.symbol}-${i}`} className="border-t border-outline-variant/40">
                <td className="p-2">{t.session}</td>
                <td className="p-2">{t.symbol}</td>
                <td className="p-2">{num(t.shares, 4)}</td>
                <td className="p-2">{num(t.price)}</td>
                <td className="p-2">{num(t.notional)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {total > shown && (
        <MicroLabel className="normal-case tracking-normal">
          Showing {shown} of {total.toLocaleString('en-US')} simulated fills.{' '}
          {total > trades.length
            ? `Saved results and exports hold the first ${trades.length.toLocaleString('en-US')}.`
            : 'The CSV export has all of them.'}
        </MicroLabel>
      )}
    </div>
  );
}
