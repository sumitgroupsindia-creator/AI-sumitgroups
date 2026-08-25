'use client';

import { useEffect, useRef, useState } from 'react';

import * as imageService from '@/services/image.service';
import type { GenerationRequest } from '@/types/api';

const TERMINAL = new Set(['completed', 'partial', 'failed']);
const POLL_MS = 1500;

/**
 * Polls a generation until every provider reaches a terminal state. Each poll returns the full
 * result set, so a provider that finishes first flips to `completed` in the UI while its sibling
 * is still `pending` — that is what drives the independent per-card loading states.
 */
export function useGenerationPolling(initial: GenerationRequest | null) {
  const [generation, setGeneration] = useState<GenerationRequest | null>(initial);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setGeneration(initial);
  }, [initial]);

  useEffect(() => {
    if (!generation || TERMINAL.has(generation.status)) return;

    let cancelled = false;

    const poll = async () => {
      try {
        const next = await imageService.getGeneration(generation.id);
        if (cancelled) return;
        setGeneration(next);
        if (!TERMINAL.has(next.status)) {
          timerRef.current = setTimeout(() => void poll(), POLL_MS);
        }
      } catch {
        if (!cancelled) timerRef.current = setTimeout(() => void poll(), POLL_MS * 2);
      }
    };

    timerRef.current = setTimeout(() => void poll(), POLL_MS);

    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [generation]);

  return { generation, setGeneration };
}
