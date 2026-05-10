import { error } from '@sveltejs/kit';
import { get } from 'svelte/store';

import { loadModules, modules } from '$lib/stores/modules';

import type { LayoutLoad } from './$types';

export const ssr = false;

export const load: LayoutLoad = async () => {
  if (get(modules).length === 0) {
    await loadModules();
  }
  const askDocs = get(modules).find((m) => m.key === 'ask-docs');
  if (!askDocs?.enabled) {
    throw error(404, 'Ask Docs is not enabled on this portal');
  }
  return {};
};
