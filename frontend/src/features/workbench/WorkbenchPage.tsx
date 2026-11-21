import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { createExperiment, planExperiment } from '../../api/experiments';
import { ApiError } from '../../api/researchRuns';
import { useAuth } from '../../context/AuthContext';
import { SURVIVORSHIP_LABEL, type ExperimentSpec } from '../../types/experiments';
import ExperimentForm from './ExperimentForm';
import ExperimentHistory from './ExperimentHistory';
import PlanPreview from './PlanPreview';
import { EMPTY_FORM, buildSpec, type FormErrors, type FormField } from './specBuilder';

export default function WorkbenchPage() {
  const [form, setForm] = useState(EMPTY_FORM);
  const [errors, setErrors] = useState<FormErrors>({});
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const ownerId = useAuth().user?.id ?? null;

  const preview = useMutation({ mutationFn: (spec: ExperimentSpec) => planExperiment(spec) });
  const start = useMutation({
    mutationFn: (spec: ExperimentSpec) => createExperiment(spec),
    onSuccess: (experiment) => {
      void queryClient.invalidateQueries({ queryKey: ['experiments', ownerId] });
      navigate(`/app/workbench/${experiment.id}`);
    },
  });

  const change = (field: FormField, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    preview.reset();
  };

  const validSpec = (): ExperimentSpec | null => {
    const built = buildSpec(form);
    setErrors(built.ok ? {} : built.errors);
    return built.ok ? built.spec : null;
  };

  const onPreview = () => {
    const spec = validSpec();
    if (spec) preview.mutate(spec);
  };

  const onSubmit = () => {
    if (start.isPending) return;
    const spec = validSpec();
    if (spec) start.mutate(spec);
  };

  const error = start.error ?? preview.error;

  return (
    <div className="w-full max-w-5xl mx-auto px-4 md:px-6 flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-3xl font-extrabold tracking-tighter text-primary">
          Research workbench
        </h1>
        <p className="text-sm text-on-surface-variant font-body">
          Simulate a fixed template on daily history to study how it behaved. Results describe
          the past only.
        </p>
        <p className="text-xs font-label uppercase tracking-widest text-outline">
          {SURVIVORSHIP_LABEL}
        </p>
      </header>

      <ExperimentForm
        value={form}
        errors={errors}
        onChange={change}
        onPreview={onPreview}
        onSubmit={onSubmit}
        previewing={preview.isPending}
        submitting={start.isPending || start.isSuccess}
      />

      {error && (
        <div role="alert" className="border border-error-container bg-error-container/30 p-4 text-error">
          <p className="text-sm font-body">
            {error instanceof ApiError ? error.error.message : 'The request failed.'}
          </p>
          {error instanceof ApiError && (
            <p className="mt-1 text-[10px] font-label uppercase tracking-widest">{error.error.code}</p>
          )}
        </div>
      )}

      {preview.data && <PlanPreview plan={preview.data} />}

      <ExperimentHistory />
    </div>
  );
}
