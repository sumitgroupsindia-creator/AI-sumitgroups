import type { ModelSelection, ProviderName } from '@/types/api';

/**
 * The concrete slots a selection resolves to.
 *
 * 'both' is not a third provider — it is a request to fan the turn out across every enabled one,
 * which is what makes the side-by-side comparison the product is built around. Resolving it here
 * rather than at each call site is what keeps chat and image generation charging for the same
 * number of slots as they run.
 */
export function providersFor(selection: ModelSelection, known: ProviderName[]): ProviderName[] {
  return selection === 'both' ? known : [selection];
}
