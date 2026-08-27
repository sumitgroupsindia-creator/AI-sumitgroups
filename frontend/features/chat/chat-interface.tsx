'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertCircle, ImageIcon, Loader2, RefreshCw } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

import { Button } from '@/components/ui/button';
import { AttachedImage } from '@/features/composer/attached-image';
import { ACCEPTED_TYPES, ComposerChip, PromptBox } from '@/features/composer/prompt-box';
import { providersFor } from '@/features/composer/slots';
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
    if (!ACCEPTED_TYPES.includes(file.type)) {
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

  const composer = (
    <PromptBox
      value={input}
      onChange={setInput}
      onSubmit={() => send(input)}
      onStop={stop}
      busy={busy}
      mode={mode}
      onModeChange={setMode}
      selection={selection}
      onSelectionChange={setSelection}
      attachment={attachment}
      onPickFile={pickFile}
      onClearAttachment={clearAttachment}
    />
  );

  // Empty threads centre the composer under a heading, the way a blank page invites a first line.
  // Once there is something to read, it moves to the bottom and the thread takes the room — the
  // same box, moved, rather than two different composers to keep in step.
  if (isEmpty) {
    return (
      <div className="aurora flex h-full flex-col overflow-y-auto scrollbar-thin">
        <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-4 py-10">
          <div className="mb-7 text-center">
            <h1 className="text-[28px] font-semibold tracking-tight sm:text-[34px]">
              {HEADINGS[mode].title}
            </h1>
            <p className="mx-auto mt-2.5 max-w-lg text-[13.5px] leading-relaxed text-muted-foreground">
              {HEADINGS[mode].subtitle}
            </p>
          </div>

          {composer}

          <div className="mt-5 flex flex-wrap justify-center gap-2">
            <ComposerChip
              label="तस्वीर बनाओ"
              icon={ImageIcon}
              active={mode === 'image'}
              onClick={() => setMode(mode === 'image' ? 'chat' : 'image')}
            />
            {STARTERS[mode].map((prompt) => (
              <ComposerChip key={prompt} label={prompt} onClick={() => send(prompt)} />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin">
        <div className="mx-auto max-w-3xl space-y-6 px-4 py-8">
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
            <div className="flex items-start gap-3 rounded-xl border border-destructive/40 bg-destructive/5 p-4">
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
      </div>

      <div className="shrink-0 border-t border-border/60 bg-background/80 px-4 py-3 backdrop-blur-xl">
        {composer}
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
