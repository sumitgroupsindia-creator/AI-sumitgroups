import { API_BASE, apiFetch } from '@/lib/api-client';
import { getAccessToken } from '@/lib/auth-storage';
import type { Conversation, ConversationDetail, ProviderName } from '@/types/api';

export function listConversations(): Promise<Conversation[]> {
  return apiFetch<Conversation[]>('/conversations');
}

export function getConversation(id: string): Promise<ConversationDetail> {
  return apiFetch<ConversationDetail>(`/conversations/${id}`);
}

export function renameConversation(id: string, title: string): Promise<Conversation> {
  return apiFetch<Conversation>(`/conversations/${id}`, { method: 'PATCH', body: { title } });
}

export function deleteConversation(id: string): Promise<void> {
  return apiFetch<void>(`/conversations/${id}`, { method: 'DELETE', raw: true });
}

export interface StreamHandlers {
  onDelta: (text: string) => void;
  onDone: (conversationId: string) => void;
  onError: (message: string, code?: string) => void;
}

/**
 * Streams a chat completion over SSE. Returns an AbortController so the caller can implement
 * "Stop generating" — aborting closes the connection and the server stops mid-stream.
 */
export function streamChat(
  params: { conversationId?: string; message: string; provider: ProviderName },
  handlers: StreamHandlers,
): AbortController {
  const controller = new AbortController();

  void (async () => {
    try {
      const res = await fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}),
        },
        body: JSON.stringify({
          conversation_id: params.conversationId ?? null,
          message: params.message,
          provider: params.provider,
        }),
      });

      if (!res.ok || !res.body) {
        let message = 'The chat service is unavailable. Please retry.';
        try {
          const data = await res.json();
          if (data?.error) message = data.error;
        } catch {
          /* non-JSON error */
        }
        handlers.onError(message);
        return;
      }

      const conversationId = res.headers.get('X-Conversation-Id') ?? params.conversationId ?? '';
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE frames are separated by a blank line.
        const frames = buffer.split('\n\n');
        buffer = frames.pop() ?? '';

        for (const frame of frames) {
          const eventLine = frame.split('\n').find((l) => l.startsWith('event: '));
          const dataLine = frame.split('\n').find((l) => l.startsWith('data: '));
          if (!eventLine || !dataLine) continue;

          const event = eventLine.slice(7).trim();
          const payload = JSON.parse(dataLine.slice(6));

          if (event === 'delta') handlers.onDelta(payload.content);
          else if (event === 'error') handlers.onError(payload.message, payload.code);
          else if (event === 'done') handlers.onDone(payload.conversation_id || conversationId);
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        handlers.onError('Connection lost. Please retry.');
      }
    }
  })();

  return controller;
}
