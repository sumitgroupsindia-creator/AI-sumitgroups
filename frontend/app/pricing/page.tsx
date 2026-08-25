'use client';

import Link from 'next/link';
import { Sparkles } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { PricingTable } from '@/features/billing/pricing-table';
import { useAuth } from '@/features/auth/auth-provider';

export default function PricingPage() {
  const { user } = useAuth();

  return (
    <div className="min-h-screen">
      <header className="border-b">
        <div className="container flex h-16 items-center justify-between">
          <Link href="/" className="flex items-center gap-2 font-semibold">
            <Sparkles className="h-5 w-5" />
            ai.sumitgroups
          </Link>
          <Button asChild variant="ghost" size="sm">
            <Link href={user ? '/chat' : '/login'}>{user ? 'Open app' : 'Sign in'}</Link>
          </Button>
        </div>
      </header>

      <main className="container py-16">
        <div className="mx-auto max-w-2xl text-center">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Simple, credit-based pricing</h1>
          <p className="mt-3 text-muted-foreground">
            Every plan runs both models on a single prompt. Start free and upgrade when you need more.
          </p>
        </div>

        <div className="mt-12">
          <PricingTable />
        </div>

        <p className="mt-10 text-center text-sm text-muted-foreground">
          Prices in INR. Payments handled securely by Razorpay — we never see your card details.
        </p>
      </main>
    </div>
  );
}
