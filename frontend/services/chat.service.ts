import { API_BASE, apiFetch } from '@/lib/api-client';
import { getAccessToken } from '@/lib/auth-storage';
import type { Conversation, ConversationDetail, ProviderName } from '@/types/api';

export function createConversation(title: string, provider: ProviderName = 'openai'): Promise<Conversation> {
  return apiFetch<Conversation>('/conversations', { method: 'POST', body: { title, provider } });
}

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
  /** Every delta is tagged, because two slots can be answering the same turn at once. */
  onDelta: (provider: ProviderName, text: string) => void;
  onProviderDone: (provider: ProviderName) => void;
  onDone: (conversationId: string) => void;
  /** `provider` is null when the failure was for the whole turn, e.g. not enough credits. */
  onError: (provider: ProviderName | null, message: string, code?: string) => void;
}

/**
 * Streams a chat completion over SSE. Returns an AbortController so the caller can implement
 * "Stop generating" — aborting closes the connection and the server stops mid-stream.
 */
export function streamChat(
  params: {
    conversationId?: string;
    message: string;
    providers: ProviderName[];
    uploadFileId?: string | null;
  },
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
          providers: params.providers,
          upload_file_id: params.uploadFileId ?? null,
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
        handlers.onError(null, message);
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

          if (event === 'delta') handlers.onDelta(payload.provider, payload.content);
          else if (event === 'provider_done') handlers.onProviderDone(payload.provider);
          else if (event === 'error') handlers.onError(payload.provider ?? null, payload.message, payload.code);
          else if (event === 'done') handlers.onDone(payload.conversation_id || conversationId);
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        handlers.onError(null, 'Connection lost. Please retry.');
      }
    }
  })();

  return controller;
}
