'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, ImageIcon, Loader2, Paperclip, Sparkles, X } from 'lucide-react';

import { ACCEPTED_TYPES } from '@/features/composer/prompt-box';
import { useModelLabel, useModelLabels } from '@/features/branding/model-branding';
import { ModelResultCard } from '@/features/images/model-result-card';
import { providersFor } from '@/features/composer/slots';
import { useCredits } from '@/hooks/use-credits';
import { useGenerationsPolling } from '@/hooks/use-generations-polling';
import { cn } from '@/lib/utils';
import * as imageService from '@/services/image.service';
import type { GenerationRequest, ModelSelection, ProviderName } from '@/types/api';

/**
 * The picture desk: what to make on the left, what came back on the right.
 *
 * A dedicated screen rather than the chat thread because making an image is an iterative job with
 * settings — the shape, which slots answer, the source photo — and re-reading those out of a
 * scrolling conversation is harder than leaving them on a panel that stays put. The thread still
 * generates images inline; this is the same API with the controls exposed.
 */

const SHAPES: { value: string; label: string; hint: string; box: string }[] = [
  { value: 'portrait', label: 'पोर्ट्रेट', hint: '9:16 — स्टोरी', box: 'h-7 w-[18px]' },
  { value: 'square', label: 'चौकोर', hint: '1:1 — फ़ीड पोस्ट', box: 'h-6 w-6' },
  { value: 'landscape', label: 'चौड़ा', hint: '16:9 — बैनर', box: 'h-[18px] w-7' },
];

// A stable identity. `useGenerationsPolling` re-syncs whenever `initial` changes, so a fresh []
// literal here would re-sync on every render and loop forever.
const NO_GENERATIONS: GenerationRequest[] = [];

const PRESETS = [
  'प्रोडक्ट फ़ोटो को साफ़ सफ़ेद बैकग्राउंड पर स्टूडियो जैसा बनाओ',
  'दिवाली ऑफ़र का पोस्टर — 50% छूट, चमकदार रंग',
  'इंस्टाग्राम स्टोरी साइज़ में मेन्यू का डिज़ाइन बनाओ',
];

export default function ImagesPage() {
  const labels = useModelLabels();
  const labelFor = useModelLabel();
  const { refresh: refreshCredits } = useCredits();
  // Memoised on the labels themselves: `Object.keys` builds a new array each render, and the
  // memo below takes it as a dependency.
  const knownProviders = useMemo(() => Object.keys(labels) as ProviderName[], [labels]);

  const [prompt, setPrompt] = useState('');
  const [selection, setSelection] = useState<ModelSelection>('both');
  const [shape, setShape] = useState('portrait');
  const [attachment, setAttachment] = useState<{ file: File; previewUrl: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { generations, setGenerations, add } = useGenerationsPolling(NO_GENERATIONS);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const providers = useMemo(
    () => providersFor(selection, knownProviders),
    [selection, knownProviders],
  );

  useEffect(() => {
    void imageService
      .listGenerations(12)
      .then(setGenerations)
      .catch(() => setGenerations([]));
  }, [setGenerations]);

  useEffect(() => {
    const url = attachment?.previewUrl;
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [attachment?.previewUrl]);

  const pickFile = (file: File | undefined) => {
    if (!file) return;
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setError('सिर्फ़ JPG, PNG या WEBP तस्वीर लगाई जा सकती है।');
      return;
    }
    setError(null);
    setAttachment({ file, previewUrl: URL.createObjectURL(file) });
  };

  const generate = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;

      setBusy(true);
      setError(null);
      try {
        // The shape rides along in the prompt: the image APIs take one instruction and no
        // settings object, so this is the only channel there is for it.
        const shaped = `${trimmed}\n\n[${SHAPES.find((s) => s.value === shape)?.hint ?? shape}]`;
        const created = attachment
          ? await imageService.generateWithUpload(attachment.file, shaped, providers)
          : await imageService.generateImages(shaped, providers);
        add(created);
        setPrompt('');
        setAttachment(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
        void refreshCredits();
      } catch (err) {
        setError(
          err instanceof Error && err.message ? err.message : 'तस्वीर नहीं बन पाई। दोबारा कोशिश करो।',
        );
      } finally {
        setBusy(false);
      }
    },
    [add, attachment, busy, providers, refreshCredits, shape],
  );

  const regenerate = async (generationId: string, provider: ProviderName) => {
    try {
      const updated = await imageService.regenerate(generationId, provider);
      add(updated);
      void refreshCredits();
    } catch {
      setError('दोबारा नहीं बन पाई।');
    }
  };

  return (
    // No scroller of its own: the shell's <main> is the one that scrolls, and nesting a second one
    // here produced two scrollbars and a sticky column that stuck to the wrong thing.
    <div className="min-h-full">
      <div className="mx-auto grid max-w-6xl gap-5 px-4 py-6 lg:grid-cols-[340px_minmax(0,1fr)]">
        {/* ------------------------------------------------------------ controls */}
        <div className="space-y-4 lg:sticky lg:top-4 lg:self-start">
          <div className="rounded-2xl border border-border/70 bg-card p-4">
            <h1 className="flex items-center gap-2 text-[15px] font-semibold">
              <ImageIcon className="h-4 w-4 text-primary" />
              तस्वीर बनाओ
            </h1>

            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void generate(prompt);
              }}
              rows={4}
              placeholder="जो तस्वीर चाहिए वो लिखो…"
              className="mt-3 w-full resize-none rounded-xl border border-border/70 bg-background/60 p-3 text-[13.5px] leading-relaxed outline-none transition-colors placeholder:text-muted-foreground focus:border-ring"
            />

            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_TYPES.join(',')}
              className="hidden"
              onChange={(e) => pickFile(e.target.files?.[0])}
            />

            {attachment ? (
              <div className="mt-2 flex items-center gap-2.5 rounded-xl border border-border/70 bg-background/60 p-2">
                {/* eslint-disable-next-line @next/next/no-img-element -- blob: URL */}
                <img src={attachment.previewUrl} alt="" className="h-10 w-10 rounded-lg object-cover" />
                <span className="flex-1 truncate text-[11px] text-muted-foreground">
                  {attachment.file.name}
                </span>
                <button
                  type="button"
                  onClick={() => setAttachment(null)}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                  <span className="sr-only">हटाओ</span>
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-border px-3 py-2.5 text-[12.5px] text-muted-foreground transition-colors hover:border-ring/60 hover:text-foreground"
              >
                <Paperclip className="h-3.5 w-3.5" />
                अपनी फ़ोटो लगाओ
              </button>
            )}

            <button
              type="button"
              onClick={() => void generate(prompt)}
              disabled={!prompt.trim() || busy}
              className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {busy ? 'बन रही है…' : 'बनाओ'}
            </button>

          </div>

          {/* --------------------------------------------------------- model */}
          <Panel title="कौन सा मॉडल">
            <div className="grid gap-1.5">
              {[...knownProviders, 'both' as const].map((option) => {
                const active = selection === option;
                const label = option === 'both' ? 'दोनों' : labelFor(option).slot;
                const hint =
                  option === 'both'
                    ? 'दोनों से एक साथ — दो तस्वीरें, दुगुने क्रेडिट'
                    : `${labelFor(option).tier} · ${labelFor(option).description}`;
                return (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setSelection(option as ModelSelection)}
                    className={cn(
                      'rounded-xl border px-3 py-2 text-left transition-colors',
                      active
                        ? 'border-primary/50 bg-primary/10'
                        : 'border-border/70 hover:bg-accent/60',
                    )}
                  >
                    <p className={cn('text-[13px] font-medium', active && 'text-primary')}>{label}</p>
                    <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{hint}</p>
                  </button>
                );
              })}
            </div>
          </Panel>

          {/* --------------------------------------------------------- shape */}
          <Panel title="शेप">
            <div className="grid grid-cols-3 gap-1.5">
              {SHAPES.map((option) => {
                const active = shape === option.value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setShape(option.value)}
                    title={option.hint}
                    className={cn(
                      'flex flex-col items-center gap-1.5 rounded-xl border px-2 py-2.5 transition-colors',
                      active ? 'border-primary/50 bg-primary/10' : 'border-border/70 hover:bg-accent/60',
                    )}
                  >
                    <span
                      className={cn(
                        'rounded-[3px] border-2',
                        option.box,
                        active ? 'border-primary' : 'border-muted-foreground/60',
                      )}
                    />
                    <span className={cn('text-[11px]', active ? 'text-primary' : 'text-muted-foreground')}>
                      {option.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </Panel>
        </div>

        {/* ------------------------------------------------------------- canvas */}
        <div className="min-w-0 space-y-4">
          {error && (
            <div className="flex items-start gap-3 rounded-xl border border-destructive/40 bg-destructive/5 p-3.5">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
              <p className="text-[13px]">{error}</p>
            </div>
          )}

          {generations.length === 0 ? (
            <div className="flex min-h-[420px] flex-col items-center justify-center rounded-2xl border border-dashed border-border/70 bg-card/40 px-6 text-center">
              <ImageIcon className="h-9 w-9 text-muted-foreground/50" />
              <p className="mt-3 text-sm font-medium">अभी कोई तस्वीर नहीं</p>
              <p className="mt-1 max-w-xs text-[12.5px] leading-relaxed text-muted-foreground">
                बाईं तरफ़ लिखो और बनाओ दबाओ। दोनों मॉडल चुनोगे तो दोनों की तस्वीरें साथ-साथ दिखेंगी।
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-1.5">
                {PRESETS.map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    onClick={() => setPrompt(preset)}
                    className="max-w-[240px] truncate rounded-full border border-border/70 bg-card px-3 py-1.5 text-[12px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                  >
                    {preset}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            generations.map((generation) => (
              <GenerationBlock
                key={generation.id}
                generation={generation}
                onRegenerate={(provider) => void regenerate(generation.id, provider)}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border/70 bg-card p-4">
      <p className="mb-2.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      {children}
    </div>
  );
}

function GenerationBlock({
  generation,
  onRegenerate,
}: {
  generation: GenerationRequest;
  onRegenerate: (provider: ProviderName) => void;
}) {
  return (
    <div className="rounded-2xl border border-border/70 bg-card/60 p-4">
      <p className="mb-3 line-clamp-2 text-[12.5px] text-muted-foreground">{generation.prompt}</p>
      <div
        className={cn(
          'grid gap-3',
          generation.results.length > 1 ? 'sm:grid-cols-2' : 'sm:grid-cols-1',
        )}
      >
        {generation.results.map((result) => (
          <ModelResultCard
            key={result.id}
            result={result}
            onRegenerate={() => onRegenerate(result.provider)}
            regenerating={result.status === 'pending' || result.status === 'processing'}
          />
        ))}
      </div>
    </div>
  );
}
