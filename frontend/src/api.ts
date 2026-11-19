import type { Job, PlanInfo, PlanOption, User } from './types'

const TOKEN_KEY = 'v2d_token'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}
export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const res = await fetch(`/api${path}`, { ...options, headers })
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const data = await res.json()
      detail = data.detail || detail
    } catch { /* ignore */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json() as Promise<T>
}

export const api = {
  me: () => request<User>('/auth/me'),
  register: (email: string, password: string, full_name: string) =>
    request<{ access_token: string }>('/auth/register', {
      method: 'POST', body: JSON.stringify({ email, password, full_name }),
    }),
  login: (email: string, password: string) =>
    request<{ access_token: string }>('/auth/login', {
      method: 'POST', body: JSON.stringify({ email, password }),
    }),

  plans: () => request<{ plans: PlanOption[]; current: PlanInfo }>('/billing/plans'),
  checkout: (plan: string) => request<{ url: string | null; message?: string }>('/billing/checkout', {
    method: 'POST', body: JSON.stringify({ plan }),
  }),
  portal: () => request<{ url: string }>('/billing/portal', { method: 'POST' }),
  devPlan: (plan: string) => request<{ plan: string }>('/billing/dev-plan', {
    method: 'POST', body: JSON.stringify({ plan }),
  }),

  jobs: () => request<Job[]>('/jobs'),
  job: (id: string) => request<Job>(`/jobs/${id}`),
  upload: (file: File, mode: string, maxWidth: number) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('mode', mode)
    fd.append('max_width', String(maxWidth))
    return request<{ id: string; status: string; message: string }>('/jobs/upload', {
      method: 'POST', body: fd,
    })
  },
  demo: (mode: string, seconds: number) => {
    const fd = new FormData()
    fd.append('mode', mode)
    fd.append('seconds', String(seconds))
    return request<{ id: string; status: string; message: string }>('/jobs/demo', {
      method: 'POST', body: fd,
    })
  },
  deleteJob: (id: string) => request<{ ok: boolean }>(`/jobs/${id}`, { method: 'DELETE' }),

  batch: (files: File[], mode: string, maxWidth: number) => {
    const fd = new FormData()
    files.forEach(f => fd.append('files', f))
    fd.append('mode', mode)
    fd.append('max_width', String(maxWidth))
    return request<{ created: { id: string; filename: string; status: string }[]; errors: any[] }>(
      '/jobs/batch', { method: 'POST', body: fd })
  },

  apiKeys: () => request<any[]>('/billing/api-keys'),
  createApiKey: (name: string) => request<{ id: number; key: string; name: string; note: string }>(
    '/billing/api-keys', { method: 'POST', body: JSON.stringify({ name }) }),
  revokeApiKey: (id: number) => request<{ ok: boolean }>(`/billing/api-keys/${id}`, { method: 'DELETE' }),

  adminUsers: () => request<any[]>('/admin/users'),
  adminStats: () => request<any>('/admin/stats'),
  adminUpdateUser: (id: number, patch: Record<string, any>) =>
    request<{ ok: boolean }>(`/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
}

export function wsUrl(jobId: string): string {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}/api/ws/jobs/${jobId}?token=${encodeURIComponent(getToken())}`
}
