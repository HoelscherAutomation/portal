import { redirect } from '@sveltejs/kit';
import { get } from 'svelte/store';

import { loadCurrentUser } from '$lib/stores/auth';
import { loadTenant, tenant } from '$lib/stores/tenant';

import type { LayoutLoad } from './$types';

export const ssr = false;

export const load: LayoutLoad = async ({ url }) => {
  // Fetch user (always); if we already have tenant config in the store, skip refetch.
  const tenantPromise = get(tenant) ? Promise.resolve(get(tenant)) : loadTenant();
  const [user, tenantConfig] = await Promise.all([
    loadCurrentUser(),
    tenantPromise
  ]);

  if (!user) {
    if (url.pathname !== '/login') {
      throw redirect(302, '/login');
    }
    return { user: null, tenant: null };
  }
  if (url.pathname === '/login') {
    throw redirect(302, '/');
  }
  return { user, tenant: tenantConfig };
};
