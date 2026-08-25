import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { streamChat } from '@/services/chat.service';
import type { ProviderName } from '@/types/api';

vi.mock('@/lib/auth-storage', () => ({ getAccessToken: () => 'test-token' }));

/** Builds a Response whose body streams the given chunks, mimicking a real SSE response. */
function sseResponse(chunks: string[], headers: Record<string, string> = {}) {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { 'X-Conversation-Id': 'conv-1', ...headers } });
}

const frame = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

/** Resolves once the handler set is finished (done or error followed by done). */
function collect() {
  const deltas: string[] = [];
  const tagged: { provider: string; text: string }[] = [];
  const errors: string[] = [];
  const errorProviders: (string | null)[] = [];
  const finishedProviders: string[] = [];
  let doneId: string | null = null;
  let resolve!: () => void;
  const finished = new Promise<void>((r) => (resolve = r));

  return {
    deltas,
    tagged,
    errors,
    errorProviders,
    finishedProviders,
    finished,
    get doneId() {
      return doneId;
    },
    handlers: {
      onDelta: (provider: ProviderName, text: string) => {
        deltas.push(text);
        tagged.push({ provider, text });
      },
      onProviderDone: (provider: ProviderName) => finishedProviders.push(provider),
      onError: (provider: ProviderName | null, message: string) => {
        errors.push(message);
        errorProviders.push(provider);
        resolve();
      },
      onDone: (id: string) => {
        doneId = id;
        resolve();
      },
    },
  };
}

describe('streamChat', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn()));
  afterEach(() => vi.unstubAllGlobals());

  it('emits each delta in order and reports the conversation id on done', async () => {
    vi.mocked(fetch).mockResolvedValue(
      sseResponse([
        frame('delta', { provider: 'openai', content: 'Hello' }),
        frame('delta', { provider: 'openai', content: ', world' }),
        frame('done', { conversation_id: 'conv-1' }),
      ]),
    );

    const c = collect();
    streamChat({ message: 'hi', providers: ['openai'] }, c.handlers);
    await c.finished;

    expect(c.deltas).toEqual(['Hello', ', world']);
    expect(c.doneId).toBe('conv-1');
    expect(c.errors).toEqual([]);
  });

  it('reassembles frames split across network chunk boundaries', async () => {
    // A frame arriving in two pieces must not be dropped or double-counted.
    vi.mocked(fetch).mockResolvedValue(
      sseResponse([
        'event: delta\ndata: {"provider":"openai","content":"par',
        'tial"}\n\n' + frame('done', { conversation_id: 'conv-1' }),
      ]),
    );

    const c = collect();
    streamChat({ message: 'hi', providers: ['openai'] }, c.handlers);
    await c.finished;

    expect(c.deltas).toEqual(['partial']);
  });

  it('surfaces a provider error event to the caller', async () => {
    vi.mocked(fetch).mockResolvedValue(
      sseResponse([
        frame('error', { provider: 'openai', message: 'The AI provider failed to respond. Please retry.', code: 'provider_error' }),
        frame('done', { conversation_id: 'conv-1' }),
      ]),
    );

    const c = collect();
    streamChat({ message: 'hi', providers: ['openai'] }, c.handlers);
    await c.finished;

    expect(c.errors[0]).toContain('failed to respond');
  });

  it('reports a friendly message when the request itself is rejected', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ error: 'Insufficient chat credits' }), { status: 402 }),
    );

    const c = collect();
    streamChat({ message: 'hi', providers: ['openai'] }, c.handlers);
    await c.finished;

    expect(c.errors).toEqual(['Insufficient chat credits']);
  });

  it('returns a controller that aborts the stream without reporting an error', async () => {
    vi.mocked(fetch).mockRejectedValue(Object.assign(new Error('aborted'), { name: 'AbortError' }));

    const c = collect();
    const controller = streamChat({ message: 'hi', providers: ['openai'] }, c.handlers);
    controller.abort();
    await new Promise((r) => setTimeout(r, 10));

    // Stopping generation is a user action, not a failure to report.
    expect(c.errors).toEqual([]);
    expect(controller.signal.aborted).toBe(true);
  });

  it('sends the slot keys, message and any attachment in the request body', async () => {
    vi.mocked(fetch).mockResolvedValue(sseResponse([frame('done', { conversation_id: 'conv-1' })]));

    const c = collect();
    streamChat(
      { conversationId: 'conv-9', message: 'hello', providers: ['gemini'], uploadFileId: 'up-1' },
      c.handlers,
    );
    await c.finished;

    const [, init] = vi.mocked(fetch).mock.calls[0]!;
    expect(JSON.parse(init!.body as string)).toEqual({
      conversation_id: 'conv-9',
      message: 'hello',
      providers: ['gemini'],
      upload_file_id: 'up-1',
    });
  });

  it('keeps two slots apart when both answer the same turn', async () => {
    // The whole point of the tagging: two models stream interleaved and must not be merged.
    vi.mocked(fetch).mockResolvedValue(
      sseResponse([
        frame('delta', { provider: 'openai', content: 'A1' }),
        frame('delta', { provider: 'gemini', content: 'B1' }),
        frame('delta', { provider: 'openai', content: 'A2' }),
        frame('provider_done', { provider: 'openai' }),
        frame('provider_done', { provider: 'gemini' }),
        frame('done', { conversation_id: 'conv-1' }),
      ]),
    );

    const c = collect();
    streamChat({ message: 'hi', providers: ['openai', 'gemini'] }, c.handlers);
    await c.finished;

    expect(c.tagged.filter((d) => d.provider === 'openai').map((d) => d.text)).toEqual(['A1', 'A2']);
    expect(c.tagged.filter((d) => d.provider === 'gemini').map((d) => d.text)).toEqual(['B1']);
    expect(c.finishedProviders).toEqual(['openai', 'gemini']);
  });

  it('reports a turn-wide failure with no provider attached', async () => {
    vi.mocked(fetch).mockResolvedValue(
      sseResponse([
        frame('error', { provider: null, message: 'Insufficient chat credits', code: 'insufficient_credits' }),
        frame('done', { conversation_id: 'conv-1' }),
      ]),
    );

    const c = collect();
    streamChat({ message: 'hi', providers: ['openai', 'gemini'] }, c.handlers);
    await c.finished;

    expect(c.errorProviders).toEqual([null]);
  });
});
