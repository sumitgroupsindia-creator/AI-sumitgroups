'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api-client';
import { formatCurrency, formatDate } from '@/lib/utils';
import * as billingService from '@/services/billing.service';
import type { Subscription } from '@/types/api';

export default function SubscriptionSettingsPage() {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    billingService
      .getSubscription()
      .then(setSubscription)
      .catch(() => setSubscription(null))
      .finally(() => setLoading(false));

  useEffect(() => {
    void load();
  }, []);

  const cancel = async () => {
    setCancelling(true);
    setError(null);
    try {
      setSubscription(await billingService.cancelSubscription());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not cancel your subscription.');
    } finally {
      setCancelling(false);
    }
  };

  if (loading) return <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />;

  if (!subscription) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>No subscription</CardTitle>
          <CardDescription>Choose a plan to unlock higher limits.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild>
            <Link href="/pricing">View plans</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  const isPaid = Number.parseFloat(subscription.plan.price) > 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle>{subscription.plan.name}</CardTitle>
            <CardDescription>
              {isPaid
                ? `${formatCurrency(subscription.plan.price, subscription.plan.currency)} / ${subscription.plan.billing_interval}`
                : 'Free plan'}
            </CardDescription>
          </div>
          <Badge variant={subscription.status === 'active' ? 'success' : 'secondary'}>{subscription.status}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Monthly chat credits</dt>
            <dd className="font-medium tabular-nums">{subscription.plan.monthly_chat_credits}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Monthly image credits</dt>
            <dd className="font-medium tabular-nums">{subscription.plan.monthly_image_credits}</dd>
          </div>
          {subscription.current_period_end && (
            <div>
              <dt className="text-muted-foreground">
                {subscription.cancel_at_period_end ? 'Access ends' : 'Renews on'}
              </dt>
              <dd className="font-medium">{formatDate(subscription.current_period_end)}</dd>
            </div>
          )}
          <div>
            <dt className="text-muted-foreground">Max upload size</dt>
            <dd className="font-medium">{subscription.plan.max_upload_mb} MB</dd>
          </div>
        </dl>

        {subscription.cancel_at_period_end && (
          <p className="rounded-md bg-muted p-3 text-sm text-muted-foreground">
            Your subscription is set to cancel at the end of the current period. You keep full access until then.
          </p>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex gap-3">
          <Button asChild variant="outline">
            <Link href="/pricing">Change plan</Link>
          </Button>
          {isPaid && subscription.status === 'active' && !subscription.cancel_at_period_end && (
            <Button variant="ghost" className="gap-2 text-destructive" onClick={() => void cancel()} disabled={cancelling}>
              {cancelling && <Loader2 className="h-4 w-4 animate-spin" />}
              Cancel subscription
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
