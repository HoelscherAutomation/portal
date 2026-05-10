import { writable } from 'svelte/store';

import { api, type User } from '../api';

export const currentUser = writable<User | null>(null);

export async function loadCurrentUser(): Promise<User | null> {
  try {
    const user = await api.get<User>('/api/me');
    currentUser.set(user);
    return user;
  } catch {
    currentUser.set(null);
    return null;
  }
}

export async function login(email: string, password: string): Promise<User> {
  const formData = new URLSearchParams();
  formData.set('username', email);
  formData.set('password', password);
  await api.postForm('/api/auth/login', formData);
  const user = await loadCurrentUser();
  if (!user) {
    throw new Error('Login succeeded but /api/me returned null');
  }
  return user;
}

export async function logout(): Promise<void> {
  await api.post('/api/auth/logout');
  currentUser.set(null);
}
