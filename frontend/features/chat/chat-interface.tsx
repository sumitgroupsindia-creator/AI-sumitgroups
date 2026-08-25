'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertCircle, Loader2, Paperclip, RefreshCw, Send, Square, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { AttachedImage } from '@/features/composer/attached-image';
import { ModeToggle } from '@/features/composer/mode-toggle';
import { SlotSelector, providersFor } from '@/features/composer/slot-selector';
import { useModelLabel, useModelLabels } from '@/features/branding/model-branding';
import { ModelResultCard } from '@/features/images/model-result-card';
import { useCredits } from '@/hooks/use-credits';
import { useGenerationsPolling } from '@/hooks/use-generations-polling';
import { HEADINGS, STARTERS } from '@/lib/starters';
import { cn } from '@/lib/utils';
import * as chatService from '@/services/chat.service';
import * as imageService from '@/services/image.service';
import type {
  ComposerMode,
  GenerationRequest,
  Message,
  ModelSelection,
  ProviderName,
} from '@/types/api';

interface ChatInterfaceProps {
  conversationId?: string;
  initialMessages?: Message[];
  initialGenerations?: GenerationRequest[];
}

interface LiveAnswer {
  content: string;
  error: string | null;
  done: boolean;
}

/** One block in the thread. Chat replies and generated images share the same timeline. */
type Turn =
  | { kind: 'user'; key: string; at: string; content: string; uploadFileId: string | null }
  | {
      kind: 'answers';
      key: string;
      at: string;
      answers: { provider: ProviderName; content: string; error: string | null; done: boolean }[];
    }
  | { kind: 'generation'; key: string; at: string; generation: GenerationRequest };

// Stable identities: fresh literals would change every render and re-trigger the sync effects.
const NO_MESSAGES: Message[] = [];
const NO_GENERATIONS: GenerationRequest[] = [];

const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp'];

/**
 * Rebuilds the thread from stored state.
 *
 * Consecutive assistant rows belong to the same turn — that is how two model slots answering one
 * question are stored — so they are grouped rather than stacked, and generations are woven in by
 * time so a picture made mid-conversation sits where it was made.
 */
function buildTurns(messages: Message[], generations: GenerationRequest[]): Turn[] {
  const turns: Turn[] = [];

  for (const message of messages) {
    if (message.role === 'user') {
      turns.push({
        kind: 'user',
        key: message.id,
        at: message.created_at,
        content: message.content,
        uploadFileId: message.upload_file_id,
      });
      continue;
    }
    if (message.role !== 'assistant') continue;

    const last = turns[turns.length - 1];
    const answer = {
      provider: (message.provider ?? 'openai') as ProviderName,
      content: message.content,
      error: message.error,
      done: true,
    };
    if (last?.kind === 'answers') last.answers.push(answer);
    else turns.push({ kind: 'answers', key: message.id, at: message.created_at, answers: [answer] });
  }

  for (const generation of generations) {
    turns.push({
      kind: 'generation',
      key: generation.id,
      at: generation.created_at,
      generation,
    });
  }

  return turns.sort((a, b) => a.at.localeCompare(b.at));
}

export function ChatInterface({
  conversationId,
  initialMessages = NO_MESSAGES,
  initialGenerations = NO_GENERATIONS,
}: ChatInterfaceProps) {
  const knownProviders = Object.keys(useModelLabels()) as ProviderName[];
  const labelFor = useModelLabel();
  const router = useRouter();
  const { refresh: refreshCredits } = useCredits();

  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const { generations, add: addGeneration } = useGenerationsPolling(initialGenerations);

  const [mode, setMode] = useState<ComposerMode>('chat');
  const [selection, setSelection] = useState<ModelSelection>(knownProviders[0] ?? 'openai');
  const [input, setInput] = useState('');
  const [attachment, setAttachment] = useState<{ file: File; previewUrl: string } | null>(null);

  const [live, setLive] = useState<Record<string, LiveAnswer> | null>(null);
  const [pendingUser, setPendingUser] = useState<{ content: string; previewUrl: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [turnError, setTurnError] = useState<string | null>(null);
  const [lastPrompt, setLastPrompt] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [activeConversationId, setActiveConversationId] = useState(conversationId);

  useEffect(() => {
    setMessages(initialMessages);
    setActiveConversationId(conversationId);
    setLive(null);
    setPendingUser(null);
    setTurnError(null);
    setLastPrompt(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed on the conversation, not array identity
  }, [conversationId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, live, generations, pendingUser]);

  // Revoke the object URL when the attachment is replaced or cleared, not on every render.
  useEffect(() => {
    const url = attachment?.previewUrl;
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [attachment?.previewUrl]);

  const providers = useMemo(
    () => providersFor(selection, knownProviders),
    [selection, knownProviders],
  );

  const turns = useMemo(() => buildTurns(messages, generations), [messages, generations]);
  const isEmpty = turns.length === 0 && !pendingUser && !live;

  const pickFile = (file: File | undefined) => {
    if (!file) return;
    if (!ACCEPTED.includes(file.type)) {
      setTurnError('सिर्फ़ JPG, PNG या WEBP तस्वीर लगाई जा सकती है।');
      return;
    }
    setTurnError(null);
    setAttachment({ file, previewUrl: URL.createObjectURL(file) });
  };

  const clearAttachment = () => {
    setAttachment(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const ensureConversation = useCallback(
    async (seedTitle: string): Promise<string> => {
      if (activeConversationId) return activeConversationId;
      const created = await chatService.createConversation(seedTitle.slice(0, 60), providers[0]!);
      setActiveConversationId(created.id);
      return created.id;
    },
    [activeConversationId, providers],
  );

  const sendChat = useCallback(
    async (text: string, file: File | null, previewUrl: string | null) => {
      let uploadFileId: string | null = null;
      if (file) {
        try {
          uploadFileId = (await imageService.uploadImage(file)).id;
        } catch {
          setBusy(false);
          setPendingUser(null);
          setTurnError('तस्वीर अपलोड नहीं हो पाई। दोबारा कोशिश करो।');
          return;
        }
      }

      setLive(Object.fromEntries(providers.map((p) => [p, { content: '', error: null, done: false }])));

      abortRef.current = chatService.streamChat(
        { conversationId: activeConversationId, message: text, providers, uploadFileId },
        {
          onDelta: (provider, chunk) =>
            setLive((prev) => ({
              ...prev,
              [provider]: {
                content: (prev?.[provider]?.content ?? '') + chunk,
                error: prev?.[provider]?.error ?? null,
                done: false,
              },
            })),
          onProviderDone: (provider) =>
            setLive((prev) =>
              prev ? { ...prev, [provider]: { ...prev[provider]!, done: true } } : prev,
            ),
          onError: (provider, message) => {
            if (provider === null) {
              setTurnError(message);
              return;
            }
            setLive((prev) =>
              prev
                ? { ...prev, [provider]: { content: prev[provider]?.content ?? '', error: message, done: true } }
                : prev,
            );
          },
          onDone: (returnedId) => {
            setBusy(false);
            setLive((current) => {
              if (!current) return null;
              const now = new Date().toISOString();
              setMessages((msgs) => [
                ...msgs,
                {
                  id: `local-user-${Date.now()}`,
                  role: 'user',
                  content: text,
                  provider: null,
                  error: null,
                  upload_file_id: uploadFileId,
                  created_at: now,
                },
                ...Object.entries(current)
                  .filter(([, answer]) => answer.content)
                  .map(([provider, answer], index) => ({
                    id: `local-assistant-${Date.now()}-${index}`,
                    role: 'assistant' as const,
                    content: answer.content,
                    provider,
                    error: answer.error,
                    upload_file_id: null,
                    created_at: now,
                  })),
              ]);
              return null;
            });
            setPendingUser(null);
            void refreshCredits();
            if (!activeConversationId && returnedId) {
              setActiveConversationId(returnedId);
              router.push(`/chat/${returnedId}`);
            }
          },
        },
      );
      void previewUrl;
    },
    [activeConversationId, providers, refreshCredits, router],
  );

  const sendImage = useCallback(
    async (text: string, file: File | null) => {
      try {
        const conversation = await ensureConversation(text);
        const created = file
          ? await imageService.generateWithUpload(file, text, providers, conversation)
          : await imageService.generateImages(text, providers, undefined, conversation);
        addGeneration(created);
        setPendingUser(null);
        void refreshCredits();
        if (!conversationId) router.push(`/chat/${conversation}`);
      } catch (err) {
        setTurnError(
          err instanceof Error && err.message ? err.message : 'तस्वीर नहीं बन पाई। दोबारा कोशिश करो।',
        );
        setPendingUser(null);
      } finally {
        setBusy(false);
      }
    },
    [addGeneration, conversationId, ensureConversation, providers, refreshCredits, router],
  );

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;

      const file = attachment?.file ?? null;
      const previewUrl = attachment?.previewUrl ?? null;

      setLastPrompt(trimmed);
      setTurnError(null);
      setInput('');
      setBusy(true);
      setPendingUser({ content: trimmed, previewUrl });
      clearAttachment();

      if (mode === 'image') void sendImage(trimmed, file);
      else void sendChat(trimmed, file, previewUrl);
    },
    [attachment, busy, mode, sendChat, sendImage],
  );

  const stop = () => {
    abortRef.current?.abort();
    setBusy(false);
    setLive(null);
    setPendingUser(null);
  };

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin">
        {isEmpty ? (
          <EmptyState mode={mode} onModeChange={setMode} onPick={send} />
        ) : (
          <div className="mx-auto max-w-4xl space-y-6 px-4 py-8">
            {turns.map((turn) => (
              <TurnBlock key={turn.key} turn={turn} labelFor={labelFor} />
            ))}

            {pendingUser && (
              <UserBubble content={pendingUser.content} previewUrl={pendingUser.previewUrl} />
            )}

            {live && (
              <AnswerColumns
                answers={Object.entries(live).map(([provider, answer]) => ({
                  provider: provider as ProviderName,
                  ...answer,
                }))}
                labelFor={labelFor}
              />
            )}

            {busy && mode === 'image' && !live && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                तस्वीर बन रही है…
              </div>
            )}

            {turnError && (
              <div className="flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/5 p-4">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                <div className="flex-1">
                  <p className="text-sm">{turnError}</p>
                  {lastPrompt && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-2 gap-2"
                      onClick={() => send(lastPrompt)}
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      दोबारा भेजो
                    </Button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="border-t bg-background/95 backdrop-blur">
        <div className="mx-auto max-w-4xl px-4 py-4">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            {/* On a blank thread the toggle sits above the heading instead, where the eye already is. */}
            {!isEmpty && <ModeToggle value={mode} onChange={setMode} size="sm" />}
            <SlotSelector value={selection} onChange={setSelection} disabled={busy} />
          </div>

          {attachment && (
            <div className="mb-2 flex items-center gap-2 rounded-lg border p-2">
              {/* eslint-disable-next-line @next/next/no-img-element -- blob: URL */}
              <img src={attachment.previewUrl} alt="" className="h-12 w-12 rounded object-cover" />
              <span className="flex-1 truncate text-xs text-muted-foreground">
                {attachment.file.name}
              </span>
              <Button size="icon" variant="ghost" className="h-7 w-7" onClick={clearAttachment}>
                <X className="h-3.5 w-3.5" />
                <span className="sr-only">तस्वीर हटाओ</span>
              </Button>
            </div>
          )}

          <div className="relative">
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED.join(',')}
              className="hidden"
              onChange={(e) => pickFile(e.target.files?.[0])}
            />
            <Button
              size="icon"
              variant="ghost"
              className="absolute bottom-1.5 left-1.5 h-8 w-8"
              disabled={busy}
              onClick={() => fileInputRef.current?.click()}
              title="तस्वीर लगाओ"
            >
              <Paperclip className="h-4 w-4" />
              <span className="sr-only">तस्वीर लगाओ</span>
            </Button>
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              placeholder={
                mode === 'image'
                  ? 'कैसी तस्वीर चाहिए, लिखो…'
                  : 'क्या लिखवाना है? तस्वीर भी लगा सकते हो…'
              }
              rows={1}
              className="max-h-48 resize-none pl-12 pr-14"
              disabled={busy}
            />
            <div className="absolute bottom-1.5 right-2">
              {busy ? (
                <Button size="icon" variant="secondary" onClick={stop} title="रोको">
                  <Square className="h-3.5 w-3.5" />
                </Button>
              ) : (
                <Button size="icon" onClick={() => send(input)} disabled={!input.trim()} title="भेजो">
                  <Send className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function TurnBlock({
  turn,
  labelFor,
}: {
  turn: Turn;
  labelFor: (provider: string) => { slot: string; tier: string; description: string };
}) {
  if (turn.kind === 'user') {
    return <UserBubble content={turn.content} uploadFileId={turn.uploadFileId} />;
  }
  if (turn.kind === 'answers') {
    return <AnswerColumns answers={turn.answers} labelFor={labelFor} />;
  }
  return (
    <div className="space-y-3">
      <UserBubble content={turn.generation.prompt} uploadFileId={turn.generation.upload_file_id} />
      <div
        className={cn(
          'grid gap-4',
          turn.generation.results.length > 1 ? 'sm:grid-cols-2' : 'sm:grid-cols-1',
        )}
      >
        {turn.generation.results.map((result) => (
          <ModelResultCard key={result.id} result={result} onRegenerate={() => {}} regenerating={false} />
        ))}
      </div>
    </div>
  );
}

function UserBubble({
  content,
  uploadFileId,
  previewUrl,
}: {
  content: string;
  uploadFileId?: string | null;
  previewUrl?: string | null;
}) {
  return (
    <div className="flex animate-fade-in flex-col items-end gap-2">
      {previewUrl ? (
        // eslint-disable-next-line @next/next/no-img-element -- blob: URL
        <img src={previewUrl} alt="" className="h-20 w-20 rounded-lg object-cover" />
      ) : uploadFileId ? (
        <AttachedImage uploadFileId={uploadFileId} />
      ) : null}
      <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">
        {content}
      </div>
    </div>
  );
}

function AnswerColumns({
  answers,
  labelFor,
}: {
  answers: { provider: ProviderName; content: string; error: string | null; done: boolean }[];
  labelFor: (provider: string) => { slot: string; tier: string; description: string };
}) {
  return (
    <div className={cn('grid animate-fade-in gap-4', answers.length > 1 && 'sm:grid-cols-2')}>
      {answers.map((answer) => (
        <div key={answer.provider} className={cn(answers.length > 1 && 'rounded-lg border p-4')}>
          {answers.length > 1 && (
            <p className="mb-2 text-xs font-medium text-muted-foreground">
              {labelFor(answer.provider).slot} · {labelFor(answer.provider).tier}
            </p>
          )}
          {answer.content ? (
            <div className="prose prose-sm dark:prose-invert max-w-none text-sm leading-relaxed">
              <ReactMarkdown>{answer.content}</ReactMarkdown>
            </div>
          ) : answer.error ? null : (
            <TypingIndicator />
          )}
          {answer.error && (
            <p className="mt-2 flex items-start gap-1.5 text-xs text-destructive">
              <AlertCircle className="mt-0.5 h-3 w-3 shrink-0" />
              {answer.error}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 py-2" aria-label="जवाब लिखा जा रहा है">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground/50"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  );
}

function EmptyState({
  mode,
  onModeChange,
  onPick,
}: {
  mode: ComposerMode;
  onModeChange: (mode: ComposerMode) => void;
  onPick: (prompt: string) => void;
}) {
  const heading = HEADINGS[mode];
  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center px-4 text-center">
      <ModeToggle value={mode} onChange={onModeChange} />
      <h1 className="mt-6 text-2xl font-semibold tracking-tight sm:text-3xl">{heading.title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{heading.subtitle}</p>
      <div className="mt-8 grid w-full gap-2 sm:grid-cols-2">
        {STARTERS[mode].map((prompt) => (
          <button
            key={prompt}
            onClick={() => onPick(prompt)}
            className="rounded-lg border p-3 text-left text-sm transition-colors hover:bg-accent"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}
