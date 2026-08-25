'use client';

import { useState, type ReactNode } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  CreditCard,
  Images,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquarePlus,
  Settings,
  Sparkles,
  Tag,
  X,
} from 'lucide-react';

import { ConversationList } from '@/features/chat/conversation-list';
import { useAuth } from '@/features/auth/auth-provider';
import { useCredits } from '@/hooks/use-credits';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';

const NAV_ITEMS = [
  { href: '/images', label: 'Images', icon: Images },
  { href: '/pricing', label: 'Pricing', icon: Tag },
  { href: '/settings/usage', label: 'Usage & Credits', icon: CreditCard },
  { href: '/settings', label: 'Settings', icon: Settings },
];

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { user, logout } = useAuth();
  const { credits } = useCredits();
  const pathname = usePathname();

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden
        />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r bg-card transition-transform lg:static lg:translate-x-0',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex items-center justify-between px-4 py-4">
          <Link href="/chat" className="flex items-center gap-2 font-semibold">
            <Sparkles className="h-5 w-5" />
            <span>ai.sumitgroups</span>
          </Link>
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(false)}>
            <X className="h-4 w-4" />
            <span className="sr-only">Close menu</span>
          </Button>
        </div>

        <div className="px-3">
          <Button asChild className="w-full justify-start gap-2">
            <Link href="/chat" onClick={() => setMobileOpen(false)}>
              <MessageSquarePlus className="h-4 w-4" />
              New Chat
            </Link>
          </Button>
        </div>

        <div className="mt-4 flex-1 overflow-y-auto scrollbar-thin px-3">
          <p className="px-2 pb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Chat History
          </p>
          <ConversationList onNavigate={() => setMobileOpen(false)} />
        </div>

        <Separator />

        <nav className="space-y-1 p-3">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                  active ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-accent/60',
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
          {user?.is_admin && (
            <Link
              href="/admin"
              onClick={() => setMobileOpen(false)}
              className={cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                pathname.startsWith('/admin')
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground hover:bg-accent/60',
              )}
            >
              <LayoutDashboard className="h-4 w-4" />
              Admin
            </Link>
          )}
        </nav>

        <Separator />

        <div className="p-3">
          {credits && (
            <div className="mb-3 rounded-lg bg-muted/60 px-3 py-2 text-xs">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Chat credits</span>
                <span className="font-medium tabular-nums">{credits.chat_balance}</span>
              </div>
              <div className="mt-1 flex justify-between">
                <span className="text-muted-foreground">Image credits</span>
                <span className="font-medium tabular-nums">{credits.image_balance}</span>
              </div>
            </div>
          )}
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{user?.full_name || user?.email}</p>
              <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
            </div>
            <Button variant="ghost" size="icon" onClick={() => void logout()} title="Log out">
              <LogOut className="h-4 w-4" />
              <span className="sr-only">Log out</span>
            </Button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 border-b px-4 lg:hidden">
          <Button variant="ghost" size="icon" onClick={() => setMobileOpen(true)}>
            <Menu className="h-5 w-5" />
            <span className="sr-only">Open menu</span>
          </Button>
          <span className="font-semibold">ai.sumitgroups</span>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
