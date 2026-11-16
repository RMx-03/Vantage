import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SnapshotProvenancePanel from './SnapshotProvenancePanel';
import { informationalRun, informationalRunV3, keylessRunV3 } from '../../test/fixtures';

describe('SnapshotProvenancePanel', () => {
  it('lists providers by role and keeps the existing fields', () => {
    render(<SnapshotProvenancePanel snapshot={informationalRunV3.snapshot} />);

    const list = screen.getByRole('list', { name: 'Providers by role' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(6);
    expect(within(list).getByText('tiingo')).toBeVisible();
    expect(screen.getByText('Snapshot content hash')).toBeVisible();
  });

  it('shows "none" for a role without a provider and "not configured" for its quality', () => {
    render(<SnapshotProvenancePanel snapshot={keylessRunV3.snapshot} />);

    const list = screen.getByRole('list', { name: 'Providers by role' });
    expect(within(list).getAllByText('none')).toHaveLength(4);
    expect(within(list).getAllByText('not configured')).toHaveLength(4);
  });

  it('shows the error code when a provider record carries one', () => {
    const snapshot = {
      ...informationalRunV3.snapshot!,
      providers: [
        {
          role: 'macro' as const,
          provider: 'fred',
          retrieved_at: null,
          quality: 'failed' as const,
          error_code: 'PROVIDER_TIMEOUT',
          content_hash: null,
        },
      ],
    };
    render(<SnapshotProvenancePanel snapshot={snapshot} />);

    expect(screen.getByText('PROVIDER_TIMEOUT')).toBeVisible();
  });

  it('renders no provider list for a v2 run', () => {
    render(<SnapshotProvenancePanel snapshot={informationalRun.snapshot} />);

    expect(screen.queryByText('Providers by role')).not.toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });
});
