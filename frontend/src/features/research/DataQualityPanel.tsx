import type { DataQuality, ModelInfo } from '../../types/research';
import { Panel, PanelHeader } from '../../components/ui';

interface DataQualityPanelProps {
  dataQuality: DataQuality | null;
  modelInfo: ModelInfo | null;
}

function getQualityBadgeClass(status: string) {
  switch (status) {
    case 'sufficient':
    case 'fresh':
    case 'healthy':
      return 'border-outline-variant bg-surface-container-highest text-on-surface';
    case 'degraded':
    case 'partial':
    case 'stale':
      return 'border-outline bg-surface-container-highest text-on-surface-variant font-bold';
    case 'insufficient':
    case 'missing':
    case 'failed':
      return 'border-error-container bg-error-container/30 text-error';
    case 'not_run':
    default:
      return 'border-outline-variant/30 bg-surface-container text-outline';
  }
}

export default function DataQualityPanel({ dataQuality, modelInfo }: DataQualityPanelProps) {
  return (
    <Panel>
      <div className="mb-4">
        <PanelHeader icon="verified">Data quality</PanelHeader>
      </div>

      {!dataQuality ? (
        <p className="text-sm text-outline">Data quality metrics unavailable for this run.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="border border-outline-variant/30 bg-surface-container-low p-4">
            <div className="text-xs font-medium text-outline uppercase tracking-wider mb-2 font-label">
              Overall Quality
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center px-2.5 py-1 text-sm font-semibold capitalize border font-label ${getQualityBadgeClass(
                  dataQuality.overall
                )}`}
              >
                {dataQuality.overall}
              </span>
            </div>
          </div>

          <div className="border border-outline-variant/30 bg-surface-container-low p-4">
            <div className="text-xs font-medium text-outline uppercase tracking-wider mb-2 font-label">
              Prices Component
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center px-2.5 py-1 text-sm font-semibold capitalize border font-label ${getQualityBadgeClass(
                  dataQuality.prices
                )}`}
              >
                {dataQuality.prices}
              </span>
            </div>
          </div>

          <div className="border border-outline-variant/30 bg-surface-container-low p-4">
            <div className="text-xs font-medium text-outline uppercase tracking-wider mb-2 font-label">
              News Component
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center px-2.5 py-1 text-sm font-semibold capitalize border font-label ${getQualityBadgeClass(
                  dataQuality.news
                )}`}
              >
                {dataQuality.news}
              </span>
            </div>
          </div>

          <div className="border border-outline-variant/30 bg-surface-container-low p-4">
            <div className="text-xs font-medium text-outline uppercase tracking-wider mb-2 font-label">
              Model Quality
            </div>
            <div className="flex flex-col gap-1">
              <span
                className={`inline-flex items-center px-2.5 py-1 text-sm font-semibold capitalize border w-fit font-label ${getQualityBadgeClass(
                  dataQuality.model
                )}`}
              >
                {dataQuality.model.replace('_', ' ')}
              </span>
              {modelInfo?.failure_code && (
                <span className="text-[11px] font-label text-error mt-1">
                  Code: {modelInfo.failure_code}
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}
