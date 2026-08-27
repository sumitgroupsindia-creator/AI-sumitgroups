'use client';

import { useEffect, useState } from 'react';

import * as billingService from '@/services/billing.service';

/**
 * Is this account on a paid plan?
 *
 * Judged by the plan's price, the same way the server judges it — a plan that costs nothing is
 * unambiguous, while matching on the code `'free'` breaks the moment a second free tier exists or
 * one gets renamed. Getting this wrong in the other direction would be worse than a locked button:
 * it would let someone pick a slot and meet a 402 after typing their prompt.
 *
 * Starts `false`, so a slot is locked until we know otherwise rather than flickering from usable
 * to locked on a slow request.
 */
export function useIsPaid(): { isPaid: boolean; loading: boolean } {
  const [isPaid, setIsPaid] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void billingService
      .getSubscription()
      .then((subscription) => {
        if (cancelled) return;
        setIsPaid(subscription?.status === 'active' && Number(subscription.plan.price) > 0);
      })
      .catch(() => {
        /* no subscription, or the request failed — treat as free */
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { isPaid, loading };
}
