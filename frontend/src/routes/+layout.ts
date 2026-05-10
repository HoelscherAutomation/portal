import { redirect } from '@sveltejs/kit';

import { loadCurrentUser } from '$lib/stores/auth';
import type { User } from '$lib/api';

export const ssr = false;

export async function load({ url }: { url: URL }): Promise<{ user: User | null }> {
  const user = await loadCurrentUser();
  if (!user) {
    if (url.pathname !== '/login') {
      throw redirect(302, '/login');
    }
    return { user: null };
  }
  if (url.pathname === '/login') {
    throw redirect(302, '/');
  }
  return { user };
}
