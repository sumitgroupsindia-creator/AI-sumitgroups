'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { MODEL_LABELS, modelLabel as fallbackLabel, type ModelLabel } from '@/lib/model-labels';
import * as configService from '@/services/config.service';
import type { ComposerMode } from '@/types/api';

/** What one operation on a slot costs the customer, in credits. One credit is one rupee. */
export type ModelPrice = Record<ComposerMode, number>;

/**
 * Customer-facing model naming, served from the database so an administrator can rename a slot
 * without a deploy.
 *
 * Seeded with the same labels the backend ships, so the first paint is already correct and the
 * fetch only matters once someone has actually renamed something. A failed fetch leaves the
 * defaults in place rather than blanking the UI — wrong-but-stable naming beats empty buttons.
 */
const BrandingContext = createContext<Record<string, ModelLabel>>(MODEL_LABELS);

/**
 * Prices ride along with the branding rather than in a request of their own: both come from the
 * same `/config/models` payload, and a composer that showed the slot's name but not yet its price
 * would quote nothing on first paint.
 *
 * Empty until that request lands. There is no sensible default price — guessing one risks quoting a
 * number the wallet then disagrees with — so callers show no figure at all rather than a wrong one.
 */
const PriceContext = createContext<Record<string, ModelPrice>>({});

export function ModelBrandingProvider({ children }: { children: ReactNode }) {
  const [labels, setLabels] = useState<Record<string, ModelLabel>>(MODEL_LABELS);
  const [prices, setPrices] = useState<Record<string, ModelPrice>>({});

  useEffect(() => {
    let cancelled = false;
    configService
      .getModelSlots()
      .then((slots) => {
        if (cancelled || slots.length === 0) return;
        setLabels(
          Object.fromEntries(
            slots.map((s) => [s.provider, { slot: s.slot, tier: s.tier, description: s.description }]),
          ),
        );
        setPrices(
          Object.fromEntries(
            slots.map((s) => [s.provider, { chat: s.chat_credit_cost, image: s.image_credit_cost }]),
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

  return (
    <BrandingContext.Provider value={labels}>
      <PriceContext.Provider value={prices}>{children}</PriceContext.Provider>
    </BrandingContext.Provider>
  );
}

/**
 * What a prompt across these slots will cost, in credits — or null while prices are still
 * unknown, so the caller can stay silent instead of quoting zero.
 */
export function useQuote(): (providers: string[], mode: ComposerMode) => number | null {
  const prices = useContext(PriceContext);
  return useCallback(
    (providers: string[], mode: ComposerMode) => {
      if (Object.keys(prices).length === 0) return null;
      let total = 0;
      for (const provider of providers) {
        const price = prices[provider];
        if (!price) return null;
        total += price[mode];
      }
      return total;
    },
    [prices],
  );
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
