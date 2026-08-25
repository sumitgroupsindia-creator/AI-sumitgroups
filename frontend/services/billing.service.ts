import { apiFetch } from '@/lib/api-client';
import type { CheckoutResponse, Credits, Plan, Subscription, UsageRecord } from '@/types/api';

export function listPlans(): Promise<Plan[]> {
  return apiFetch<Plan[]>('/subscription/plans', { auth: false });
}

export function getSubscription(): Promise<Subscription | null> {
  return apiFetch<Subscription | null>('/subscription');
}

export function startCheckout(planCode: string): Promise<CheckoutResponse> {
  return apiFetch<CheckoutResponse>('/subscription/checkout', {
    method: 'POST',
    body: { plan_code: planCode },
  });
}

export function cancelSubscription(): Promise<Subscription> {
  return apiFetch<Subscription>('/subscription/cancel', { method: 'POST' });
}

export function getCredits(): Promise<Credits> {
  return apiFetch<Credits>('/credits');
}

export function getUsage(limit = 50, offset = 0): Promise<UsageRecord[]> {
  return apiFetch<UsageRecord[]>(`/usage?limit=${limit}&offset=${offset}`);
}
