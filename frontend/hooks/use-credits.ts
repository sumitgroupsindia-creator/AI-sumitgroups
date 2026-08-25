'use client';

import { useCallback, useEffect, useState } from 'react';

import * as billingService from '@/services/billing.service';
import type { Credits } from '@/types/api';

export function useCredits() {
  const [credits, setCredits] = useState<Credits | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setCredits(await billingService.getCredits());
    } catch {
      setCredits(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { credits, loading, refresh };
}
