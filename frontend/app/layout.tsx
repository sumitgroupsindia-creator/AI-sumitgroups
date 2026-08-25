import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { AuthProvider } from '@/features/auth/auth-provider';
import './globals.css';

export const metadata: Metadata = {
  title: 'One Prompt. Multiple AI Models. | ai.sumitgroups.com',
  description:
    'Run one prompt through OpenAI and Google Gemini at the same time, then compare the results side by side.',
  metadataBase: new URL('https://ai.sumitgroups.com'),
  openGraph: {
    title: 'One Prompt. Multiple AI Models. Better Results.',
    description: 'Compare OpenAI and Gemini image generations side by side.',
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
