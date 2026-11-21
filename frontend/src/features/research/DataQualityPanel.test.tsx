import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import DataQualityPanel from './DataQualityPanel';
import { informationalRun, informationalRunV3, keylessRunV3 } from '../../test/fixtures';

describe('DataQualityPanel', () => {
  it('shows the four optional roles for a v3 run', () => {
    render(<DataQualityPanel dataQuality={informationalRunV3.data_quality} modelInfo={null} />);

    for (const label of ['Filings', 'Fundamentals', 'Macro', 'Price cross-check']) {
      expect(screen.getByText(label)).toBeVisible();
    }
  });

  it('shows not_configured as "not configured" in the neutral style', () => {
    render(<DataQualityPanel dataQuality={keylessRunV3.data_quality} modelInfo={null} />);

    const badges = screen.getAllByText('not configured');
    expect(badges).toHaveLength(4);
    expect(badges[0].className).toContain('text-outline');
    expect(badges[0].className).not.toContain('text-error');
  });

  it('renders no role tiles for a v2 run', () => {
    render(<DataQualityPanel dataQuality={informationalRun.data_quality} modelInfo={null} />);

    for (const label of ['Filings', 'Fundamentals', 'Macro', 'Price cross-check']) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
    expect(screen.queryByText('not configured')).not.toBeInTheDocument();
  });
});
