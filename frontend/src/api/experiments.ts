import { pollInterval } from '../features/research/runPolling';
import type {
  Experiment,
  ExperimentPlan,
  ExperimentSpec,
  ExperimentSummary,
  ExportFormat,
} from '../types/experiments';
import { apiError, authorizedFetch, request } from './researchRuns';

const post = (body?: unknown): RequestInit => ({
  method: 'POST',
  ...(body === undefined ? {} : { body: JSON.stringify(body) }),
});

export const planExperiment = (spec: ExperimentSpec): Promise<ExperimentPlan> =>
  request<ExperimentPlan>('/experiments/plan', post(spec));

export const createExperiment = (spec: ExperimentSpec): Promise<Experiment> =>
  request<Experiment>('/experiments', post(spec));

export const getExperiment = (id: string): Promise<Experiment> =>
  request<Experiment>(`/experiments/${encodeURIComponent(id)}`);

export const listExperiments = (limit = 20): Promise<ExperimentSummary[]> =>
  request<ExperimentSummary[]>(`/experiments?limit=${limit}`);

export const replayExperiment = (id: string): Promise<Experiment> =>
  request<Experiment>(`/experiments/${encodeURIComponent(id)}/replay`, post());

export async function deleteExperiment(id: string): Promise<void> {
  await request<null>(`/experiments/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

/** Exports need the bearer token, so they are fetched as a blob, not linked. */
export async function exportExperiment(
  id: string,
  format: ExportFormat
): Promise<{ blob: Blob; filename: string }> {
  const response = await authorizedFetch(
    `/experiments/${encodeURIComponent(id)}/export?format=${format}`
  );
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    throw apiError(response, body);
  }
  return { blob: await response.blob(), filename: `experiment-${id}.${format}` };
}

export const experimentPollInterval = (
  experiment: Experiment | undefined,
  updateCount: number
): number | false => pollInterval(experiment?.status === 'running', updateCount);
