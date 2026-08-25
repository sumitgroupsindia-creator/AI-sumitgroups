'use client';

import { useCallback, useState } from 'react';

import { ApiError } from '@/lib/api-client';
import * as billingService from '@/services/billing.service';

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => { open: () => void };
  }
}

const RAZORPAY_SCRIPT = 'https://checkout.razorpay.com/v1/checkout.js';

function loadRazorpayScript(): Promise<boolean> {
  if (typeof window === 'undefined') return Promise.resolve(false);
  if (window.Razorpay) return Promise.resolve(true);

  return new Promise((resolve) => {
    const script = document.createElement('script');
    script.src = RAZORPAY_SCRIPT;
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

/**
 * Opens Razorpay's hosted checkout. Activation is never trusted from the browser — the backend
 * flips the subscription to active only when it receives a signature-verified webhook.
 */
export function useRazorpayCheckout() {
  const [pendingPlan, setPendingPlan] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkout = useCallback(async (planCode: string, userEmail?: string, userName?: string) => {
    setPendingPlan(planCode);
    setError(null);
    try {
      const scriptReady = await loadRazorpayScript();
      if (!scriptReady) {
        setError('Could not load the payment window. Check your connection and try again.');
        return;
      }

      const order = await billingService.startCheckout(planCode);
      const razorpay = new window.Razorpay!({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        order_id: order.order_id,
        name: 'ai.sumitgroups.com',
        description: `${planCode} plan`,
        prefill: { email: userEmail, name: userName },
        theme: { color: '#0a0a0a' },
        modal: { ondismiss: () => setPendingPlan(null) },
        handler: () => {
          // Payment captured. The webhook activates the plan; send the user somewhere that reflects it.
          window.location.href = '/settings/subscription?checkout=processing';
        },
      });
      razorpay.open();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not start checkout. Please try again.');
      setPendingPlan(null);
    }
  }, []);

  return { checkout, pendingPlan, error };
}
