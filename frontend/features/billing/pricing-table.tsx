'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Check, Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/features/auth/auth-provider';
import { useRazorpayCheckout } from '@/features/billing/use-razorpay-checkout';
import { formatCurrency, cn } from '@/lib/utils';
import * as billingService from '@/services/billing.service';
import type { Plan, Subscription } from '@/types/api';

export function PricingTable() {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const { user } = useAuth();
  const { checkout, pendingPlan, error } = useRazorpayCheckout();
  const router = useRouter();

  useEffect(() => {
    void billingService
      .listPlans()
      .then(setPlans)
      .catch(() => setPlans([]));
  }, []);

  useEffect(() => {
    if (!user) return;
    void billingService
      .getSubscription()
      .then(setSubscription)
      .catch(() => setSubscription(null));
  }, [user]);

  if (plans === null) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const handleSelect = (plan: Plan) => {
    if (!user) {
      router.push('/signup');
      return;
    }
    if (Number.parseFloat(plan.price) === 0) {
      router.push('/chat');
      return;
    }
    void checkout(plan.code, user.email, user.full_name ?? undefined);
  };

  return (
    <div>
      {error && <p className="mb-6 text-center text-sm text-destructive">{error}</p>}

      <div className="grid gap-6 md:grid-cols-3">
        {plans.map((plan) => {
          const price = Number.parseFloat(plan.price);
          const isCurrent = subscription?.plan.code === plan.code && subscription.status === 'active';
          const isHighlighted = plan.code === 'pro';

          return (
            <Card
              key={plan.id}
              className={cn('flex flex-col', isHighlighted && 'border-foreground/30 shadow-md')}
            >
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>{plan.name}</CardTitle>
                  {isHighlighted && <Badge>Most popular</Badge>}
                </div>
                <CardDescription>{plan.description}</CardDescription>
                <div className="pt-4">
                  <span className="text-3xl font-semibold tracking-tight">
                    {price === 0 ? 'Free' : formatCurrency(plan.price, plan.currency)}
                  </span>
                  {price > 0 && (
                    <span className="text-sm text-muted-foreground">/{plan.billing_interval}</span>
                  )}
                </div>
              </CardHeader>

              <CardContent className="flex flex-1 flex-col">
                <ul className="flex-1 space-y-2.5 text-sm">
                  <Feature>{plan.monthly_credits.toLocaleString()} credits per month (1 credit = ₹1)</Feature>
                  <Feature>Spend them on chat or on images, however you like</Feature>
                  <Feature>Compare Model 1 and Model 2 side by side</Feature>
                  <Feature>Upload photos up to {plan.max_upload_mb} MB</Feature>
                  {plan.priority_queue && <Feature>Priority generation queue</Feature>}
                </ul>

                <Button
                  className="mt-6 w-full gap-2"
                  variant={isHighlighted ? 'default' : 'outline'}
                  disabled={isCurrent || pendingPlan === plan.code}
                  onClick={() => handleSelect(plan)}
                >
                  {pendingPlan === plan.code && <Loader2 className="h-4 w-4 animate-spin" />}
                  {isCurrent ? 'Current plan' : price === 0 ? 'Get started' : `Upgrade to ${plan.name}`}
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function Feature({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2">
      <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
      <span>{children}</span>
    </li>
  );
}
