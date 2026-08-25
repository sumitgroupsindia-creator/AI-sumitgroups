import { apiFetch } from '@/lib/api-client';
import type { PublicModelSlot } from '@/types/api';

/** Public model branding. Unauthenticated, so the marketing pages can use it too. */
export function getModelSlots(): Promise<PublicModelSlot[]> {
  return apiFetch<PublicModelSlot[]>('/config/models');
}
