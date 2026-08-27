'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Check, Pencil, Trash2, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import * as chatService from '@/services/chat.service';
import { cn } from '@/lib/utils';
import type { Conversation } from '@/types/api';

/**
 * Buckets a thread by how long ago it was last touched.
 *
 * Flat lists stop being navigable at about thirty rows — every title looks equally recent, so
 * finding this morning's thread means reading all of them. The boundaries are the ones people
 * actually reason in: today, yesterday, this week, before that.
 */
function bucketOf(iso: string): string {
  const then = new Date(iso);
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);

  const days = Math.floor((startOfToday.getTime() - then.getTime()) / 86_400_000);
  if (days < 0) return 'आज';
  if (days === 0) return 'कल';
  if (days < 7) return 'पिछले 7 दिन';
  if (days < 30) return 'पिछले 30 दिन';
  return 'उससे पहले';
}

const BUCKET_ORDER = ['आज', 'कल', 'पिछले 7 दिन', 'पिछले 30 दिन', 'उससे पहले'];

export function ConversationList({
  onNavigate,
  query = '',
  reloadKey = 0,
}: {
  onNavigate?: () => void;
  /** Filters by title. Empty shows everything. */
  query?: string;
  /** Bump to force a reload — used after a bulk delete elsewhere in the sidebar. */
  reloadKey?: number;
}) {
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
  }, [load, pathname, reloadKey]);

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

  // Grouped once per change, not per render: the buckets are derived from every row's timestamp.
  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matching = (conversations ?? []).filter(
      (c) => !needle || c.title.toLowerCase().includes(needle),
    );

    const byBucket = new Map<string, Conversation[]>();
    for (const conversation of matching) {
      const bucket = bucketOf(conversation.updated_at || conversation.created_at);
      const existing = byBucket.get(bucket);
      if (existing) existing.push(conversation);
      else byBucket.set(bucket, [conversation]);
    }
    return BUCKET_ORDER.filter((b) => byBucket.has(b)).map((b) => [b, byBucket.get(b)!] as const);
  }, [conversations, query]);

  if (conversations === null) {
    return (
      <div className="space-y-2 px-1">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    );
  }

  if (conversations.length === 0) {
    return <p className="px-3 py-4 text-sm text-muted-foreground">अभी कोई चैट नहीं है।</p>;
  }

  if (groups.length === 0) {
    return <p className="px-3 py-4 text-sm text-muted-foreground">कुछ नहीं मिला।</p>;
  }

  return (
    <div className="space-y-4">
      {groups.map(([bucket, items]) => (
        <div key={bucket}>
          <p className="px-3 pb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground/80">
            {bucket}
          </p>
          <ul className="space-y-0.5">
            {items.map((conversation) => {
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
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={() => void handleRename(conversation.id)}
                      >
                        <Check className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={() => setEditingId(null)}
                      >
                        <X className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ) : (
                    <div
                      className={cn(
                        'flex items-center rounded-lg pr-1 transition-colors',
                        active ? 'bg-accent' : 'hover:bg-accent/60',
                      )}
                    >
                      <Link
                        href={`/chat/${conversation.id}`}
                        onClick={onNavigate}
                        className="min-w-0 flex-1 truncate px-3 py-2 text-[13px]"
                        title={conversation.title}
                      >
                        {conversation.title}
                      </Link>
                      <div className="flex shrink-0 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-7 w-7"
                          onClick={() => {
                            setEditingId(conversation.id);
                            setDraftTitle(conversation.title);
                          }}
                          title="नाम बदलो"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-7 w-7 text-destructive"
                          onClick={() => void handleDelete(conversation.id)}
                          title="हटाओ"
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
        </div>
      ))}
    </div>
  );
}
