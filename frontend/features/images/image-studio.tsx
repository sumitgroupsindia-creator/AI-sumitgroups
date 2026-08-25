'use client';

import { useCallback, useRef, useState } from 'react';
import { AlertCircle, ImagePlus, Loader2, Sparkles, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ModelResultCard } from '@/features/images/model-result-card';
import { useCredits } from '@/hooks/use-credits';
import { useGenerationPolling } from '@/hooks/use-generation-polling';
import { ApiError } from '@/lib/api-client';
import { modelLabel } from '@/lib/model-labels';
import * as imageService from '@/services/image.service';
import { cn } from '@/lib/utils';
import type { GenerationRequest, ProviderName } from '@/types/api';

type Mode = 'openai' | 'gemini' | 'both';

const MODE_PROVIDERS: Record<Mode, ProviderName[]> = {
  openai: ['openai'],
  gemini: ['gemini'],
  both: ['openai', 'gemini'],
};

const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp'];

export function ImageStudio({ initialGeneration = null }: { initialGeneration?: GenerationRequest | null }) {
  const [prompt, setPrompt] = useState('');
  const [mode, setMode] = useState<Mode>('both');
  const [file, setFile] = useState<File | null>(null);
  const [filePreview, setFilePreview] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [regeneratingProvider, setRegeneratingProvider] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  // setState is async, so a fast double-click can pass the `submitting` check twice and be
  // charged twice. A ref flips synchronously.
  const inFlightRef = useRef(false);
  const { generation, setGeneration } = useGenerationPolling(initialGeneration);
  const { credits, refresh: refreshCredits } = useCredits();

  const pickFile = (selected: File | null) => {
    if (filePreview) URL.revokeObjectURL(filePreview);
    if (!selected) {
      setFile(null);
      setFilePreview(null);
      return;
    }
    if (!ACCEPTED.includes(selected.type)) {
      setError('Please choose a JPG, PNG or WEBP image.');
      return;
    }
    setError(null);
    setFile(selected);
    setFilePreview(URL.createObjectURL(selected));
  };

  const submit = useCallback(async () => {
    const trimmed = prompt.trim();
    if (!trimmed || inFlightRef.current) return;

    inFlightRef.current = true;
    setSubmitting(true);
    setError(null);
    try {
      const providers = MODE_PROVIDERS[mode];
      const created = file
        ? await imageService.generateWithUpload(file, trimmed, providers)
        : await imageService.generateImages(trimmed, providers);
      setGeneration(created);
      void refreshCredits();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Could not start the generation. Please try again.',
      );
    } finally {
      setSubmitting(false);
    }
  }, [prompt, mode, file, submitting, setGeneration, refreshCredits]);

  const handleRegenerate = useCallback(
    async (provider: ProviderName) => {
      if (!generation) return;
      setRegeneratingProvider(provider);
      setError(null);
      try {
        setGeneration(await imageService.regenerate(generation.id, provider));
        void refreshCredits();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Could not regenerate. Please try again.');
      } finally {
        setRegeneratingProvider(null);
      }
    },
    [generation, setGeneration, refreshCredits],
  );

  // Newest result per provider — a regenerate appends a row rather than replacing it.
  const latestByProvider = new Map<string, GenerationRequest['results'][number]>();
  for (const result of generation?.results ?? []) {
    const existing = latestByProvider.get(result.provider);
    if (!existing || new Date(result.created_at) >= new Date(existing.created_at)) {
      latestByProvider.set(result.provider, result);
    }
  }
  const openaiResult = latestByProvider.get('openai');
  const geminiResult = latestByProvider.get('gemini');

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Image Studio</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          One prompt, two models, side by side. Upload a photo to use it as the starting point.
        </p>
      </header>

      <div className="rounded-xl border bg-card p-4">
        <Textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void submit();
          }}
          placeholder="Create a professional cinematic portrait, dramatic side lighting, shallow depth of field…"
          rows={3}
          className="resize-none border-0 p-0 focus-visible:ring-0"
        />

        {filePreview && (
          <div className="mt-3 inline-flex items-center gap-2 rounded-lg border p-2">
            {/* eslint-disable-next-line @next/next/no-img-element -- local object URL preview */}
            <img src={filePreview} alt="Upload preview" className="h-14 w-14 rounded object-cover" />
            <div className="text-xs">
              <p className="max-w-[12rem] truncate font-medium">{file?.name}</p>
              <p className="text-muted-foreground">Used as generation input</p>
            </div>
            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => pickFile(null)}>
              <X className="h-3.5 w-3.5" />
              <span className="sr-only">Remove upload</span>
            </Button>
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t pt-3">
          <div className="flex items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED.join(',')}
              className="hidden"
              onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
            />
            <Button size="sm" variant="outline" className="gap-2" onClick={() => fileInputRef.current?.click()}>
              <ImagePlus className="h-3.5 w-3.5" />
              Upload photo
            </Button>

            <div className="inline-flex rounded-md border p-0.5" role="radiogroup" aria-label="Models to run">
              {(['openai', 'gemini', 'both'] as Mode[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  role="radio"
                  aria-checked={mode === option}
                  onClick={() => setMode(option)}
                  title={option === 'both' ? 'Run both models' : modelLabel(option).description}
                  className={cn(
                    'rounded px-3 py-1 text-xs font-medium transition-colors',
                    mode === option ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {option === 'both' ? 'Both' : modelLabel(option).slot}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3">
            {credits && (
              <span className="text-xs text-muted-foreground">
                {credits.image_balance} image credits left
              </span>
            )}
            <Button onClick={() => void submit()} disabled={!prompt.trim() || submitting} className="gap-2">
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Generate
            </Button>
          </div>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/5 p-4">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          <div className="flex-1 text-sm">
            <p>{error}</p>
            {error.toLowerCase().includes('credit') && (
              <a href="/pricing" className="mt-1 inline-block underline underline-offset-2">
                View plans
              </a>
            )}
          </div>
        </div>
      )}

      {generation && (
        <section className="space-y-4">
          <div className="flex items-baseline justify-between gap-4">
            <p className="min-w-0 flex-1 truncate text-sm text-muted-foreground">“{generation.prompt}”</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {openaiResult && (
              <ModelResultCard
                result={openaiResult}
                onRegenerate={handleRegenerate}
                regenerating={regeneratingProvider === 'openai'}
              />
            )}
            {geminiResult && (
              <ModelResultCard
                result={geminiResult}
                onRegenerate={handleRegenerate}
                regenerating={regeneratingProvider === 'gemini'}
              />
            )}
          </div>
        </section>
      )}
    </div>
  );
}
