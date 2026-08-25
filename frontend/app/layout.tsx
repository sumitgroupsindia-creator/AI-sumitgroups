import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { AuthProvider } from '@/features/auth/auth-provider';
import './globals.css';

export const metadata: Metadata = {
  title: 'One Prompt. Multiple AI Models. | ai.sumitgroups.com',
  description:
    'Run one prompt through two advanced AI models at the same time, then compare the results side by side.',
  metadataBase: new URL('https://ai.sumitgroups.com'),
  openGraph: {
    title: 'One Prompt. Multiple AI Models. Better Results.',
    description: 'Compare two AI image models side by side, from a single prompt.',
    url: 'https://ai.sumitgroups.com',
    siteName: 'ai.sumitgroups.com',
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
