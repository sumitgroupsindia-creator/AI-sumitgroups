'use client';

import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { fetchAuthedBlobUrl } from '@/lib/api-client';
import { relativeTime } from '@/lib/utils';
import type { GenerationRequest } from '@/types/api';

export function ImageHistory({
  items,
  onSelect,
}: {
  items: GenerationRequest[];
  onSelect: (generation: GenerationRequest) => void;
}) {
  return (
    <section className="mx-auto max-w-5xl px-4 pb-12">
      <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-muted-foreground">History</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((generation) => (
          <button
            key={generation.id}
            onClick={() => onSelect(generation)}
            className="flex gap-3 rounded-lg border p-3 text-left transition-colors hover:bg-accent/60"
          >
            <Thumbnail generation={generation} />
            <div className="min-w-0 flex-1">
              <p className="line-clamp-2 text-sm">{generation.prompt}</p>
              <div className="mt-2 flex items-center gap-2">
                <Badge variant={generation.status === 'completed' ? 'success' : 'secondary'} className="text-[10px]">
                  {generation.status}
                </Badge>
                <span className="text-xs text-muted-foreground">{relativeTime(generation.created_at)}</span>
              </div>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function Thumbnail({ generation }: { generation: GenerationRequest }) {
  const [src, setSrc] = useState<string | null>(null);
  const thumbUrl = generation.results.find((r) => r.thumbnail_url)?.thumbnail_url;

  useEffect(() => {
    if (!thumbUrl) return;
    let objectUrl: string | null = null;
    let cancelled = false;

    void fetchAuthedBlobUrl(thumbUrl)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        setSrc(url);
      })
      .catch(() => undefined);

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [thumbUrl]);

  if (!src) return <div className="h-16 w-16 shrink-0 rounded bg-muted" />;
  // eslint-disable-next-line @next/next/no-img-element -- authenticated blob: URL
  return <img src={src} alt="" className="h-16 w-16 shrink-0 rounded object-cover" />;
}
