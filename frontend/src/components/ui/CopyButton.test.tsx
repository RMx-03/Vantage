import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, afterEach } from 'vitest';
import CopyButton from './CopyButton';

afterEach(() => vi.unstubAllGlobals());

describe('CopyButton', () => {
  it('writes the value to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    render(<CopyButton value="run-123" label="Copy run ID" />);
    await userEvent.click(screen.getByRole('button', { name: 'Copy run ID' }));

    expect(writeText).toHaveBeenCalledWith('run-123');
  });

  it('confirms the copy in a live region', async () => {
    vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });

    render(<CopyButton value="run-123" label="Copy run ID" />);
    await userEvent.click(screen.getByRole('button', { name: 'Copy run ID' }));

    expect(await screen.findByText('Copied')).toBeVisible();
  });

  it('does not throw when the clipboard api is unavailable', async () => {
    vi.stubGlobal('navigator', {});

    render(<CopyButton value="run-123" label="Copy run ID" />);
    await userEvent.click(screen.getByRole('button', { name: 'Copy run ID' }));

    expect(screen.getByRole('button', { name: 'Copy run ID' })).toBeVisible();
  });
});
