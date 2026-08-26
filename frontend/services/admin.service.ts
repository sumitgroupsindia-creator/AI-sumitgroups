import { apiFetch } from '@/lib/api-client';
import type {
  AdminGenerationResult,
  AdminPricing,
  AdminSetting,
  AdminSettingAudit,
  AdminStats,
  AdminUser,
  Plan,
  ProviderBrand,
  ProviderConfig,
  PromptTemplate,
} from '@/types/api';

export function getStats(): Promise<AdminStats> {
  return apiFetch<AdminStats>('/admin/stats');
}

export function listUsers(limit = 50, offset = 0): Promise<AdminUser[]> {
  return apiFetch<AdminUser[]>(`/admin/users?limit=${limit}&offset=${offset}`);
}

export function updateUser(id: string, patch: { is_active?: boolean; is_admin?: boolean }): Promise<AdminUser> {
  return apiFetch<AdminUser>(`/admin/users/${id}`, { method: 'PATCH', body: patch });
}

export function listPlans(): Promise<Plan[]> {
  return apiFetch<Plan[]>('/admin/plans');
}

export function updatePlan(
  id: string,
  patch: Partial<Pick<Plan, 'name' | 'monthly_credits' | 'max_upload_mb'>> & {
    price?: number;
    is_active?: boolean;
  },
): Promise<Plan> {
  return apiFetch<Plan>(`/admin/plans/${id}`, { method: 'PATCH', body: patch });
}

export function listProviderConfigs(): Promise<ProviderConfig[]> {
  return apiFetch<ProviderConfig[]>('/admin/models');
}

export function updateProviderConfig(
  id: string,
  patch: {
    is_enabled?: boolean;
    provider_cost_inr?: number;
    credit_cost?: number;
    margin_credits?: number;
    model?: string;
    display_name?: string;
  },
): Promise<ProviderConfig> {
  return apiFetch<ProviderConfig>(`/admin/models/${id}`, { method: 'PATCH', body: patch });
}

/** Current prices next to what they actually earned over the last `days`. */
export function getPricing(days = 30): Promise<AdminPricing> {
  return apiFetch<AdminPricing>(`/admin/pricing?days=${days}`);
}

export function listFailedGenerations(limit = 50): Promise<AdminGenerationResult[]> {
  return apiFetch<AdminGenerationResult[]>(`/admin/generations/failed?limit=${limit}`);
}

export function listPromptTemplates(): Promise<PromptTemplate[]> {
  return apiFetch<PromptTemplate[]>('/admin/prompts');
}

export function updatePromptTemplate(
  id: string,
  patch: Partial<Pick<PromptTemplate, 'name' | 'description' | 'content' | 'sort_order'>> & {
    is_enabled?: boolean;
  },
): Promise<PromptTemplate> {
  return apiFetch<PromptTemplate>(`/admin/prompts/${id}`, { method: 'PATCH', body: patch });
}

export function listProviderBrands(): Promise<ProviderBrand[]> {
  return apiFetch<ProviderBrand[]>('/admin/brands');
}

export function updateProviderBrand(
  id: string,
  patch: Partial<Pick<ProviderBrand, 'slot' | 'tier' | 'description' | 'sort_order'>>,
): Promise<ProviderBrand> {
  return apiFetch<ProviderBrand>(`/admin/brands/${id}`, { method: 'PATCH', body: patch });
}

export function listSettings(): Promise<AdminSetting[]> {
  return apiFetch<AdminSetting[]>('/admin/settings');
}

/**
 * Secrets left blank are ignored server-side rather than cleared, so an untouched form is safe to
 * submit wholesale.
 */
export function updateSettings(values: Record<string, string>): Promise<AdminSetting[]> {
  return apiFetch<AdminSetting[]>('/admin/settings', { method: 'PUT', body: { values } });
}

export function listSettingAudit(limit = 50): Promise<AdminSettingAudit[]> {
  return apiFetch<AdminSettingAudit[]>(`/admin/settings/audit?limit=${limit}`);
}
