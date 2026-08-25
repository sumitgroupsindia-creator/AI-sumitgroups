import { apiFetch } from '@/lib/api-client';
import { clearTokens, setTokens } from '@/lib/auth-storage';
import type { TokenPair, User } from '@/types/api';

export async function register(email: string, password: string, fullName?: string): Promise<TokenPair> {
  const tokens = await apiFetch<TokenPair>('/auth/register', {
    method: 'POST',
    auth: false,
    body: { email, password, full_name: fullName || null },
  });
  setTokens(tokens.access_token, tokens.refresh_token);
  return tokens;
}

export async function login(email: string, password: string): Promise<TokenPair> {
  const tokens = await apiFetch<TokenPair>('/auth/login', {
    method: 'POST',
    auth: false,
    body: { email, password },
  });
  setTokens(tokens.access_token, tokens.refresh_token);
  return tokens;
}

export async function logout(): Promise<void> {
  try {
    await apiFetch<void>('/auth/logout', { method: 'POST', raw: true });
  } finally {
    clearTokens();
  }
}

export function getCurrentUser(): Promise<User> {
  return apiFetch<User>('/user/me');
}

export function updateProfile(fullName: string): Promise<User> {
  return apiFetch<User>('/user/me', { method: 'PATCH', body: { full_name: fullName } });
}

export function forgotPassword(email: string): Promise<{ message: string }> {
  return apiFetch('/auth/forgot-password', { method: 'POST', auth: false, body: { email } });
}

export function resetPassword(token: string, newPassword: string): Promise<void> {
  return apiFetch<void>('/auth/reset-password', {
    method: 'POST',
    auth: false,
    raw: true,
    body: { token, new_password: newPassword },
  });
}
