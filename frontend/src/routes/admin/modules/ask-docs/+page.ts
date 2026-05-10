import { error } from '@sveltejs/kit';

import type { PageLoad } from './$types';

export const ssr = false;

export const load: PageLoad = async ({ parent }) => {
  const { user } = await parent();
  if (!user || !user.is_superuser) {
    throw error(403, 'Admin access required');
  }
  return {};
};
