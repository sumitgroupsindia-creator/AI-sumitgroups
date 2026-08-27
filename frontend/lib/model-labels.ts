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
  /** Free accounts cannot select this slot. Defaults false until /config/models lands. */
  requiresPaidPlan?: boolean;
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

/** The customer-facing name for a provider, by key. */
export function modelDisplayName(provider: string): string {
  return modelName(modelLabel(provider));
}


/**
 * The one name a customer sees for a model.
 *
 * The tier, not the slot. Both are admin-editable and there is no rule keeping them different —
 * set to the same word they read as a stutter ("Standard · Standard"), and shown together they ask
 * the customer to hold two names for one thing. One name is enough, and the tier is the one that
 * says something useful about the model. `slot` remains in the data for the admin screens.
 */
export function modelName(label: ModelLabel): string {
  return label.tier.trim() || label.slot.trim() || 'Model';
}
