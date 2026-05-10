import { writable } from 'svelte/store';

import { API_BASE, api, type ApiError, type TenantConfig } from '../api';

export const tenant = writable<TenantConfig | null>(null);
export const tenantError = writable<string | null>(null);

export async function loadTenant(): Promise<TenantConfig | null> {
  try {
    const config = await api.get<TenantConfig>('/api/tenant/config');
    tenant.set(config);
    tenantError.set(null);
    return config;
  } catch (err) {
    const apiErr = err as ApiError;
    if (apiErr?.status === 401 || apiErr?.status === 403) {
      // Not authenticated — fine, layout will redirect.
      tenant.set(null);
      tenantError.set(null);
      return null;
    }
    tenantError.set(apiErr?.detail ?? 'Could not load tenant config');
    tenant.set(null);
    return null;
  }
}

export function logoUrl(filename: string | null): string | null {
  if (!filename) return null;
  return `${API_BASE}/uploads/${filename}`;
}

export async function updateTenant(patch: Partial<{
  company_name: string;
  primary_color: string;
  welcome_message: string | null;
}>): Promise<TenantConfig> {
  const updated = await api.put<TenantConfig>('/api/tenant/config', patch);
  tenant.set(updated);
  return updated;
}

export async function uploadLogo(file: File): Promise<TenantConfig> {
  const formData = new FormData();
  formData.append('file', file);
  const updated = await api.postFile<TenantConfig>('/api/tenant/logo', formData);
  tenant.set(updated);
  return updated;
}
