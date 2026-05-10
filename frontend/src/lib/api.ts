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

export type ChatErrorEvent = {
  type: 'error';
  detail: string;
};

export type ChatEvent = ChatSourceEvent | ChatDeltaEvent | ChatFinalEvent | ChatErrorEvent;

export type ChunkPreview = {
  doc_id: string;
  page_num: number;
  chunk_index: number;
  content: string;
  source_path: string;
};

export type SecretMarker = { _set: boolean };

export type AnthropicSettings = {
  api_key: SecretMarker | string | null;
  model: string;
  max_tokens: number;
};

export type OllamaSettings = {
  url: string;
  model: string;
  max_tokens: number;
};

export type AskDocsConfig = {
  llm_mode: 'anthropic' | 'ollama' | 'hoelscher_proxy';
  anthropic: AnthropicSettings;
  ollama: OllamaSettings;
  hoelscher_proxy: Record<string, never>;
  reranker: { enabled: boolean };
};

export type ProbeResult = {
  ok: boolean;
  latency_ms?: number;
  error?: string;
};

export type DashboardDocuments = {
  total: number;
  by_status: { pending: number; indexing: number; indexed: number; failed: number };
  total_chunks: number;
};

export type DashboardQueries30d = {
  count: number;
  tokens: number;
  cost_usd_estimated: number;
  by_mode: Array<{ mode: string; count: number; tokens: number }>;
  tokens_per_day: Array<{ date: string; tokens: number }>;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
};

export type DashboardPayload = {
  documents: DashboardDocuments;
  queries_30d: DashboardQueries30d;
  update_banner: null | { message: string; severity?: string };
};

export type QueryListItem = {
  id: number;
  user_email: string | null;
  query_text: string;
  answer_text: string;
  citation_count: number;
  llm_mode: string;
  tokens_used: number | null;
  duration_ms: number;
  sources_used: Array<{ number: number; filename: string; page_num: number; content: string }>;
  created_at: string;
};

export type QueryDetail = QueryListItem;
