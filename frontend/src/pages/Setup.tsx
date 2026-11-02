import { useState, type ReactNode } from 'react'
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, LinearProgress, MenuItem, Paper, Stack, Switch, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, TextField, Typography,
} from '@mui/material'
import Grid from '@mui/material/Grid'
import { api } from '../api'
import { Card, Empty, Page, State, Utilization, errText, inr, monthLabel, useApp, useLoad } from '../ui'
import { useLookups } from './Transactions'

export function FormDialog({ open, title, onClose, onSubmit, children, submitLabel = 'Save' }: { open: boolean; title: string; onClose: () => void; onSubmit: () => Promise<void>; children: ReactNode; submitLabel?: string }) {
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const go = async (e: any) => { e.preventDefault(); setBusy(true); setErr(''); try { await onSubmit() } catch (x) { setErr(errText(x)) } setBusy(false) }
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs" component="form" onSubmit={go}>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>{err && <Alert severity="error">{err}</Alert>}{children}</Stack></DialogContent>
      <DialogActions><Button onClick={onClose}>Cancel</Button><Button type="submit" variant="contained" disabled={busy}>{submitLabel}</Button></DialogActions>
    </Dialog>
  )
}

const ACCOUNT_TYPES = [['cash', 'Cash'], ['bank', 'Bank account'], ['upi', 'UPI wallet'], ['credit_card', 'Credit card'], ['wallet', 'Digital wallet'], ['petty_cash', 'Petty cash'], ['other', 'Other']]

export function Accounts() {
  const app = useApp()
  const { data, loading, error, reload } = useLoad('/accounts')
  const [open, setOpen] = useState(false)
  const [f, setF] = useState({ name: '', type: 'bank', opening: '' })
  const [xfer, setXfer] = useState(false)
  const [t, setT] = useState({ from: '', to: '', amount: '' })
  const manage = app.can('account.manage')
  return (
    <Page title="Accounts" subtitle="Balances are calculated from transactions. Transfers between your own accounts are never counted as income or expense."
      actions={<>{manage && <Button variant="contained" onClick={() => setOpen(true)}>Add account</Button>}<Button onClick={() => setXfer(true)}>Transfer between accounts</Button></>}>
      <State loading={loading} error={error}>
        <Grid container spacing={2}>
          {data?.map((a: any) => (
            <Grid key={a.id} size={{ xs: 12, sm: 6, md: 4 }}>
              <Card>
                <Stack direction="row" justifyContent="space-between"><Typography fontWeight={700}>{a.name}</Typography><Chip size="small" label={ACCOUNT_TYPES.find((x) => x[0] === a.type)?.[1]} /></Stack>
                <Typography variant="h5" fontWeight={800} color={a.balance_minor < 0 ? 'error.main' : 'text.primary'}>{inr(a.balance_minor)}</Typography>
                <Typography variant="caption" color="text.secondary">{a.type === 'credit_card' ? (a.balance_minor < 0 ? 'Outstanding on the card' : 'No amount owed') : 'Calculated balance'} · opening {inr(a.opening_minor)}{a.status !== 'active' ? ' · inactive' : ''}</Typography>
              </Card>
            </Grid>
          ))}
        </Grid>
        <Alert severity="info" sx={{ mt: 2 }}>SpendOS never asks for bank logins or card numbers. Credit-card purchases are recorded as expenses; paying the card bill is a transfer, so nothing is counted twice.</Alert>
      </State>
      <FormDialog open={open} title="Add account" onClose={() => setOpen(false)} onSubmit={async () => { await api('/accounts', { body: { name: f.name, type: f.type, opening: f.opening || '0' } }); setOpen(false); setF({ name: '', type: 'bank', opening: '' }); reload(); app.toast('Account added') }}>
        <TextField label="Account name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required autoFocus />
        <TextField select label="Type" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}>{ACCOUNT_TYPES.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}</TextField>
        <TextField label="Opening balance" value={f.opening} onChange={(e) => setF({ ...f, opening: e.target.value })} helperText="Leave empty for zero" />
      </FormDialog>
      <FormDialog open={xfer} title="Transfer between accounts" onClose={() => setXfer(false)} submitLabel="Transfer" onSubmit={async () => {
        await api('/transactions', { body: { date: new Date().toISOString().slice(0, 10), type: 'transfer', amount: t.amount, account_id: t.from, to_account_id: t.to, description: 'Account transfer' } }); setXfer(false); reload(); app.toast('Transfer recorded - not counted as income or expense') }}>
        <TextField select label="From" value={t.from} onChange={(e) => setT({ ...t, from: e.target.value })} required>{data?.map((a: any) => <MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>)}</TextField>
        <TextField select label="To" value={t.to} onChange={(e) => setT({ ...t, to: e.target.value })} required>{data?.map((a: any) => <MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>)}</TextField>
        <TextField label="Amount" value={t.amount} onChange={(e) => setT({ ...t, amount: e.target.value })} required />
      </FormDialog>
    </Page>
  )
}

export function Categories() {
  const app = useApp()
  const { data, loading, error, reload } = useLoad('/categories')
  const [dlg, setDlg] = useState<any>(null)
  const manage = app.can('config.manage')
  const roots = (data || []).filter((c: any) => !c.parent_id)
  const row = (c: any, indent = 0) => (
    <TableRow key={c.id}>
      <TableCell sx={{ pl: 2 + indent * 3 }}><Box component="span" sx={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', bgcolor: c.color, mr: 1 }} />{c.name}</TableCell>
      <TableCell>{c.kind}</TableCell><TableCell>{c.required_fields?.join(', ') || '—'}</TableCell><TableCell>{c.active ? <Chip size="small" color="success" label="Enabled" /> : <Chip size="small" label="Disabled" />}</TableCell>
      <TableCell align="right">{manage && <Button size="small" onClick={() => setDlg({ ...c })}>Edit</Button>}</TableCell>
    </TableRow>
  )
  return (
    <Page title="Categories" subtitle="Your own copy of the category tree — changes here affect only this workspace" actions={manage && <Button variant="contained" onClick={() => setDlg({ name: '', kind: 'expense', color: '#5c6bc0', active: true, required_fields: [], parent_id: null })}>Add category</Button>}>
      <State loading={loading} error={error}>
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="Categories"><TableHead><TableRow><TableCell>Name</TableCell><TableCell>Applies to</TableCell><TableCell>Mandatory fields</TableCell><TableCell>Status</TableCell><TableCell /></TableRow></TableHead>
            <TableBody>{roots.map((r: any) => [row(r), ...(data || []).filter((c: any) => c.parent_id === r.id).map((c: any) => row(c, 1))])}</TableBody></Table>
        </TableContainer>
      </State>
      {dlg && (
        <FormDialog open title={dlg.id ? 'Edit category' : 'Add category'} onClose={() => setDlg(null)} onSubmit={async () => {
          const body = { name: dlg.name, kind: dlg.kind, color: dlg.color, icon: dlg.icon || 'label', active: dlg.active, parent_id: dlg.parent_id || null, required_fields: dlg.required_fields }
          await api(dlg.id ? `/categories/${dlg.id}` : '/categories', { method: dlg.id ? 'PATCH' : 'POST', body }); setDlg(null); reload(); app.toast('Category saved') }}>
          <TextField label="Name" value={dlg.name} onChange={(e) => setDlg({ ...dlg, name: e.target.value })} required autoFocus />
          <TextField select label="Applies to" value={dlg.kind} onChange={(e) => setDlg({ ...dlg, kind: e.target.value })}><MenuItem value="expense">Expenses</MenuItem><MenuItem value="income">Income</MenuItem><MenuItem value="both">Both</MenuItem></TextField>
          {!dlg.id && <TextField select label="Parent category (for a subcategory)" value={dlg.parent_id || ''} onChange={(e) => setDlg({ ...dlg, parent_id: e.target.value })}><MenuItem value="">None (top level)</MenuItem>{roots.map((r: any) => <MenuItem key={r.id} value={r.id}>{r.name}</MenuItem>)}</TextField>}
          <TextField label="Colour" type="color" value={dlg.color} onChange={(e) => setDlg({ ...dlg, color: e.target.value })} />
          <TextField select SelectProps={{ multiple: true }} label="Mandatory fields" value={dlg.required_fields || []} onChange={(e) => setDlg({ ...dlg, required_fields: e.target.value })}>{['description', 'project', 'department'].map((x) => <MenuItem key={x} value={x}>{x}</MenuItem>)}</TextField>
          <FormControlLabel control={<Switch checked={dlg.active} onChange={(e) => setDlg({ ...dlg, active: e.target.checked })} />} label="Enabled" />
        </FormDialog>
      )}
    </Page>
  )
}

export function Departments() {
  const app = useApp()
  const { data, loading, error, reload } = useLoad('/departments')
  const rep = useLoad('/reports/department')
  const [name, setName] = useState<string | null>(null)
  return (
    <Page title="Departments" subtitle="Where operating cost is incurred. Managers see only their own department." actions={app.can('config.manage') && <Button variant="contained" onClick={() => setName('')}>Add department</Button>}>
      <State loading={loading || rep.loading} error={error}>
        <TableContainer component={Paper} variant="outlined"><Table size="small" aria-label="Departments">
          <TableHead><TableRow><TableCell>Department</TableCell><TableCell align="right">Actual ({rep.data?.period && monthLabel(rep.data.period)})</TableCell><TableCell align="right">Budget</TableCell><TableCell align="right">Variance</TableCell></TableRow></TableHead>
          <TableBody>{data?.map((d: any) => { const r = rep.data?.rows.find((x: any) => x[0] === d.name); return (
            <TableRow key={d.id}><TableCell>{d.name}</TableCell><TableCell align="right">{inr(r ? r[1] : 0)}</TableCell><TableCell align="right">{inr(r?.[2])}</TableCell><TableCell align="right">{inr(r?.[3], { sign: true })}</TableCell></TableRow>) })}</TableBody></Table></TableContainer>
      </State>
      <FormDialog open={name !== null} title="Add department" onClose={() => setName(null)} onSubmit={async () => { await api('/departments', { body: { name } }); setName(null); reload(); rep.reload(); app.toast('Department added') }}>
        <TextField label="Department name" value={name || ''} onChange={(e) => setName(e.target.value)} required autoFocus />
      </FormDialog>
    </Page>
  )
}

export function Projects() {
  const app = useApp()
  const { data, loading, error, reload } = useLoad('/projects')
  const L = useLookups()
  const rep = useLoad('/reports/project')
  const [dlg, setDlg] = useState<any>(null)
  return (
    <Page title="Projects" subtitle="Project-wise spend including allocated (split) expenses" actions={app.can('config.manage') && <Button variant="contained" onClick={() => setDlg({ name: '', department_id: '' })}>Add project</Button>}>
      <State loading={loading || rep.loading} error={error}>
        <TableContainer component={Paper} variant="outlined"><Table size="small" aria-label="Projects">
          <TableHead><TableRow><TableCell>Project</TableCell><TableCell>Department</TableCell><TableCell align="right">Actual</TableCell><TableCell align="right">Budget</TableCell><TableCell align="right">Variance</TableCell></TableRow></TableHead>
          <TableBody>{data?.map((p: any) => { const r = rep.data?.rows.find((x: any) => x[0] === p.name); return (
            <TableRow key={p.id}><TableCell>{p.name}</TableCell><TableCell>{L.name(L.departments, p.department_id)}</TableCell><TableCell align="right">{inr(r ? r[1] : 0)}</TableCell><TableCell align="right">{inr(r?.[2])}</TableCell><TableCell align="right">{inr(r?.[3], { sign: true })}</TableCell></TableRow>) })}</TableBody></Table></TableContainer>
      </State>
      {dlg && <FormDialog open title="Add project" onClose={() => setDlg(null)} onSubmit={async () => { await api('/projects', { body: { name: dlg.name, department_id: dlg.department_id || null } }); setDlg(null); reload(); rep.reload(); app.toast('Project added') }}>
        <TextField label="Project name" value={dlg.name} onChange={(e) => setDlg({ ...dlg, name: e.target.value })} required autoFocus />
        <TextField select label="Department" value={dlg.department_id} onChange={(e) => setDlg({ ...dlg, department_id: e.target.value })}><MenuItem value="">None</MenuItem>{L.departments.map((d: any) => <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>)}</TextField>
      </FormDialog>}
    </Page>
  )
}

export function Budgets() {
  const app = useApp()
  const [period, setPeriod] = useState('')
  const { data, loading, error, reload } = useLoad(`/budgets${period ? `?period=${period}` : ''}`)
  const dash = useLoad('/dashboard')
  const L = useLookups()
  const [dlg, setDlg] = useState<any>(null)
  const p = period || dash.data?.period || ''
  const budgets = (data || []).filter((b: any) => !p || b.period === p || !period)
  const shown = period ? data || [] : (data || []).filter((b: any) => b.period === p)
  const scopeOptions = dlg?.scope === 'department' ? L.departments : dlg?.scope === 'project' ? L.projects : dlg?.scope === 'category' ? L.categories.filter((c: any) => !c.parent_id && c.kind === 'expense') : dlg?.scope === 'dimension' ? (L.dims.find((d: any) => d.key === 'campaign')?.values || []) : []
  return (
    <Page title="Budgets" subtitle="Actual spend is calculated from the same transactions as every report. Alerts fire at 50%, 75%, 90% and 100%."
      actions={<>
        <TextField type="month" label="Month" value={p} onChange={(e) => setPeriod(e.target.value)} InputLabelProps={{ shrink: true }} />
        {app.can('budget.manage') && <Button variant="contained" onClick={() => setDlg({ name: '', scope: app.me!.tenant.edition === 'personal' ? 'overall' : 'project', scope_id: '', period: p, amount: '' })}>New budget</Button>}
      </>}>
      <State loading={loading || dash.loading} error={error}>
        {shown.length === 0 ? <Paper variant="outlined"><Empty text="No budgets for this month yet." /></Paper> : (
          <TableContainer component={Paper} variant="outlined"><Table size="small" aria-label="Budgets">
            <TableHead><TableRow><TableCell>Budget</TableCell><TableCell>Scope</TableCell><TableCell align="right">Budgeted</TableCell><TableCell align="right">Actual</TableCell><TableCell align="right">Remaining</TableCell><TableCell>Utilisation</TableCell><TableCell /></TableRow></TableHead>
            <TableBody>{shown.map((b: any) => (
              <TableRow key={b.id}><TableCell>{b.name}</TableCell><TableCell>{b.scope}</TableCell><TableCell align="right">{inr(b.budget_minor)}</TableCell><TableCell align="right">{inr(b.actual_minor)}</TableCell>
                <TableCell align="right" sx={{ color: b.variance_minor < 0 ? 'error.main' : undefined }}>{inr(b.variance_minor)}</TableCell><TableCell><Utilization pct={b.utilization} /></TableCell>
                <TableCell>{app.can('budget.manage') && <Button size="small" color="error" onClick={async () => { await api(`/budgets/${b.id}`, { method: 'DELETE' }); reload() }}>Delete</Button>}</TableCell></TableRow>))}</TableBody></Table></TableContainer>
        )}
      </State>
      {dlg && <FormDialog open title="New budget" onClose={() => setDlg(null)} onSubmit={async () => { await api('/budgets', { body: { name: dlg.name, scope: dlg.scope, scope_id: dlg.scope_id || null, dimension_id: dlg.scope === 'dimension' ? L.dims.find((d: any) => d.key === 'campaign')?.id : null, period: dlg.period, amount: dlg.amount } }); setDlg(null); reload(); app.reload(); app.toast('Budget created') }}>
        <TextField label="Budget name" value={dlg.name} onChange={(e) => setDlg({ ...dlg, name: e.target.value })} required autoFocus />
        <TextField select label="Applies to" value={dlg.scope} onChange={(e) => setDlg({ ...dlg, scope: e.target.value, scope_id: '' })}>
          <MenuItem value="overall">{app.me!.tenant.edition === 'personal' ? 'Whole household' : 'Whole organization'}</MenuItem><MenuItem value="category">A category</MenuItem>
          {app.me!.tenant.edition === 'business' && [<MenuItem key="d" value="department">A department</MenuItem>, <MenuItem key="p" value="project">A project</MenuItem>]}
          {app.has('growth_spend') && <MenuItem value="dimension">A campaign</MenuItem>}
        </TextField>
        {dlg.scope !== 'overall' && <TextField select label="Which one" value={dlg.scope_id} onChange={(e) => setDlg({ ...dlg, scope_id: e.target.value })} required>{scopeOptions.map((o: any) => <MenuItem key={o.id} value={o.id}>{o.name}</MenuItem>)}</TextField>}
        <TextField label="Month" type="month" value={dlg.period} onChange={(e) => setDlg({ ...dlg, period: e.target.value })} InputLabelProps={{ shrink: true }} required />
        <TextField label="Amount" value={dlg.amount} onChange={(e) => setDlg({ ...dlg, amount: e.target.value })} required />
      </FormDialog>}
    </Page>
  )
}

export function Family() {
  const app = useApp()
  const { data, loading, error, reload } = useLoad('/members')
  const rep = useLoad('/reports/member')
  const [dlg, setDlg] = useState<any>(null)
  const [issued, setIssued] = useState<any>(null)
  return (
    <Page title="Family" subtitle="Who is in the household, who can see what, and what each member spends" actions={app.can('member.manage') && <Button variant="contained" onClick={() => setDlg({ name: '', email: '', role: 'family_member' })}>Add family member</Button>}>
      <State loading={loading || rep.loading} error={error}>
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 7 }}>
            <TableContainer component={Paper} variant="outlined"><Table size="small" aria-label="Family members"><TableHead><TableRow><TableCell>Name</TableCell><TableCell>Role</TableCell><TableCell>Can do</TableCell></TableRow></TableHead>
              <TableBody>{data?.map((m: any) => <TableRow key={m.id}><TableCell>{m.name}<br /><Typography variant="caption" color="text.secondary">{m.email}</Typography></TableCell><TableCell>{m.role_label}</TableCell>
                <TableCell>{m.role === 'owner' ? 'Everything' : m.role === 'family_member' ? 'Own and shared transactions' : 'View shared items only'}</TableCell></TableRow>)}</TableBody></Table></TableContainer>
          </Grid>
          <Grid size={{ xs: 12, md: 5 }}><Card title="Spending by member (this month)">{(rep.data?.rows || []).map((r: any) => <Stack key={r[0]} direction="row" justifyContent="space-between" sx={{ py: 0.5 }}><Typography variant="body2">{r[0]}</Typography><Typography variant="body2" fontWeight={600}>{inr(r[1])}</Typography></Stack>)}</Card></Grid>
        </Grid>
      </State>
      {dlg && <FormDialog open title="Add family member" onClose={() => setDlg(null)} onSubmit={async () => { const r = await api('/members', { body: dlg }); setDlg(null); setIssued(r); reload() }}>
        <TextField label="Name" value={dlg.name} onChange={(e) => setDlg({ ...dlg, name: e.target.value })} required autoFocus />
        <TextField label="Email" type="email" value={dlg.email} onChange={(e) => setDlg({ ...dlg, email: e.target.value })} required />
        <TextField select label="Role" value={dlg.role} onChange={(e) => setDlg({ ...dlg, role: e.target.value })}><MenuItem value="family_member">Family member (own transactions)</MenuItem><MenuItem value="family_viewer">Family viewer (shared items, read-only)</MenuItem></TextField>
      </FormDialog>}
      <Dialog open={!!issued} onClose={() => setIssued(null)}><DialogTitle>Member added</DialogTitle><DialogContent>{issued?.temporary_password ? <Typography>Temporary password (shown once): <b>{issued.temporary_password}</b></Typography> : <Typography>They already have an account and can switch to this workspace.</Typography>}</DialogContent><DialogActions><Button onClick={() => setIssued(null)}>Done</Button></DialogActions></Dialog>
    </Page>
  )
}

export function Goals() {
  const app = useApp()
  const { data, loading, error, reload } = useLoad('/goals')
  const [dlg, setDlg] = useState<any>(null)
  return (
    <Page title="Savings goals" subtitle="Targets you are saving towards" actions={app.can('goals.manage') && <Button variant="contained" onClick={() => setDlg({ name: '', target: '', saved: '', target_date: '' })}>New goal</Button>}>
      <State loading={loading} error={error}>
        <Grid container spacing={2}>{data?.map((g: any) => (
          <Grid key={g.id} size={{ xs: 12, md: 4 }}><Card title={g.name}>
            <Typography variant="h6">{inr(g.saved_minor)} <Typography component="span" color="text.secondary">of {inr(g.target_minor)}</Typography></Typography>
            <LinearProgress variant="determinate" aria-label={`${g.name} progress`} value={Math.min(100, (g.saved_minor / g.target_minor) * 100)} sx={{ height: 10, borderRadius: 5, my: 1 }} />
            <Typography variant="caption" color="text.secondary">{Math.round((g.saved_minor / g.target_minor) * 100)}% · target date {g.target_date || 'not set'}</Typography></Card></Grid>))}</Grid>
        {data?.length === 0 && <Empty text="No goals yet." />}
      </State>
      {dlg && <FormDialog open title="New savings goal" onClose={() => setDlg(null)} onSubmit={async () => { await api('/goals', { body: { name: dlg.name, target: dlg.target, saved: dlg.saved || '0', target_date: dlg.target_date || null } }); setDlg(null); reload(); app.toast('Goal created') }}>
        <TextField label="Goal" value={dlg.name} onChange={(e) => setDlg({ ...dlg, name: e.target.value })} required autoFocus />
        <TextField label="Target amount" value={dlg.target} onChange={(e) => setDlg({ ...dlg, target: e.target.value })} required />
        <TextField label="Saved so far" value={dlg.saved} onChange={(e) => setDlg({ ...dlg, saved: e.target.value })} />
        <TextField label="Target date" type="date" value={dlg.target_date} onChange={(e) => setDlg({ ...dlg, target_date: e.target.value })} InputLabelProps={{ shrink: true }} />
      </FormDialog>}
    </Page>
  )
}
