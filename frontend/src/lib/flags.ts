/** Read at call time so tests can stub the flag. */
export const workbenchEnabled = (): boolean =>
  import.meta.env.VITE_RESEARCH_WORKBENCH_ENABLED === 'true';
