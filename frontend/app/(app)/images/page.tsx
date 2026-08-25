'use client';

import { useEffect, useState } from 'react';

import { ImageStudio } from '@/features/images/image-studio';
import { ImageHistory } from '@/features/images/image-history';
import * as imageService from '@/services/image.service';
import type { GenerationRequest } from '@/types/api';

export default function ImagesPage() {
  const [history, setHistory] = useState<GenerationRequest[]>([]);
  const [selected, setSelected] = useState<GenerationRequest | null>(null);

  useEffect(() => {
    void imageService
      .listGenerations()
      .then((items) => {
        setHistory(items);
        setSelected((current) => current ?? items[0] ?? null);
      })
      .catch(() => setHistory([]));
  }, []);

  return (
    <div>
      <ImageStudio initialGeneration={selected} />
      {history.length > 0 && <ImageHistory items={history} onSelect={setSelected} />}
    </div>
  );
}
