import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Panel, PanelHeader, MicroLabel, StatusChip } from './index';

describe('ui primitives', () => {
  it('PanelHeader renders an accessible heading', () => {
    render(<PanelHeader>Metrics</PanelHeader>);
    expect(screen.getByRole('heading', { name: 'Metrics' })).toBeVisible();
  });

  it('Panel renders children', () => {
    render(<Panel><span>body</span></Panel>);
    expect(screen.getByText('body')).toBeVisible();
  });

  it('MicroLabel renders its text', () => {
    render(<MicroLabel>Recent</MicroLabel>);
    expect(screen.getByText('Recent')).toBeVisible();
  });

  it('StatusChip renders a human label per status', () => {
    const { rerender } = render(<StatusChip status="informational" />);
    expect(screen.getByText('informational')).toBeVisible();

    rerender(<StatusChip status="insufficient_data" />);
    expect(screen.getByText('insufficient data')).toBeVisible();
  });

  it('StatusChip never renders trade language', () => {
    render(<StatusChip status="review" />);
    expect(screen.queryByText(/approved|rejected/i)).not.toBeInTheDocument();
  });
});
