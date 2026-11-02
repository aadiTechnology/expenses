// Empty = same origin. Set VITE_API_URL at build time when the API has its own domain (e.g. https://expensesapi.aaditechnology.com).
const BASE = ((import.meta as any).env?.VITE_API_URL ?? '').replace(/\/$/, '') + '/api/v1'
const KEY = 'spendos.token'
export const getToken = () => sessionStorage.getItem(KEY) || ''
export const setToken = (t: string | null) => (t ? sessionStorage.setItem(KEY, t) : sessionStorage.removeItem(KEY))

export class ApiError extends Error {
  status: number
  detail: any
  constructor(status: number, detail: any) {
    super(typeof detail === 'string' ? detail : detail?.message || 'Request failed')
    this.status = status
    this.detail = detail
  }
}

async function parse(res: Response) {
  const text = await res.text()
  let body: any = null
  try { body = text ? JSON.parse(text) : null } catch { body = text }
  if (!res.ok) {
    const d = body?.detail
    throw new ApiError(res.status, Array.isArray(d) ? d.map((x: any) => x.msg).join('; ') : d ?? 'Request failed')
  }
  return body
}

export async function api(path: string, opts: { method?: string; body?: any; form?: FormData } = {}) {
  const headers: Record<string, string> = {}
  const t = getToken()
  if (t) headers.Authorization = `Bearer ${t}`
  let body: any
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.body) }
  const res = await fetch(`${BASE}${path}`, { method: opts.method || (body ? 'POST' : 'GET'), headers, body })
  return parse(res)
}

export async function download(path: string, filename: string) {
  const res = await fetch(`${BASE}${path}`, { headers: { Authorization: `Bearer ${getToken()}` } })
  if (!res.ok) throw new ApiError(res.status, 'Download failed')
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export const qs = (o: Record<string, any>) => {
  const p = new URLSearchParams()
  Object.entries(o).forEach(([k, v]) => v !== undefined && v !== null && v !== '' && p.set(k, String(v)))
  const s = p.toString()
  return s ? `?${s}` : ''
}
