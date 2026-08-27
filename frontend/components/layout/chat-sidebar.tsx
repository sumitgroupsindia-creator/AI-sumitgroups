'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Search, SquarePen, Trash2, X } from 'lucide-react';

import { ConversationList } from '@/features/chat/conversation-list';
import { useAuth } from '@/features/auth/auth-provider';
import { cn } from '@/lib/utils';
import * as chatService from '@/services/chat.service';

/**
 * The thread rail: start a new chat, find an old one, or clear them all.
 *
 * Collapsible rather than permanent. On a phone it is the whole screen when open and absent when
 * closed; on a desktop it takes its column back the moment it is dismissed, which matters because
 * the composer is centred and a rail that never leaves pushes it permanently off-centre.
 */
export function ChatSidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState('');
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const { user } = useAuth();
  const router = useRouter();

  const clearHistory = async () => {
    setClearing(true);
    try {
      // No bulk endpoint exists, so this is a fan-out of single deletes. `allSettled`, not `all`:
      // one thread failing to delete must not abandon the rest half-done.
      const conversations = await chatService.listConversations();
      await Promise.allSettled(conversations.map((c) => chatService.deleteConversation(c.id)));
      setReloadKey((k) => k + 1);
      router.push('/chat');
    } finally {
      setClearing(false);
      setConfirmingClear(false);
    }
  };

  return (
    <>
      {/* Scrim, phones only — on a desktop the rail shares the row rather than covering it. */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={onClose}
          aria-hidden
        />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-[280px] shrink-0 flex-col border-r border-border/60 bg-card transition-transform duration-200',
          'lg:static lg:z-auto lg:h-auto lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full lg:hidden',
        )}
      >
        <div className="flex items-center gap-2 p-3">
          <Link
            href="/chat"
            onClick={onClose}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            <SquarePen className="h-4 w-4" />
            नई चैट
          </Link>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            title="बंद करो"
          >
            <X className="h-4 w-4" />
            <span className="sr-only">Close sidebar</span>
          </button>
        </div>

        <div className="px-3 pb-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="चैट खोजो…"
              className="h-9 w-full rounded-lg border border-border/70 bg-background/60 pl-8 pr-3 text-[13px] outline-none transition-colors placeholder:text-muted-foreground focus:border-ring"
            />
          </div>
        </div>

        <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-2 pb-2">
          <ConversationList onNavigate={onClose} query={query} reloadKey={reloadKey} />
        </div>

        <div className="space-y-2 border-t border-border/60 p-3">
          <Link
            href="/pricing"
            onClick={onClose}
            className="block rounded-lg bg-primary/10 px-3 py-2.5 text-center transition-colors hover:bg-primary/15"
          >
            <span className="block text-[13px] font-medium text-primary">प्लान अपग्रेड करो</span>
            <span className="mt-0.5 block text-[11px] text-muted-foreground">
              ज़्यादा क्रेडिट, ज़्यादा तस्वीरें
            </span>
          </Link>

          {confirmingClear ? (
            <div className="flex gap-1.5">
              <button
                type="button"
                disabled={clearing}
                onClick={() => void clearHistory()}
                className="flex-1 rounded-lg bg-destructive px-2 py-2 text-[12px] font-medium text-destructive-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
              >
                {clearing ? 'हट रही है…' : 'हाँ, सब हटाओ'}
              </button>
              <button
                type="button"
                disabled={clearing}
                onClick={() => setConfirmingClear(false)}
                className="rounded-lg border border-border px-2.5 py-2 text-[12px] text-muted-foreground transition-colors hover:bg-accent"
              >
                रहने दो
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmingClear(true)}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border px-3 py-2 text-[12px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <Trash2 className="h-3.5 w-3.5" />
              सारी चैट हटाओ
            </button>
          )}

          {user && (
            <p className="truncate px-1 pt-1 text-[11px] text-muted-foreground" title={user.email}>
              {user.full_name || user.email}
            </p>
          )}
        </div>
      </aside>
    </>
  );
}
