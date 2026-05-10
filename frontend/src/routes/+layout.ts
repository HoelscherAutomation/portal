import { redirect } from '@sveltejs/kit';

import type { TenantConfig, User } from '$lib/api';
import { loadCurrentUser } from '$lib/stores/auth';
import { loadTenant } from '$lib/stores/tenant';

export const ssr = false;

export async function load({ url }: { url: URL }): Promise<{ user: User | null; tenant: TenantConfig | null }> {
  const user = await loadCurrentUser();
  if (!user) {
    if (url.pathname !== '/login') {
      throw redirect(302, '/login');
    }
    return { user: null, tenant: null };
  }
  if (url.pathname === '/login') {
    throw redirect(302, '/');
  }
  const tenantConfig = await loadTenant();
  return { user, tenant: tenantConfig };
}
