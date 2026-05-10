import { api, type DashboardPayload, type QueryDetail, type QueryListItem } from '../api';

export async function loadDashboard(): Promise<DashboardPayload> {
  return await api.get<DashboardPayload>('/api/admin/modules/ask-docs/dashboard');
}

export async function loadQueries(limit = 100, offset = 0): Promise<QueryListItem[]> {
  return await api.get<QueryListItem[]>(
    `/api/admin/modules/ask-docs/queries?limit=${limit}&offset=${offset}`
  );
}

export async function loadQueryDetail(queryId: number): Promise<QueryDetail> {
  return await api.get<QueryDetail>(`/api/admin/modules/ask-docs/queries/${queryId}`);
}
