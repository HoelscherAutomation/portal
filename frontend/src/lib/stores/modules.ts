import { writable } from 'svelte/store';

import { api, type ApiError, type Module } from '../api';

export const modules = writable<Module[]>([]);
export const modulesError = writable<string | null>(null);

export async function loadModules(): Promise<Module[]> {
  try {
    const list = await api.get<Module[]>('/api/modules');
    modules.set(list);
    modulesError.set(null);
    return list;
  } catch (err) {
    const apiErr = err as ApiError;
    if (apiErr?.status === 401 || apiErr?.status === 403) {
      modules.set([]);
      modulesError.set(null);
      return [];
    }
    modulesError.set(apiErr?.detail ?? 'Could not load modules');
    modules.set([]);
    return [];
  }
}

export async function requestModule(key: string): Promise<void> {
  await api.post<{ status: string }>(`/api/modules/${key}/request`);
  await loadModules();
}
