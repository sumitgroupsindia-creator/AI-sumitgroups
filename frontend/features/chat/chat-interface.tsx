'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertCircle, RefreshCw, Send, Square } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ModelSelector } from '@/features/chat/model-selector';
import { useCredits } from '@/hooks/use-credits';
import * as chatService from '@/services/chat.service';
import { cn } from '@/lib/utils';
import type { Message, ProviderName } from '@/types/api';

interface ChatInterfaceProps {
  conversationId?: string;
  initialMessages?: Message[];
  initialProvider?: ProviderName;
}

interface PendingAssistant {
  content: string;
  error: string | null;
}

export function ChatInterface({ conversationId, initialMessages = [], initialProvider }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [pending, setPending] = useState<PendingAssistant | null>(null);
  const [input, setInput] = useState('');
  const [provider, setProvider] = useState<ProviderName>(initialProvider ?? 'openai');
  const [streaming, setStreaming] = useState(false);
  const [lastPrompt, setLastPrompt] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const { refresh: refreshCredits } = useCredits();

  useEffect(() => {
    setMessages(initialMessages);
  }, [initialMessages]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, pending]);

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || streaming) return;

      setLastPrompt(trimmed);
      setMessages((prev) => [
        ...prev,
        {
          id: `local-${Date.now()}`,
          role: 'user',
          content: trimmed,
          provider: null,
          model: null,
          error: null,
          created_at: new Date().toISOString(),
        },
      ]);
      setInput('');
      setPending({ content: '', error: null });
      setStreaming(true);

      abortRef.current = chatService.streamChat(
        { conversationId, message: trimmed, provider },
        {
          onDelta: (chunk) =>
            setPending((prev) => (prev ? { ...prev, content: prev.content + chunk } : { content: chunk, error: null })),
          onError: (message) => setPending((prev) => ({ content: prev?.content ?? '', error: message })),
          onDone: (returnedId) => {
            setStreaming(false);
            setPending((prev) => {
              if (prev && prev.content) {
                setMessages((msgs) => [
                  ...msgs,
                  {
                    id: `local-assistant-${Date.now()}`,
                    role: 'assistant',
                    content: prev.content,
                    provider,
                    model: null,
                    error: null,
                    created_at: new Date().toISOString(),
                  },
                ]);
                void refreshCredits();
                return null;
              }
              return prev; // keep the error card visible
            });
            if (!conversationId && returnedId) router.push(`/chat/${returnedId}`);
          },
        },
      );
    },
    [conversationId, provider, streaming, router, refreshCredits],
  );

  const stop = () => {
    abortRef.current?.abort();
    setStreaming(false);
    if (pending?.content) {
      setMessages((prev) => [
        ...prev,
        {
          id: `local-assistant-${Date.now()}`,
          role: 'assistant',
          content: pending.content,
          provider,
          model: null,
          error: null,
          created_at: new Date().toISOString(),
        },
      ]);
    }
    setPending(null);
  };

  const regenerate = () => {
    if (!lastPrompt) return;
    // Drop the previous assistant turn so the retry replaces it rather than appending.
    setMessages((prev) => {
      const copy = [...prev];
      while (copy.length && copy[copy.length - 1]?.role === 'assistant') copy.pop();
      while (copy.length && copy[copy.length - 1]?.role === 'user') copy.pop();
      return copy;
    });
    setPending(null);
    send(lastPrompt);
  };

  const isEmpty = messages.length === 0 && !pending;

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin">
        {isEmpty ? (
          <EmptyState onPick={(prompt) => send(prompt)} />
        ) : (
          <div className="mx-auto max-w-3xl space-y-6 px-4 py-8">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}

            {pending && (
              <div className="animate-fade-in">
                {pending.content && (
                  <div className="prose prose-sm dark:prose-invert max-w-none text-sm leading-relaxed">
                    <ReactMarkdown>{pending.content}</ReactMarkdown>
                  </div>
                )}
                {!pending.content && !pending.error && <TypingIndicator />}
                {pending.error && (
                  <div className="flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/5 p-4">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                    <div className="flex-1">
                      <p className="text-sm">{pending.error}</p>
                      <Button size="sm" variant="outline" className="mt-2 gap-2" onClick={regenerate}>
                        <RefreshCw className="h-3.5 w-3.5" />
                        Retry
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="border-t bg-background/95 backdrop-blur">
        <div className="mx-auto max-w-3xl px-4 py-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <ModelSelector value={provider} onChange={setProvider} disabled={streaming} />
            {!streaming && messages.length > 0 && lastPrompt && (
              <Button size="sm" variant="ghost" className="gap-2" onClick={regenerate}>
                <RefreshCw className="h-3.5 w-3.5" />
                Regenerate
              </Button>
            )}
          </div>

          <div className="relative">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              placeholder="Send a message, or describe an image to generate…"
              rows={1}
              className="max-h-48 resize-none pr-14"
              disabled={streaming}
            />
            <div className="absolute bottom-2 right-2">
              {streaming ? (
                <Button size="icon" variant="secondary" onClick={stop} title="Stop generating">
                  <Square className="h-3.5 w-3.5" />
                </Button>
              ) : (
                <Button size="icon" onClick={() => send(input)} disabled={!input.trim()} title="Send">
                  <Send className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>
          <p className="mt-2 text-center text-xs text-muted-foreground">
            Want to compare image models?{' '}
            <a href="/images" className="underline underline-offset-2">
              Generate with OpenAI and Gemini side by side
            </a>
            .
          </p>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';
  return (
    <div className={cn('animate-fade-in', isUser && 'flex justify-end')}>
      <div
        className={cn(
          isUser
            ? 'max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground'
            : 'prose prose-sm dark:prose-invert max-w-none text-sm leading-relaxed',
        )}
      >
        {isUser ? message.content : <ReactMarkdown>{message.content}</ReactMarkdown>}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 py-2" aria-label="Assistant is typing">
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

const STARTERS = [
  'Explain the difference between REST and GraphQL in simple terms',
  'Write a professional follow-up email after a client meeting',
  'Summarise the key risks of migrating a monolith to microservices',
  'Give me a 7-day workout plan for a beginner',
];

function EmptyState({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center px-4 text-center">
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">How can I help you today?</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Ask anything, or head to Images to run one prompt through two models at once.
      </p>
      <div className="mt-8 grid w-full gap-2 sm:grid-cols-2">
        {STARTERS.map((prompt) => (
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
