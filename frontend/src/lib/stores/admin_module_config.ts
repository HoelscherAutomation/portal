import { api, type AskDocsConfig, type ProbeResult } from '../api';

export async function loadAskDocsConfig(): Promise<AskDocsConfig> {
  return await api.get<AskDocsConfig>('/api/admin/modules/ask-docs/config');
}

export async function saveAskDocsConfig(payload: AskDocsConfig): Promise<AskDocsConfig> {
  return await api.put<AskDocsConfig>('/api/admin/modules/ask-docs/config', payload);
}

export async function probeAskDocsConfig(
  mode: AskDocsConfig['llm_mode'],
  settings: Record<string, unknown>
): Promise<ProbeResult> {
  return await api.post<ProbeResult>('/api/admin/modules/ask-docs/config/probe', { mode, settings });
}
