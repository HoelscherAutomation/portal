import { env } from '$env/dynamic/public';

export const API_BASE = env.PUBLIC_API_URL ?? 'http://localhost:8000';

export type ApiError = { status: number; detail: string };

async function request<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const baseHeaders: Record<string, string> =
    init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' };
  const initHeaders = (init.headers ?? {}) as Record<string, string>;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      credentials: 'include',
      headers: { ...baseHeaders, ...initHeaders }
    });
  } catch (networkErr) {
    // fetch() itself throws on network failure / DNS / CORS denial.
    // Log the original error so the underlying cause (CORS, DNS, etc.) is
    // visible in the browser console for debugging.
    console.error('fetch failed:', networkErr);
    throw {
      status: 0,
      detail: 'Network error — could not reach the server'
    } satisfies ApiError;
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body?.detail ?? body?.message ?? detail;
    } catch {
      // body wasn't JSON; keep statusText
    }
    throw { status: response.status, detail } satisfies ApiError;
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  postForm: <T>(path: string, formData: URLSearchParams) =>
    request<T>(path, {
      method: 'POST',
      body: formData,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    }),
  postFile: <T>(path: string, formData: FormData) =>
    request<T>(path, {
      method: 'POST',
      body: formData,
      headers: {} // let browser set multipart boundary
    })
};

export type User = {
  id: number;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
};

export type TenantConfig = {
  company_name: string;
  primary_color: string;
  logo_filename: string | null;
  welcome_message: string | null;
  updated_at: string;
};

export type Module = {
  key: string;
  name: string;
  description: string;
  status: 'live' | 'preview';
  target: string;
  enabled: boolean;
  has_pending_request: boolean;
};

export type AskDocsDocument = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: 'pending' | 'indexing' | 'indexed' | 'failed';
  chunk_count: number;
  error_message: string | null;
  uploaded_at: string;
};

export type ChatSourceEvent = {
  type: 'sources';
  sources: Array<{ number: number; filename: string; page_num: number; content: string }>;
};

export type ChatDeltaEvent = {
  type: 'delta';
  text: string;
};

export type ChatFinalEvent = {
  type: 'final';
  answer: string;
  citations: number[];
};

export type ChatEvent = ChatSourceEvent | ChatDeltaEvent | ChatFinalEvent;

export type ChunkPreview = {
  doc_id: string;
  page_num: number;
  chunk_index: number;
  content: string;
  source_path: string;
};
