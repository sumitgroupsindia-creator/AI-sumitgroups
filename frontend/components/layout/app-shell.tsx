'use client';

import { useEffect, useState, type ReactNode } from 'react';

import { ChatSidebar } from '@/components/layout/chat-sidebar';
import { TopNav } from '@/components/layout/top-nav';

/**
 * Nav across the top, thread rail down the left, work in the middle.
 *
 * The rail starts closed and is remembered per browser: someone who wants their history pinned
 * open should not have to reopen it on every visit, and someone who wants the composer centred
 * should not have to close it on every visit either.
 */
const SIDEBAR_STORAGE_KEY = 'sg-sidebar-open';

export function AppShell({ children }: { children: ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    try {
      setSidebarOpen(localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true');
    } catch {
      /* site data blocked — the rail simply starts closed */
    }
  }, []);

  const setOpen = (next: boolean) => {
    setSidebarOpen(next);
    try {
      localStorage.setItem(SIDEBAR_STORAGE_KEY, String(next));
    } catch {
      /* nothing to remember it with; the session still works */
    }
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      <TopNav onToggleSidebar={() => setOpen(!sidebarOpen)} />
      <div className="flex min-h-0 flex-1">
        <ChatSidebar open={sidebarOpen} onClose={() => setOpen(false)} />
        {/* The one scroller for ordinary pages. Chat and the image desk manage their own inner
            scrolling because they pin a composer to the bottom; everything else — settings, admin,
            pricing — is plain flow and simply scrolls here. This was `overflow-hidden`, which meant
            any page taller than the viewport had its lower half unreachable. */}
        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto scrollbar-thin">{children}</main>
      </div>
    </div>
  );
}
