'use client';

import { useEffect, useState } from 'react';
import { ImageOff } from 'lucide-react';

import { fetchAuthedBlobUrl } from '@/lib/api-client';
import { cn } from '@/lib/utils';

/**
 * A stored upload, shown inside the turn it was attached to. Fetched as an authenticated blob
 * because the file route requires a bearer token, which a plain <img src> cannot send.
 */
export function AttachedImage({ uploadFileId, className }: { uploadFileId: string; className?: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    void fetchAuthedBlobUrl(`/files/uploaded/${uploadFileId}`)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        setSrc(url);
      })
      .catch(() => !cancelled && setFailed(true));

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [uploadFileId]);

  if (failed) {
    return (
      <div className={cn('flex h-20 w-20 items-center justify-center rounded-lg border', className)}>
        <ImageOff className="h-4 w-4 text-muted-foreground" />
      </div>
    );
  }
  if (!src) return <div className={cn('h-20 w-20 animate-pulse rounded-lg bg-muted', className)} />;

  // eslint-disable-next-line @next/next/no-img-element -- blob: URLs cannot go through next/image
  return <img src={src} alt="भेजी गई तस्वीर" className={cn('h-20 w-20 rounded-lg object-cover', className)} />;
}
