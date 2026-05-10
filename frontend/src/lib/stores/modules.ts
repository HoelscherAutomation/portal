import { writable } from 'svelte/store';

import { api, type Module } from '../api';

export const modules = writable<Module[]>([]);

export async function loadModules(): Promise<Module[]> {
  try {
    const list = await api.get<Module[]>('/api/modules');
    modules.set(list);
    return list;
  } catch {
    modules.set([]);
    return [];
  }
}

export async function requestModule(key: string): Promise<void> {
  await api.post<{ status: string }>(`/api/modules/${key}/request`);
  await loadModules();
}
