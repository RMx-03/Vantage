import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import Drawer from './Drawer';

describe('Drawer', () => {
  it('renders nothing when closed', () => {
    render(<Drawer open={false} onClose={vi.fn()} title="History"><p>body</p></Drawer>);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('exposes an accessible modal dialog when open', () => {
    render(<Drawer open onClose={vi.fn()} title="History"><p>body</p></Drawer>);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleName('History');
  });

  it('closes on Escape', async () => {
    const onClose = vi.fn();
    render(<Drawer open onClose={onClose} title="History"><p>body</p></Drawer>);
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });

  it('closes when the backdrop is clicked', async () => {
    const onClose = vi.fn();
    render(<Drawer open onClose={onClose} title="History"><p>body</p></Drawer>);
    await userEvent.click(screen.getByTestId('drawer-backdrop'));
    expect(onClose).toHaveBeenCalled();
  });

  it('moves focus into the dialog on open', () => {
    render(<Drawer open onClose={vi.fn()} title="History"><button>inside</button></Drawer>);
    expect(screen.getByRole('dialog')).toContainElement(document.activeElement as HTMLElement | null);
  });
});
