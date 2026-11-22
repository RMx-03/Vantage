import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { listExperiments } from '../../api/experiments';
import { MicroLabel, Panel, PanelHeader, StatusChip } from '../../components/ui';
import { useAuth } from '../../context/AuthContext';
import { TEMPLATE_LABELS } from '../../types/experiments';

export default function ExperimentHistory() {
  const ownerId = useAuth().user?.id ?? null;
  const { data, isLoading, isError } = useQuery({
    queryKey: ['experiments', ownerId],
    queryFn: () => listExperiments(50),
  });
  const [picked, setPicked] = useState<string[]>([]);
  const toggle = (id: string) =>
    setPicked((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]));
  const comparable = picked.length >= 2 && picked.length <= 4;

  return (
    <Panel className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PanelHeader icon="history">Your experiments</PanelHeader>
        {comparable ? (
          <Link
            to={`/app/workbench/compare?ids=${picked.join(',')}`}
            className="text-xs font-bold font-label uppercase tracking-widest border border-outline-variant px-4 py-2 text-on-surface hover:bg-surface-container-highest"
          >
            Compare {picked.length}
          </Link>
        ) : (
          <MicroLabel>Pick 2 to 4 to compare</MicroLabel>
        )}
      </div>
      {isLoading && <MicroLabel>Loading…</MicroLabel>}
      {isError && <p className="text-sm text-error font-body">History could not be loaded.</p>}
      {data && data.length === 0 && (
        <p className="text-sm text-outline font-body">No experiments yet.</p>
      )}
      <ul className="flex flex-col gap-2">
        {data?.map((item) => (
          <li key={item.id} className="flex items-start gap-3">
            <input
              type="checkbox"
              checked={picked.includes(item.id)}
              onChange={() => toggle(item.id)}
              aria-label={`Pick for comparison: ${item.question}`}
              className="mt-4 accent-primary"
            />
            <Link
              to={`/app/workbench/${item.id}`}
              className="flex flex-1 flex-col gap-2 border border-outline-variant bg-surface-container-low p-3 hover:border-outline hover:bg-surface-container"
            >
              <span className="text-sm text-on-surface font-body">{item.question}</span>
              <span className="flex flex-wrap items-center gap-3">
                <StatusChip
                  status={item.research_status ?? (item.status === 'failed' ? 'failed' : 'unknown')}
                  label={item.research_status ?? item.status}
                />
                <MicroLabel>{TEMPLATE_LABELS[item.template]}</MicroLabel>
                <MicroLabel>{item.symbols.length} symbols</MicroLabel>
                <MicroLabel>
                  {item.start} → {item.end ?? 'latest'}
                </MicroLabel>
                {item.replay_of && <MicroLabel>replay</MicroLabel>}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
