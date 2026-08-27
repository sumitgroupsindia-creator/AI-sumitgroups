'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ImageIcon, LayoutDashboard, LogOut, MessageSquare, PanelLeft, Tag } from 'lucide-react';

import { Brand } from '@/components/layout/brand';
import { ThemeToggle } from '@/features/theme/theme-provider';
import { useAuth } from '@/features/auth/auth-provider';
import { useCredits } from '@/hooks/use-credits';
import { cn, formatCredits } from '@/lib/utils';

/**
 * The destinations, and only the destinations that exist.
 *
 * Deliberately short. Every entry here is a feature with a working backend behind it — a nav that
 * advertises a tool the product does not have is a nav that teaches people not to trust it.
 */
const NAV = [
  { href: '/chat', label: 'Chat', icon: MessageSquare },
  { href: '/images', label: 'Image', icon: ImageIcon },
  { href: '/pricing', label: 'Pricing', icon: Tag },
];

export function TopNav({ onToggleSidebar }: { onToggleSidebar?: () => void }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { credits } = useCredits();

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b border-border/60 bg-background/80 px-3 backdrop-blur-xl">
      {onToggleSidebar && (
        <button
          type="button"
          onClick={onToggleSidebar}
          className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          title="चैट लिस्ट"
        >
          <PanelLeft className="h-[18px] w-[18px]" />
          <span className="sr-only">Toggle sidebar</span>
        </button>
      )}

      <Brand className="mr-1" />

      <nav className="ml-2 hidden items-center gap-1 md:flex">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                'flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm transition-colors',
                active
                  ? 'bg-accent font-medium text-foreground'
                  : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="ml-auto flex items-center gap-1.5">
        {credits && (
          <Link
            href="/settings/usage"
            title="1 credit = ₹1"
            className="hidden items-center gap-1.5 rounded-full border border-border/70 bg-card px-3 py-1.5 text-xs transition-colors hover:bg-accent sm:inline-flex"
          >
            <span className="text-muted-foreground">Credits</span>
            <span className="font-medium tabular-nums">{formatCredits(credits.balance)}</span>
          </Link>
        )}

        {user?.is_admin && (
          <Link
            href="/admin"
            title="Admin"
            className={cn(
              'inline-flex h-9 w-9 items-center justify-center rounded-full transition-colors hover:bg-accent',
              pathname.startsWith('/admin') ? 'text-foreground' : 'text-muted-foreground',
            )}
          >
            <LayoutDashboard className="h-[18px] w-[18px]" />
            <span className="sr-only">Admin</span>
          </Link>
        )}

        <ThemeToggle />

        {user ? (
          <button
            type="button"
            onClick={() => void logout()}
            title={user.full_name || user.email}
            className="inline-flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <LogOut className="h-[18px] w-[18px]" />
            <span className="sr-only">Log out</span>
          </button>
        ) : (
          <Link
            href="/login"
            className="rounded-full px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Login
          </Link>
        )}
      </div>
    </header>
  );
}
