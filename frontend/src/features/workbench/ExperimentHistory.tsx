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
    queryFn: () => listExperiments(20),
  });

  return (
    <Panel className="flex flex-col gap-4">
      <PanelHeader icon="history">Your experiments</PanelHeader>
      {isLoading && <MicroLabel>Loading…</MicroLabel>}
      {isError && <p className="text-sm text-error font-body">History could not be loaded.</p>}
      {data && data.length === 0 && (
        <p className="text-sm text-outline font-body">No experiments yet.</p>
      )}
      <ul className="flex flex-col gap-2">
        {data?.map((item) => (
          <li key={item.id}>
            <Link
              to={`/app/workbench/${item.id}`}
              className="flex flex-col gap-2 border border-outline-variant bg-surface-container-low p-3 hover:border-outline hover:bg-surface-container"
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
