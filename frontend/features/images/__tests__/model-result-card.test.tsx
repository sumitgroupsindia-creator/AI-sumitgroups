import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { ModelResultCard } from '@/features/images/model-result-card';
import type { GenerationResult } from '@/types/api';

vi.mock('@/lib/api-client', () => ({
  // Never resolves: keeps the component in its "image not yet fetched" state so tests stay
  // deterministic without needing a real blob URL.
  fetchAuthedBlobUrl: vi.fn(() => new Promise<string>(() => {})),
  API_BASE: '/api/v1',
}));

vi.mock('@/services/image.service', () => ({ downloadImage: vi.fn() }));

function makeResult(overrides: Partial<GenerationResult> = {}): GenerationResult {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    provider: 'openai',
    status: 'pending',
    error: null,
    image_url: null,
    thumbnail_url: null,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe('ModelResultCard', () => {
  beforeEach(() => vi.clearAllMocks());

  it('labels the card by its product name, never by vendor', () => {
    render(<ModelResultCard result={makeResult()} onRegenerate={vi.fn()} regenerating={false} />);

    expect(screen.getByText('Standard')).toBeInTheDocument();
    // The contract that matters: the vendor behind a slot never reaches the customer.
    expect(screen.queryByText(/openai/i)).not.toBeInTheDocument();
  });

  it('shows a loading state while the model is still working', () => {
    render(
      <ModelResultCard result={makeResult({ status: 'processing' })} onRegenerate={vi.fn()} regenerating={false} />,
    );

    expect(screen.getByText('Generating…')).toBeInTheDocument();
    expect(screen.getByText('Generating')).toBeInTheDocument(); // status badge
  });

  it('shows the error with a retry action when this model failed', () => {
    render(
      <ModelResultCard
        result={makeResult({ status: 'failed', error: 'The provider failed to generate an image.' })}
        onRegenerate={vi.fn()}
        regenerating={false}
      />,
    );

    expect(screen.getByText('The provider failed to generate an image.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });

  it('renders a failed card independently, so a sibling success is unaffected', () => {
    const { rerender } = render(
      <ModelResultCard result={makeResult({ status: 'failed', error: 'boom' })} onRegenerate={vi.fn()} regenerating={false} />,
    );
    expect(screen.getByText('Failed')).toBeInTheDocument();

    rerender(
      <ModelResultCard
        result={makeResult({ provider: 'gemini', status: 'completed', image_url: '/api/v1/files/generated/x' })}
        onRegenerate={vi.fn()}
        regenerating={false}
      />,
    );
    expect(screen.getByText('Premium')).toBeInTheDocument();
    expect(screen.queryByText(/gemini/i)).not.toBeInTheDocument();
    expect(screen.getByText('Done')).toBeInTheDocument();
  });

  it('disables download until the image is actually available', () => {
    render(<ModelResultCard result={makeResult()} onRegenerate={vi.fn()} regenerating={false} />);
    expect(screen.getByRole('button', { name: /download/i })).toBeDisabled();
  });

  it('passes the provider slot key back when regenerating', async () => {
    const onRegenerate = vi.fn();
    render(
      <ModelResultCard
        result={makeResult({ status: 'failed', error: 'boom' })}
        onRegenerate={onRegenerate}
        regenerating={false}
      />,
    );

    screen.getByRole('button', { name: /retry/i }).click();
    expect(onRegenerate).toHaveBeenCalledWith('openai');
  });
});
