'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import * as imageService from '@/services/image.service';
import type { GenerationRequest } from '@/types/api';

const TERMINAL = new Set(['completed', 'partial', 'failed']);
const POLL_MS = 1500;

/**
 * Keeps every unfinished generation in a thread up to date.
 *
 * A thread can hold several generations, and each one finishes on its own schedule — so this polls
 * only those still running and stops entirely once none are. Each poll returns the full result set,
 * which is what lets one model's card flip to done while its sibling is still working.
 */
export function useGenerationsPolling(initial: GenerationRequest[]) {
  const [generations, setGenerations] = useState<GenerationRequest[]>(initial);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setGenerations(initial);
  }, [initial]);

  const add = useCallback((generation: GenerationRequest) => {
    setGenerations((prev) => [...prev.filter((g) => g.id !== generation.id), generation]);
  }, []);

  const pending = generations.filter((g) => !TERMINAL.has(g.status)).map((g) => g.id);
  // A primitive key: depending on the array itself would restart the timer on every poll result.
  const pendingKey = pending.join(',');

  useEffect(() => {
    if (!pendingKey) return;
    let cancelled = false;

    const poll = async () => {
      const ids = pendingKey.split(',');
      try {
        const fresh = await Promise.all(ids.map((id) => imageService.getGeneration(id)));
        if (cancelled) return;
        setGenerations((prev) => prev.map((g) => fresh.find((f) => f.id === g.id) ?? g));
      } catch {
        /* transient: the next tick tries again */
      }
      if (!cancelled) timerRef.current = setTimeout(() => void poll(), POLL_MS);
    };

    timerRef.current = setTimeout(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [pendingKey]);

  return { generations, setGenerations, add };
}
