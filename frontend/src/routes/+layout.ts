import { redirect } from '@sveltejs/kit';

import { loadCurrentUser } from '$lib/stores/auth';
import { loadTenant } from '$lib/stores/tenant';

import type { LayoutLoad } from './$types';

export const ssr = false;

export const load: LayoutLoad = async ({ url }) => {
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
};
