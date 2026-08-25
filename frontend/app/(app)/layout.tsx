'use client';

import type { ReactNode } from 'react';

import { AppShell } from '@/components/layout/app-shell';
import { RequireAuth } from '@/features/auth/require-auth';
import { ModelBrandingProvider } from '@/features/branding/model-branding';

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <ModelBrandingProvider>
        <AppShell>{children}</AppShell>
      </ModelBrandingProvider>
    </RequireAuth>
  );
}
