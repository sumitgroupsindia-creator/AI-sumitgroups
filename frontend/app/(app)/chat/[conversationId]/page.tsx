'use client';

import { use, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';

import { ChatInterface } from '@/features/chat/chat-interface';
import * as chatService from '@/services/chat.service';
import type { ConversationDetail } from '@/types/api';

export default function ConversationPage({ params }: { params: Promise<{ conversationId: string }> }) {
  const { conversationId } = use(params);
  const [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const [notFound, setNotFound] = useState(false);
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    void chatService
      .getConversation(conversationId)
      .then((data) => !cancelled && setConversation(data))
      .catch(() => !cancelled && setNotFound(true));
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  useEffect(() => {
    if (notFound) router.replace('/chat');
  }, [notFound, router]);

  if (!conversation) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <ChatInterface
      conversationId={conversation.id}
      initialMessages={conversation.messages}
      initialProvider={conversation.provider}
    />
  );
}
