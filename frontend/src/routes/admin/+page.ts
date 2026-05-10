import { error } from '@sveltejs/kit';

export const ssr = false;

export async function load({ parent }: { parent: () => Promise<{ user: { is_superuser: boolean } | null }> }) {
  const { user } = await parent();
  if (!user || !user.is_superuser) {
    throw error(403, 'Admin access required');
  }
  return {};
}
