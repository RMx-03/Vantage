import { mapResearchError } from './researchErrors';
import { CopyButton } from '../../components/ui';

interface ResearchErrorProps {
  error: unknown;
  onRetry: () => void;
  onReauth: () => void;
  retrying: boolean;
}

export default function ResearchError({
  error,
  onRetry,
  onReauth,
  retrying,
}: ResearchErrorProps) {
  const { message, isAuthError, runId, requestId } = mapResearchError(error);

  return (
    <div className="border border-error-container bg-error-container/30 p-6 text-error">
      <div className="flex items-center gap-2 font-semibold text-error text-base mb-2 font-label">
        <span>Failed to complete research run</span>
      </div>
      <p className="text-sm leading-relaxed text-error font-body">{message}</p>

      {(runId || requestId) && (
        <div className="mt-3 flex flex-wrap gap-4 text-xs font-label text-error">
          {runId && (
            <span className="inline-flex items-center gap-2">
              <span>Run ID: {runId}</span>
              <CopyButton value={runId} label="Copy run ID" />
            </span>
          )}
          {requestId && (
            <span className="inline-flex items-center gap-2">
              <span>Request ID: {requestId}</span>
              <CopyButton value={requestId} label="Copy request ID" />
            </span>
          )}
        </div>
      )}

      <div className="mt-4 flex items-center gap-3">
        {isAuthError ? (
          <button
            type="button"
            onClick={onReauth}
            className="px-4 py-2 bg-error text-on-error text-xs font-bold font-label uppercase tracking-widest transition-opacity hover:opacity-90"
          >
            Sign in again
          </button>
        ) : (
          <button
            type="button"
            onClick={onRetry}
            disabled={retrying}
            className="px-4 py-2 bg-surface-container hover:bg-surface-container-highest text-on-surface text-xs font-bold font-label uppercase tracking-widest border border-outline-variant transition-colors disabled:opacity-50"
          >
            Retry research
          </button>
        )}
      </div>
    </div>
  );
}
