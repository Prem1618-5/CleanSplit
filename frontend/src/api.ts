import axios from 'axios';

const BASE = import.meta.env.VITE_API_URL || '';

const api = axios.create({ baseURL: BASE });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

const form = (data: Record<string, unknown>) => {
  const fd = new FormData();
  Object.entries(data).forEach(([k, v]) => {
    if (v !== undefined && v !== null) fd.append(k, String(v));
  });
  return fd;
};

// ── Auth ──────────────────────────────────────────────────────
export const authApi = {
  register: (name: string, email: string, password: string) =>
    api.post('/api/auth/register', form({ name, email, password })),
  login: (email: string, password: string) => {
    const fd = new FormData();
    fd.append('username', email);
    fd.append('password', password);
    return api.post('/api/auth/login', fd);
  },
  me: () => api.get('/api/auth/me'),
};

// ── Groups ────────────────────────────────────────────────────
export const groupsApi = {
  list: () => api.get('/api/groups'),
  create: (name: string, usd_inr_rate: number) =>
    api.post('/api/groups', form({ name, usd_inr_rate })),
  get: (id: number) => api.get(`/api/groups/${id}`),
  update: (id: number, data: { name?: string; usd_inr_rate?: number }) =>
    api.patch(`/api/groups/${id}`, form(data)),
  addMember: (id: number, user_email: string, joined_at: string) =>
    api.post(`/api/groups/${id}/members`, form({ user_email, joined_at })),
  updateMember: (group_id: number, user_id: number, data: { left_at?: string }) =>
    api.patch(`/api/groups/${group_id}/members/${user_id}`, form(data)),
};

// ── Expenses ──────────────────────────────────────────────────
export const expensesApi = {
  list: (group_id: number) => api.get(`/api/groups/${group_id}/expenses`),
  get: (id: number) => api.get(`/api/expenses/${id}`),
  create: (
    group_id: number,
    data: {
      description: string;
      amount: number;
      currency: string;
      paid_by_user_id: number;
      split_type: string;
      expense_date: string;
      split_members: string;
      notes?: string;
    }
  ) => api.post(`/api/groups/${group_id}/expenses`, form(data)),
  delete: (id: number) => api.delete(`/api/expenses/${id}`),
};

// ── Balances ──────────────────────────────────────────────────
export const balancesApi = {
  group: (group_id: number) => api.get(`/api/groups/${group_id}/balances`),
  member: (group_id: number, user_id: number) =>
    api.get(`/api/groups/${group_id}/balances/${user_id}`),
};

// ── Settlements ───────────────────────────────────────────────
export const settlementsApi = {
  list: (group_id: number) => api.get(`/api/groups/${group_id}/settlements`),
  create: (
    group_id: number,
    data: {
      payer_id: number;
      receiver_id: number;
      amount: number;
      currency: string;
      settlement_date: string;
      notes?: string;
    }
  ) => api.post(`/api/groups/${group_id}/settlements`, form(data)),
};

// ── Import ────────────────────────────────────────────────────
export const importApi = {
  upload: (group_id: number, usd_inr_rate: number, file: File) => {
    const fd = new FormData();
    fd.append('group_id', String(group_id));
    fd.append('usd_inr_rate', String(usd_inr_rate));
    fd.append('file', file);
    return api.post('/api/import/upload', fd);
  },
  getRows: (session_id: number) => api.get(`/api/import/${session_id}/rows`),
  downloadReport: (session_id: number) =>
    api.get(`/api/import/${session_id}/report.md`, { responseType: 'blob' }),
  updateRow: (session_id: number, row_id: number, new_status: string, parsed_override?: string) =>
    api.patch(
      `/api/import/${session_id}/rows/${row_id}`,
      form({ new_status, ...(parsed_override ? { parsed_override } : {}) })
    ),
  commit: (session_id: number) => api.post(`/api/import/${session_id}/commit`),
  cancel: (session_id: number) => api.delete(`/api/import/${session_id}`),
};

export default api;
