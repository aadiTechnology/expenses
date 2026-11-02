import { useState } from 'react'
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Tooltip, Typography } from '@mui/material'
import DownloadIcon from '@mui/icons-material/Download'
import { api, download, qs } from '../api'
import { Card, Empty, Page, State, Utilization, errText, inr, useApp, useLoad } from '../ui'
import { useLookups } from './Transactions'

export function Reports() {
  const app = useApp()
  const biz = app.me!.tenant.edition === 'business'
  const all = app.can('scope.all')
  const options: [string, string][] = biz
    ? [['department', 'Department expenditure'], ['project', 'Project expenditure'], ['category', 'Category-wise expenditure'], ['budget_vs_actual', 'Budget vs actual'], ['monthly', 'Monthly operating costs'], ['reimbursement', 'Employee reimbursement'], ['comparison', 'Monthly comparison']]
    : [['monthly', 'Monthly income and expense'], ['category', 'Category-wise expenses'], ...(all ? [['account', 'Account-wise balances'] as [string, string]] : []), ['member', 'Family-member-wise expenses'], ['contributions', 'Family contributions'], ['budget_vs_actual', 'Budget vs actual'], ['comparison', 'Monthly comparison']]
  const [name, setName] = useState(options[0][0])
  const [period, setPeriod] = useState('')
  const { data, loading, error } = useLoad(`/reports/${name}${qs({ period })}`)
  const fmt = (i: number, v: any) => (data.money?.includes(i) ? inr(v, { sign: data.columns[i] === 'Variance' || data.columns[i] === 'Difference' || data.columns[i] === 'Change' }) : typeof v === 'number' && data.columns[i].includes('%') ? `${v}%` : v ?? '—')
  return (
    <Page title="Reports" subtitle="Every report is built from the same reconciled transactions and respects what you are allowed to see"
      actions={<>
        <Button startIcon={<DownloadIcon />} onClick={() => download(`/reports/${name}${qs({ period: period || data?.period, format: 'csv' })}`, `${name}.csv`)}>CSV</Button>
        <Button startIcon={<DownloadIcon />} onClick={() => download(`/reports/${name}${qs({ period: period || data?.period, format: 'pdf' })}`, `${name}.pdf`)}>PDF</Button>
      </>}>
      <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
        <TextField select label="Report" value={name} onChange={(e) => setName(e.target.value)} sx={{ minWidth: 280 }}>{options.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}</TextField>
        <TextField type="month" label="Month" value={period || data?.period || ''} onChange={(e) => setPeriod(e.target.value)} InputLabelProps={{ shrink: true }} />
      </Stack>
      <State loading={loading && !data} error={error}>
        {data && (
          <TableContainer component={Paper} variant="outlined">
            <Typography sx={{ p: 2, pb: 0 }} fontWeight={700}>{data.title}</Typography>
            <Table size="small" aria-label={data.title}>
              <TableHead><TableRow>{data.columns.map((c: string, i: number) => <TableCell key={c} align={i ? 'right' : 'left'}>{c}</TableCell>)}</TableRow></TableHead>
              <TableBody>{data.rows.map((r: any[], ri: number) => <TableRow key={ri}>{r.map((v, i) => <TableCell key={i} align={i ? 'right' : 'left'}>{fmt(i, v)}</TableCell>)}</TableRow>)}</TableBody>
            </Table>
            {data.rows.length === 0 && <Empty text="No data for this period." />}
          </TableContainer>
        )}
      </State>
    </Page>
  )
}

export function GrowthSpend() {
  const app = useApp()
  const L = useLookups()
  const [f, setF] = useState<any>({ period: '', department_id: '', project_id: '', category_id: '' })
  const { data, loading, error, reload } = useLoad(`/growth/spend${qs(f)}`)
  const imports = useLoad('/growth/imports')
  const [imp, setImp] = useState(false)
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value })
  return (
    <Page title="Marketing & sales spend" subtitle="Spend by campaign against budget. Cost-per-lead, CAC and ROI appear only when real lead, customer or revenue data has been imported."
      actions={<>
        {app.has('growth_import') && app.can('growth.manage') && <Button variant="contained" onClick={() => setImp(true)}>Import growth data (CSV)</Button>}
        <Button startIcon={<DownloadIcon />} onClick={() => download(`/growth/spend${qs({ ...f, format: 'csv' })}`, 'growth-spend.csv')}>Export CSV</Button>
      </>}>
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        <TextField type="month" label="Month" value={f.period || data?.period || ''} onChange={set('period')} InputLabelProps={{ shrink: true }} />
        <TextField select label="Department" value={f.department_id} onChange={set('department_id')} sx={{ minWidth: 190 }}><MenuItem value="">All</MenuItem>{L.departments.map((d: any) => <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>)}</TextField>
        <TextField select label="Project" value={f.project_id} onChange={set('project_id')} sx={{ minWidth: 190 }}><MenuItem value="">All</MenuItem>{L.projects.map((d: any) => <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>)}</TextField>
        <TextField select label="Category" value={f.category_id} onChange={set('category_id')} sx={{ minWidth: 170 }}><MenuItem value="">All</MenuItem>{L.categories.filter((c: any) => !c.parent_id && c.kind === 'expense').map((d: any) => <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>)}</TextField>
      </Stack>
      <State loading={loading && !data} error={error}>
        {data && (
          <>
            <TableContainer component={Paper} variant="outlined" sx={{ mb: 2 }}>
              <Table size="small" aria-label="Campaign spend">
                <TableHead><TableRow><TableCell>Campaign</TableCell><TableCell align="right">Actual</TableCell><TableCell align="right">Budget</TableCell><TableCell align="right">Variance</TableCell><TableCell>Utilisation</TableCell><TableCell align="right">Leads</TableCell><TableCell align="right">Cost / lead</TableCell><TableCell align="right">CAC (est.)</TableCell></TableRow></TableHead>
                <TableBody>{data.rows.map((r: any) => (
                  <TableRow key={r.value_id}>
                    <TableCell>{r.name}<Typography variant="caption" color="text.secondary" display="block">{r.metric_note}</Typography>{r.source && <Typography variant="caption" color="text.secondary" display="block">Source: {r.source}</Typography>}</TableCell>
                    <TableCell align="right">{inr(r.actual_minor)}</TableCell><TableCell align="right">{inr(r.budget_minor)}</TableCell><TableCell align="right" sx={{ color: r.variance_minor < 0 ? 'error.main' : undefined }}>{inr(r.variance_minor)}</TableCell>
                    <TableCell><Utilization pct={r.utilization} /></TableCell><TableCell align="right">{r.leads ?? '—'}</TableCell>
                    <TableCell align="right">{r.cost_per_lead_minor ? inr(r.cost_per_lead_minor) : <Tooltip title="Needs imported lead count"><Chip size="small" label="Unavailable" /></Tooltip>}</TableCell>
                    <TableCell align="right">{r.cac_minor ? inr(r.cac_minor) : <Tooltip title="Needs imported customer count"><Chip size="small" label="Unavailable" /></Tooltip>}</TableCell>
                  </TableRow>))}
                  <TableRow><TableCell>Marketing spend with no campaign tag</TableCell><TableCell align="right">{inr(data.untagged_minor)}</TableCell><TableCell colSpan={6} /></TableRow>
                  <TableRow sx={{ '& td': { fontWeight: 700 } }}><TableCell>Total (reconciles to Marketing transactions)</TableCell><TableCell align="right">{inr(data.total_minor)}</TableCell><TableCell colSpan={6} /></TableRow>
                </TableBody>
              </Table>
            </TableContainer>
            <Alert severity="info">{data.notes[0]} Customer-acquisition cost shown is an estimate: spend divided by imported customers, under the attribution method recorded with the import.</Alert>
          </>
        )}
        <Card title="Import history" sx={{ mt: 2 }}>
          {imports.data?.length === 0 && <Empty text="No imports yet." />}
          {imports.data?.map((b: any) => <Typography key={b.id} variant="body2">{b.at.slice(0, 10)} · {b.source} · {b.period} · {b.currency} · attribution “{b.attribution_method}” · <b>{b.status}</b> ({b.rows_ok} rows){b.errors?.length ? ` · ${b.errors.length} error(s)` : ''}</Typography>)}
        </Card>
      </State>
      <ImportGrowth open={imp} onClose={() => setImp(false)} onDone={() => { reload(); imports.reload() }} />
    </Page>
  )
}

function ImportGrowth({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const app = useApp()
  const [f, setF] = useState({ source: 'Manual CSV', period: '2026-10', currency: 'INR', attribution_method: 'Last touch, self-reported' })
  const [file, setFile] = useState<File | null>(null)
  const [errors, setErrors] = useState<any[]>([])
  const [msg, setMsg] = useState('')
  const go = async () => {
    if (!file) return
    const form = new FormData(); Object.entries(f).forEach(([k, v]) => form.append(k, v)); form.append('file', file)
    try { await api('/growth/import', { method: 'POST', form }); app.toast('Growth data imported'); setErrors([]); onDone(); onClose() } catch (x: any) { setMsg(errText(x)); setErrors(x.detail?.errors || []); onDone() }
  }
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Import campaign results</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography variant="body2">CSV columns: campaign, leads, customers, revenue, external_ref. All rows are checked first — if any row fails, nothing is imported.</Typography>
          <TextField label="Source system" value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} />
          <Stack direction="row" spacing={1}><TextField label="Period" type="month" value={f.period} onChange={(e) => setF({ ...f, period: e.target.value })} InputLabelProps={{ shrink: true }} /><TextField label="Currency" value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value })} /></Stack>
          <TextField label="Attribution method" value={f.attribution_method} onChange={(e) => setF({ ...f, attribution_method: e.target.value })} helperText="Shown beside every metric derived from this file" />
          <input type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] || null)} aria-label="Growth CSV file" />
          {msg && <Alert severity="error">{msg}{errors.map((e, i) => <div key={i}>Row {e.row}: {e.message}</div>)}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Cancel</Button><Button variant="contained" onClick={go} disabled={!file}>Validate and import</Button></DialogActions>
    </Dialog>
  )
}
