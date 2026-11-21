import { MicroLabel, Panel, PanelHeader } from '../../components/ui';
import type { Finding } from '../../types/experiments';

export default function FindingsPanel({ findings }: { findings: Finding[] }) {
  return (
    <Panel className="flex flex-col gap-3">
      <PanelHeader icon="flag">Findings</PanelHeader>
      {findings.length === 0 ? (
        <p className="text-sm text-outline font-body">No data findings for this simulation.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {findings.map((f, i) => (
            <li key={`${f.code}-${f.symbol ?? ''}-${i}`} className="flex flex-col gap-1">
              <span className="text-sm text-on-surface font-body">{f.message}</span>
              <MicroLabel>{f.code}</MicroLabel>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
