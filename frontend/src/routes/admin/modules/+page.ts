import { error } from '@sveltejs/kit';
import { get } from 'svelte/store';

import { loadModules, modules } from '$lib/stores/modules';

import type { PageLoad } from './$types';

export const ssr = false;

export const load: PageLoad = async ({ parent }) => {
  const { user } = await parent();
  if (!user || !user.is_superuser) {
    throw error(403, 'Admin access required');
  }
  if (get(modules).length === 0) {
    await loadModules();
  }
  return {};
};
