'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { MODEL_LABELS, modelLabel as fallbackLabel, type ModelLabel } from '@/lib/model-labels';
import * as configService from '@/services/config.service';

/**
 * Customer-facing model naming, served from the database so an administrator can rename a slot
 * without a deploy.
 *
 * Seeded with the same labels the backend ships, so the first paint is already correct and the
 * fetch only matters once someone has actually renamed something. A failed fetch leaves the
 * defaults in place rather than blanking the UI — wrong-but-stable naming beats empty buttons.
 */
const BrandingContext = createContext<Record<string, ModelLabel>>(MODEL_LABELS);

export function ModelBrandingProvider({ children }: { children: ReactNode }) {
  const [labels, setLabels] = useState<Record<string, ModelLabel>>(MODEL_LABELS);

  useEffect(() => {
    let cancelled = false;
    configService
      .getModelSlots()
      .then((slots) => {
        if (cancelled || slots.length === 0) return;
        setLabels(
          Object.fromEntries(
            slots.map((s) => [
              s.provider,
              {
                slot: s.slot,
                tier: s.tier,
                description: s.description,
                requiresPaidPlan: s.requires_paid_plan,
              },
            ]),
          ),
        );
      })
      .catch(() => {
        /* keep the defaults */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return <BrandingContext.Provider value={labels}>{children}</BrandingContext.Provider>;
}

/** Returns a lookup for one provider's customer-facing label. */
export function useModelLabel(): (provider: string) => ModelLabel {
  const labels = useContext(BrandingContext);
  return useCallback((provider: string) => labels[provider] ?? fallbackLabel(provider), [labels]);
}

/** Every known slot, in the order the backend returned them. */
export function useModelLabels(): Record<string, ModelLabel> {
  return useContext(BrandingContext);
}

/** "Model 1 · Standard" — where a single string is needed. */
export function useModelDisplayName(): (provider: string) => string {
  const label = useModelLabel();
  return useMemo(() => (provider: string) => {
    const l = label(provider);
    return `${l.slot} · ${l.tier}`;
  }, [label]);
}
