import { describe, expect, it } from 'vitest';

import { MODEL_LABELS, modelDisplayName, modelLabel } from '@/lib/model-labels';

const VENDOR_PATTERN = /openai|gemini|gpt|google|anthropic|claude/i;

describe('model labels', () => {
  it('maps each provider to a neutral slot and tier', () => {
    expect(modelLabel('openai').slot).toBe('Model 1');
    expect(modelLabel('openai').tier).toBe('Standard');
    expect(modelLabel('gemini').slot).toBe('Model 2');
    expect(modelLabel('gemini').tier).toBe('Premium');
  });

  it('never exposes a vendor name in any customer-facing string', () => {
    for (const label of Object.values(MODEL_LABELS)) {
      expect(label.slot).not.toMatch(VENDOR_PATTERN);
      expect(label.tier).not.toMatch(VENDOR_PATTERN);
      expect(label.description).not.toMatch(VENDOR_PATTERN);
    }
  });

  it('falls back to a neutral label for an unknown provider rather than echoing it back', () => {
    const label = modelLabel('some-future-provider');
    expect(label.slot).toBe('Model');
    expect(label.slot).not.toContain('some-future-provider');
  });

  it('composes a display name from slot and tier', () => {
    expect(modelDisplayName('openai')).toBe('Model 1 · Standard');
    expect(modelDisplayName('gemini')).toBe('Model 2 · Premium');
  });
});
