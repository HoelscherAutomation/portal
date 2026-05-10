import { writable } from 'svelte/store';

import { api, type ApiError, type User } from '../api';

export const currentUser = writable<User | null>(null);
export const authError = writable<string | null>(null);

export async function loadCurrentUser(): Promise<User | null> {
  try {
    const user = await api.get<User>('/api/me');
    currentUser.set(user);
    authError.set(null);
    return user;
  } catch (err) {
    const apiErr = err as ApiError;
    if (apiErr?.status === 401 || apiErr?.status === 403) {
      // Genuine "not authenticated" — clear the user.
      currentUser.set(null);
      authError.set(null);
      return null;
    }
    // Server error or network outage — surface it, don't masquerade as logged-out.
    authError.set(apiErr?.detail ?? 'Could not reach the server');
    currentUser.set(null);
    return null;
  }
}

export async function login(email: string, password: string): Promise<User> {
  const formData = new URLSearchParams();
  formData.set('username', email);
  formData.set('password', password);
  await api.postForm('/api/auth/login', formData);
  // Direct call (no swallowing) so login surfaces /api/me failures clearly.
  const user = await api.get<User>('/api/me');
  currentUser.set(user);
  return user;
}

export async function logout(): Promise<void> {
  await api.post('/api/auth/logout');
  currentUser.set(null);
}
