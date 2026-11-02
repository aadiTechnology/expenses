import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { Alert, Box, Chip, LinearProgress, Paper, Snackbar, Stack, Typography } from '@mui/material'
import { api, ApiError } from './api'
import { getLang, saveLang, translate, type Lang } from './i18n'

export const inr = (minor: number | null | undefined, opts: { sign?: boolean } = {}) => {
  if (minor === null || minor === undefined) return '—'
  const v = minor / 100
  const s = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: v % 1 ? 2 : 0, maximumFractionDigits: 2 }).format(Math.abs(v))
  return (v < 0 ? '−' : opts.sign && v > 0 ? '+' : '') + s
}

export interface Session {
  user: any
  tenant: any
  role: string
  role_label: string
  membership_id: string
  permissions: string[]
  entitlements: Record<string, boolean>
  memberships: any[]
  unread: number
}
interface Ctx { lang: Lang; setLang: (l: Lang) => void; t: (text: string) => string; me: Session | null; reload: () => Promise<void>; can: (p: string) => boolean; has: (module: string) => boolean; toast: (msg: string, sev?: 'success' | 'error' | 'info') => void }
export const AppCtx = createContext<Ctx>(null as any)
export const useApp = () => useContext(AppCtx)

export function ToastHost({ children, me, reload }: { children: ReactNode; me: Session | null; reload: () => Promise<void> }) {
  const [t, setT] = useState<{ msg: string; sev: 'success' | 'error' | 'info' } | null>(null)
  const [lang, setLangState] = useState<Lang>(getLang())
  const value: Ctx = {
    lang, setLang: (l) => { saveLang(l); setLangState(l) }, t: (x) => translate(lang, x),
    me, reload,
    can: (p) => !!me?.permissions?.includes(p),
    has: (m) => !!me?.entitlements?.[m],
    toast: (msg, sev = 'success') => setT({ msg, sev }),
  }
  return (
    <AppCtx.Provider value={value}>
      {children}
      <Snackbar open={!!t} autoHideDuration={5000} onClose={() => setT(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {t ? <Alert severity={t.sev} variant="filled" onClose={() => setT(null)} role="status">{t.msg}</Alert> : undefined}
      </Snackbar>
    </AppCtx.Provider>
  )
}

export function errText(e: any) {
  if (e instanceof ApiError) return typeof e.detail === 'object' && e.detail?.message ? e.detail.message : e.message
  return String(e?.message || e)
}

/** Fetch helper with loading / error state. */
export function useLoad<T = any>(path: string | null, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (path === null) return
    let live = true
    setLoading(true)
    api(path).then((d) => live && (setData(d), setError(null))).catch((e) => live && setError(errText(e))).finally(() => live && setLoading(false))
    return () => { live = false }
  }, [path, tick, ...deps])
  return { data, error, loading, reload: () => setTick((x) => x + 1) }
}

export function Page({ title, subtitle, actions, children }: { title: string; subtitle?: string; actions?: ReactNode; children: ReactNode }) {
  const { t } = useApp()
  return (
    <Box>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={1} sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h5" component="h1" fontWeight={700}>{t(title)}</Typography>
          {subtitle && <Typography variant="body2" color="text.secondary">{subtitle}</Typography>}
        </Box>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>{actions}</Stack>
      </Stack>
      {children}
    </Box>
  )
}

export function Card({ title, children, action, sx }: { title?: string; children: ReactNode; action?: ReactNode; sx?: any }) {
  return (
    <Paper variant="outlined" sx={{ p: 2, ...sx }}>
      {(title || action) && (
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="subtitle1" fontWeight={600}>{title}</Typography>
          {action}
        </Stack>
      )}
      {children}
    </Paper>
  )
}

export function State({ loading, error, children }: { loading: boolean; error: string | null; children: ReactNode }) {
  if (loading) return <LinearProgress aria-label="Loading" />
  if (error) return <Alert severity="error">{error}</Alert>
  return <>{children}</>
}

export function Empty({ text }: { text: string }) {
  return <Typography color="text.secondary" sx={{ py: 3, textAlign: 'center' }}>{text}</Typography>
}

const STATUS: Record<string, { label: string; color: any }> = {
  posted: { label: 'Posted', color: 'default' }, draft: { label: 'Draft', color: 'default' }, submitted: { label: 'Awaiting approval', color: 'warning' },
  pm_approved: { label: 'Awaiting finance', color: 'warning' }, verified: { label: 'Ready to pay', color: 'info' }, paid: { label: 'Paid', color: 'success' },
  rejected: { label: 'Rejected', color: 'error' },
}
export const StatusChip = ({ status }: { status: string }) => <Chip size="small" label={STATUS[status]?.label || status} color={STATUS[status]?.color || 'default'} variant={status === 'posted' ? 'outlined' : 'filled'} />

export function Bars({ rows, color = '#3949ab' }: { rows: { name: string; amount_minor: number; color?: string }[]; color?: string }) {
  const max = Math.max(1, ...rows.map((r) => r.amount_minor))
  if (!rows.length) return <Empty text="No spending in this period yet." />
  return (
    <Stack spacing={1}>
      {rows.map((r) => (
        <Box key={r.name}>
          <Stack direction="row" justifyContent="space-between"><Typography variant="body2">{r.name}</Typography><Typography variant="body2" fontWeight={600}>{inr(r.amount_minor)}</Typography></Stack>
          <Box sx={{ height: 8, bgcolor: 'action.hover', borderRadius: 4 }}><Box sx={{ height: 8, width: `${(r.amount_minor / max) * 100}%`, bgcolor: r.color || color, borderRadius: 4 }} /></Box>
        </Box>
      ))}
    </Stack>
  )
}

export function Utilization({ pct }: { pct: number | null }) {
  if (pct === null || pct === undefined) return <Typography variant="body2" color="text.secondary">No budget</Typography>
  const c = pct >= 100 ? 'error' : pct >= 90 ? 'warning' : pct >= 75 ? 'info' : 'success'
  return (
    <Box sx={{ minWidth: 120 }}>
      <LinearProgress variant="determinate" value={Math.min(100, pct)} color={c as any} sx={{ height: 8, borderRadius: 4 }} aria-label={`${pct}% used`} />
      <Typography variant="caption">{pct}% used</Typography>
    </Box>
  )
}

export const monthLabel = (p: string) => new Date(`${p}-01T00:00:00`).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })
export const today = () => new Date().toISOString().slice(0, 10)
