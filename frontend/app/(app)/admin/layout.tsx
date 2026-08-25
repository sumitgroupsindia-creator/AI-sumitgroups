'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { RequireAuth } from '@/features/auth/require-auth';
import { cn } from '@/lib/utils';

const TABS = [
  { href: '/admin', label: 'Overview' },
  { href: '/admin/users', label: 'Users' },
  { href: '/admin/plans', label: 'Plans' },
  { href: '/admin/models', label: 'Models' },
  { href: '/admin/usage', label: 'Failures' },
];

export default function AdminLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <RequireAuth adminOnly>
      <div className="mx-auto max-w-6xl px-4 py-8">
        <h1 className="text-2xl font-semibold tracking-tight">Admin</h1>
        <nav className="mt-6 flex flex-wrap gap-1 border-b">
          {TABS.map((tab) => (
            <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                '-mb-px border-b-2 px-4 py-2 text-sm transition-colors',
                pathname === tab.href
                  ? 'border-foreground font-medium'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              {tab.label}
            </Link>
          ))}
        </nav>
        <div className="py-8">{children}</div>
      </div>
    </RequireAuth>
  );
}
