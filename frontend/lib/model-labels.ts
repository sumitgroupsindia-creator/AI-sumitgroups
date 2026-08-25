import type { ProviderName } from '@/types/api';

/**
 * Default presentation for model slots.
 *
 * These are the values the backend seeds, kept here so the UI paints correct labels before the
 * branding request resolves and has something to fall back on if it fails. The live values come
 * from `features/branding/model-branding` — read them with `useModelLabel`, not from this file, in
 * anything a customer sees.
 *
 * The underlying provider names (OpenAI, Gemini) are deliberately never shown in the customer-facing
 * UI — users see neutral, product-owned labels instead. This keeps the branding ours and lets a
 * provider be swapped behind a slot without changing what customers see. Admin screens are the one
 * exception: they show the real provider, because that is what an administrator configures.
 */
export interface ModelLabel {
  slot: string;
  tier: string;
  description: string;
}

export const MODEL_LABELS: Record<ProviderName, ModelLabel> = {
  openai: {
    slot: 'Model 1',
    tier: 'Standard',
    description: 'Balanced quality and speed for everyday prompts.',
  },
  gemini: {
    slot: 'Model 2',
    tier: 'Premium',
    description: 'Alternative interpretation, often stronger on detail and lighting.',
  },
};

export function modelLabel(provider: string): ModelLabel {
  return (
    MODEL_LABELS[provider as ProviderName] ?? {
      slot: 'Model',
      tier: 'Standard',
      description: '',
    }
  );
}

/** "Model 1 · Standard" — used where a single string is needed. */
export function modelDisplayName(provider: string): string {
  const label = modelLabel(provider);
  return `${label.slot} · ${label.tier}`;
}
