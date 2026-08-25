'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Check, Pencil, Trash2, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import * as chatService from '@/services/chat.service';
import { cn } from '@/lib/utils';
import type { Conversation } from '@/types/api';

export function ConversationList({ onNavigate }: { onNavigate?: () => void }) {
  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const pathname = usePathname();
  const router = useRouter();

  const load = useCallback(async () => {
    try {
      setConversations(await chatService.listConversations());
    } catch {
      setConversations([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, pathname]);

  const handleRename = async (id: string) => {
    const title = draftTitle.trim();
    if (!title) return;
    await chatService.renameConversation(id, title);
    setEditingId(null);
    await load();
  };

  const handleDelete = async (id: string) => {
    await chatService.deleteConversation(id);
    if (pathname === `/chat/${id}`) router.push('/chat');
    await load();
  };

  if (conversations === null) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    );
  }

  if (conversations.length === 0) {
    return <p className="px-2 py-4 text-sm text-muted-foreground">No conversations yet.</p>;
  }

  return (
    <ul className="space-y-1">
      {conversations.map((conversation) => {
        const active = pathname === `/chat/${conversation.id}`;
        const isEditing = editingId === conversation.id;

        return (
          <li key={conversation.id} className="group relative">
            {isEditing ? (
              <div className="flex items-center gap-1 px-1">
                <Input
                  value={draftTitle}
                  onChange={(e) => setDraftTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void handleRename(conversation.id);
                    if (e.key === 'Escape') setEditingId(null);
                  }}
                  className="h-8 text-sm"
                  autoFocus
                />
                <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => void handleRename(conversation.id)}>
                  <Check className="h-3.5 w-3.5" />
                </Button>
                <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => setEditingId(null)}>
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            ) : (
              <div
                className={cn(
                  'flex items-center rounded-md pr-1 transition-colors',
                  active ? 'bg-accent' : 'hover:bg-accent/60',
                )}
              >
                <Link
                  href={`/chat/${conversation.id}`}
                  onClick={onNavigate}
                  className="min-w-0 flex-1 truncate px-3 py-2 text-sm"
                  title={conversation.title}
                >
                  {conversation.title}
                </Link>
                <div className="flex shrink-0 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7"
                    onClick={() => {
                      setEditingId(conversation.id);
                      setDraftTitle(conversation.title);
                    }}
                    title="Rename"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7 text-destructive"
                    onClick={() => void handleDelete(conversation.id)}
                    title="Delete"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
