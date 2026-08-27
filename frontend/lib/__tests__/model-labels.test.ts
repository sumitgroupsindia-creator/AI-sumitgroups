import { describe, expect, it } from 'vitest';

import { MODEL_LABELS, modelDisplayName, modelLabel, modelName } from '@/lib/model-labels';

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

  it('names a model by its tier, so a customer holds one name and not two', () => {
    expect(modelDisplayName('openai')).toBe('Standard');
    expect(modelDisplayName('gemini')).toBe('Premium');
  });

  it('falls back to the slot when an administrator has cleared the tier', () => {
    expect(modelName({ slot: 'Model 9', tier: '  ', description: '' })).toBe('Model 9');
  });

  it('never repeats itself when slot and tier were set to the same word', () => {
    // Both fields are admin-editable and nothing keeps them apart; "Standard · Standard" is the
    // stutter this rule exists to prevent.
    expect(modelName({ slot: 'Standard', tier: 'Standard', description: '' })).toBe('Standard');
  });
});
