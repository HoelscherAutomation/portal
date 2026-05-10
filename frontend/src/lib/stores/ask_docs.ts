import { writable } from 'svelte/store';

import { api, type ApiError, type AskDocsDocument } from '../api';

export const askDocsDocuments = writable<AskDocsDocument[]>([]);
export const askDocsError = writable<string | null>(null);

export async function loadDocuments(): Promise<AskDocsDocument[]> {
  try {
    const docs = await api.get<AskDocsDocument[]>('/api/modules/ask-docs/documents');
    askDocsDocuments.set(docs);
    askDocsError.set(null);
    return docs;
  } catch (err) {
    const apiErr = err as ApiError;
    if (apiErr?.status === 401 || apiErr?.status === 403) {
      askDocsDocuments.set([]);
      askDocsError.set(null);
      return [];
    }
    askDocsError.set(apiErr?.detail ?? 'Could not load documents');
    askDocsDocuments.set([]);
    return [];
  }
}

export async function uploadDocument(file: File): Promise<AskDocsDocument> {
  const formData = new FormData();
  formData.append('file', file);
  const created = await api.postFile<AskDocsDocument>('/api/modules/ask-docs/documents', formData);
  await loadDocuments();
  return created;
}

export async function deleteDocument(id: string): Promise<void> {
  await api.delete(`/api/modules/ask-docs/documents/${id}`);
  await loadDocuments();
}

export async function getDocument(id: string): Promise<AskDocsDocument> {
  return await api.get<AskDocsDocument>(`/api/modules/ask-docs/documents/${id}`);
}
