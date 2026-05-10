import { loadDocuments } from '$lib/stores/ask_docs';

import type { PageLoad } from './$types';

export const ssr = false;

export const load: PageLoad = async () => {
  await loadDocuments();
  return {};
};
