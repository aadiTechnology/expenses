import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, Drawer, FormControlLabel, IconButton, MenuItem, Paper, Stack, Switch, Table, TableBody, TableCell,
  TableContainer, TableHead, TablePagination, TableRow, TextField, Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import DownloadIcon from '@mui/icons-material/Download'
import UploadIcon from '@mui/icons-material/Upload'
import { api, ApiError, download, qs } from '../api'
import { Card, Empty, Page, State, StatusChip, errText, inr, today, useApp, useLoad } from '../ui'

export function useLookups() {
  const accounts = useLoad('/accounts'), categories = useLoad('/categories'), projects = useLoad('/projects'), departments = useLoad('/departments')
  const members = useLoad('/members'), dims = useLoad('/dimensions')
  return {
    accounts: accounts.data || [], categories: categories.data || [], projects: projects.data || [], departments: departments.data || [], members: members.data || [], dims: dims.data || [],
    loading: accounts.loading || categories.loading, name: (list: any[], id: string) => list.find((x) => x.id === id)?.name || '',
  }
}

export function categoryOptions(categories: any[], kind: string) {
  const out: { value: string; label: string }[] = []
  categories.filter((c) => c.active && !c.parent_id && (c.kind === kind || c.kind === 'both')).forEach((p) => {
    out.push({ value: p.id, label: p.name })
    categories.filter((c) => c.parent_id === p.id && c.active).forEach((s) => out.push({ value: `${p.id}|${s.id}`, label: `${p.name} › ${s.name}` }))
  })
  return out
}

export function TxnForm({ initial, type: forced, onDone, onCancel }: { initial?: any; type?: string; onDone: (t: any) => void; onCancel?: () => void }) {
  const app = useApp()
  const L = useLookups()
  const biz = app.me!.tenant.edition === 'business'
  const claim = biz && !app.can('txn.edit_any')
  const [f, setF] = useState<any>(() => ({
    type: initial?.type || forced || 'expense', date: initial?.date || today(), amount: initial ? (initial.amount_minor / 100).toString() : '', cat: initial ? (initial.subcategory_id ? `${initial.category_id}|${initial.subcategory_id}` : initial.category_id || '') : '',
    description: initial?.description || '', merchant: initial?.merchant || '', account_id: initial?.account_id || '', to_account_id: initial?.to_account_id || '', project_id: initial?.project_id || '',
    department_id: initial?.department_id || '', member_id: initial?.member_id || '', shared: initial?.shared || false, notes: initial?.notes || '', refund_of_id: initial?.refund_of_id || '', dimensions: initial?.dimensions || {},
  }))
  const [splits, setSplits] = useState<{ project_id: string; amount: string }[]>(() => (initial?.splits || []).filter((s: any) => s.project_id).map((s: any) => ({ project_id: s.project_id, amount: s.amount })))
  const [shares, setShares] = useState<{ member_id: string; amount: string }[]>(() => (initial?.splits || []).filter((s: any) => s.member_id).map((s: any) => ({ member_id: s.member_id, amount: s.amount })))
  const [err, setErr] = useState('')
  const [dup, setDup] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [errs, setErrs] = useState<Record<string, string>>({})
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const catOpts = useMemo(() => categoryOptions(L.categories, f.type === 'income' ? 'income' : 'expense'), [L.categories, f.type])
  const expenses = useLoad(f.type === 'refund' || f.type === 'reimbursement' ? '/transactions?type=expense&page_size=100' : null)
  const isTransfer = f.type === 'transfer'
  const isCredit = f.type === 'refund' || f.type === 'reimbursement'

  useEffect(() => { if (!f.account_id && L.accounts.length && !claim && !initial) setF((x: any) => ({ ...x, account_id: L.accounts.find((a: any) => a.status === 'active')?.id || '' })) }, [L.accounts.length])

  const validate = () => {
    const e: Record<string, string> = {}
    if (!f.amount || !(Number(f.amount) > 0)) e.amount = 'Enter an amount greater than zero'
    else if (!/^\d+(\.\d{1,2})?$/.test(f.amount.replace(/,/g, ''))) e.amount = 'Use at most two decimal places'
    if (!f.date) e.date = 'Choose a date'
    if (!isTransfer && !isCredit && !f.cat) e.cat = 'Choose a category'
    if (isTransfer && (!f.account_id || !f.to_account_id)) e.to_account_id = 'Choose both accounts'
    if (isTransfer && f.account_id === f.to_account_id) e.to_account_id = 'Choose two different accounts'
    if (!claim && !f.account_id) e.account_id = 'Choose the account used'
    if (claim && !f.project_id) e.project_id = 'Choose the project to charge'
    setErrs(e)
    return Object.keys(e).length === 0
  }
  const save = async (allow = false, submit = true) => {
    if (!validate()) return
    setBusy(true); setErr(''); setDup(null)
    const [cat, sub] = (f.cat || '').split('|')
    const body: any = {
      date: f.date, type: f.type, amount: f.amount.replace(/,/g, ''), category_id: cat || null, subcategory_id: sub || null, description: f.description, merchant: f.merchant || null,
      account_id: f.account_id || null, to_account_id: f.to_account_id || null, project_id: f.project_id || null, department_id: f.department_id || null, member_id: f.member_id || null,
      shared: f.shared, notes: f.notes || null, refund_of_id: f.refund_of_id || null, dimensions: f.dimensions, allow_duplicate: allow, submit,
      splits: [...splits.filter((s) => s.amount).map((s) => ({ project_id: s.project_id || null, amount: s.amount })), ...(f.shared ? shares.filter((s) => s.member_id && s.amount).map((s) => ({ member_id: s.member_id, amount: s.amount })) : [])],
    }
    try {
      const r = initial ? await api(`/transactions/${initial.id}`, { method: 'PATCH', body }) : await api('/transactions', { body })
      onDone(r)
    } catch (x) {
      if (x instanceof ApiError && x.detail?.code === 'DUPLICATE') setDup(x.detail)
      else setErr(errText(x))
    }
    setBusy(false)
  }
  const sum = splits.reduce((s, x) => s + (Number(x.amount) || 0), 0)
  const shareSum = shares.reduce((s, x) => s + (Number(x.amount) || 0), 0)
  const splitEqually = () => {
    const total = Math.round(Number(f.amount || 0) * 100)
    const who = L.members.filter((m: any) => m.role !== 'family_viewer')
    if (!total || !who.length) return
    const base = Math.floor(total / who.length)
    setShares(who.map((m: any, i: number) => ({ member_id: m.id, amount: ((base + (i === 0 ? total - base * who.length : 0)) / 100).toFixed(2) })))
  }
  const types = initial ? [f.type] : claim ? ['expense'] : ['expense', 'income', 'transfer', 'refund', 'reimbursement']
  return (
    <Stack spacing={2} component="form" onSubmit={(e) => { e.preventDefault(); save() }} aria-label="Transaction form">
      {err && <Alert severity="error">{err}</Alert>}
      {dup && (
        <Alert severity="warning" action={<Button color="inherit" size="small" onClick={() => save(true)}>Save anyway</Button>}>
          This looks like a duplicate of a transaction you already recorded. Check before saving again.
        </Alert>
      )}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        {types.length > 1 && <TextField select label="Type" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value, cat: '' })} sx={{ minWidth: 160 }}>{types.map((t) => <MenuItem key={t} value={t}>{t[0].toUpperCase() + t.slice(1)}</MenuItem>)}</TextField>}
        <TextField label="Amount" value={f.amount} onChange={set('amount')} error={!!errs.amount} helperText={errs.amount || 'INR'} inputProps={{ inputMode: 'decimal' }} sx={{ flex: 1 }} autoFocus />
        <TextField label="Date" type="date" value={f.date} onChange={set('date')} error={!!errs.date} helperText={errs.date} InputLabelProps={{ shrink: true }} />
      </Stack>
      {!isTransfer && !isCredit && (
        <TextField select label="Category" value={f.cat} onChange={set('cat')} error={!!errs.cat} helperText={errs.cat}>
          {catOpts.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
        </TextField>
      )}
      {isCredit && (
        <TextField select label="Original expense (linked)" value={f.refund_of_id} onChange={set('refund_of_id')} helperText="Refunds and reimbursements are linked to the expense they reduce">
          <MenuItem value="">Not linked</MenuItem>
          {(expenses.data?.items || []).map((t: any) => <MenuItem key={t.id} value={t.id}>{t.date} · {t.description} · {inr(t.amount_minor)}</MenuItem>)}
        </TextField>
      )}
      <TextField label="Description" value={f.description} onChange={set('description')} />
      {!isTransfer && <TextField label="Merchant / payee" value={f.merchant} onChange={set('merchant')} />}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        {!claim && (
          <TextField select label={isTransfer ? 'From account' : 'Payment account'} value={f.account_id} onChange={set('account_id')} error={!!errs.account_id} helperText={errs.account_id} sx={{ flex: 1 }}>
            {L.accounts.filter((a: any) => a.status === 'active').map((a: any) => <MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>)}
          </TextField>
        )}
        {isTransfer && (
          <TextField select label="To account" value={f.to_account_id} onChange={set('to_account_id')} error={!!errs.to_account_id} helperText={errs.to_account_id} sx={{ flex: 1 }}>
            {L.accounts.filter((a: any) => a.status === 'active').map((a: any) => <MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>)}
          </TextField>
        )}
      </Stack>
      {biz && !isTransfer && (
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <TextField select label="Project" value={f.project_id} onChange={set('project_id')} error={!!errs.project_id} helperText={errs.project_id} sx={{ flex: 1 }}>
            <MenuItem value="">None</MenuItem>{L.projects.filter((p: any) => p.active).map((p: any) => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}
          </TextField>
          {!claim && <TextField select label="Department" value={f.department_id} onChange={set('department_id')} sx={{ flex: 1 }}><MenuItem value="">Default</MenuItem>{L.departments.map((d: any) => <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>)}</TextField>}
        </Stack>
      )}
      {L.dims.length > 0 && f.type === 'expense' && (
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          {L.dims.map((d: any) => (
            <TextField key={d.id} select label={d.name + (d.required ? ' (required)' : ' (optional)')} value={f.dimensions[d.id] || ''} onChange={(e) => setF({ ...f, dimensions: { ...f.dimensions, [d.id]: e.target.value } })} sx={{ flex: 1 }}>
              <MenuItem value="">None</MenuItem>{d.values.map((v: any) => <MenuItem key={v.id} value={v.id}>{v.name}</MenuItem>)}
            </TextField>
          ))}
        </Stack>
      )}
      {!biz && (
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="center">
          {app.can('scope.all') && <TextField select label="Whose expense" value={f.member_id} onChange={set('member_id')} sx={{ flex: 1 }}><MenuItem value="">Me</MenuItem>{L.members.map((m: any) => <MenuItem key={m.id} value={m.id}>{m.name}</MenuItem>)}</TextField>}
          <FormControlLabel control={<Switch checked={f.shared} onChange={set('shared')} />} label="Shared household expense" />
        </Stack>
      )}
      {biz && !claim && f.type === 'expense' && (
        <Box>
          <Button size="small" onClick={() => setSplits([...splits, { project_id: '', amount: '' }])}>Allocate across projects</Button>
          {splits.map((s, i) => (
            <Stack key={i} direction="row" spacing={1} sx={{ mt: 1 }}>
              <TextField select label="Project" value={s.project_id} onChange={(e) => setSplits(splits.map((x, j) => (j === i ? { ...x, project_id: e.target.value } : x)))} sx={{ flex: 1 }}>{L.projects.map((p: any) => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}</TextField>
              <TextField label="Amount" value={s.amount} onChange={(e) => setSplits(splits.map((x, j) => (j === i ? { ...x, amount: e.target.value } : x)))} />
              <IconButton onClick={() => setSplits(splits.filter((_, j) => j !== i))} aria-label="Remove allocation"><CloseIcon /></IconButton>
            </Stack>
          ))}
          {splits.length > 0 && <Typography variant="caption" color={Math.abs(sum - Number(f.amount || 0)) < 0.005 ? 'success.main' : 'error.main'}>Allocated {sum.toFixed(2)} of {Number(f.amount || 0).toFixed(2)} — the total must match exactly</Typography>}
        </Box>
      )}
      {!biz && f.shared && f.type === 'expense' && app.can('scope.all') && (
        <Box>
          <Stack direction="row" spacing={1}><Button size="small" onClick={() => setShares([...shares, { member_id: '', amount: '' }])}>Allocate between family members</Button><Button size="small" onClick={splitEqually}>Split equally</Button></Stack>
          {shares.map((s, i) => (
            <Stack key={i} direction="row" spacing={1} sx={{ mt: 1 }}>
              <TextField select label="Member" value={s.member_id} onChange={(e) => setShares(shares.map((x, j) => (j === i ? { ...x, member_id: e.target.value } : x)))} sx={{ flex: 1 }}>{L.members.filter((m: any) => m.role !== 'family_viewer').map((m: any) => <MenuItem key={m.id} value={m.id}>{m.name}</MenuItem>)}</TextField>
              <TextField label="Share" value={s.amount} onChange={(e) => setShares(shares.map((x, j) => (j === i ? { ...x, amount: e.target.value } : x)))} />
              <IconButton onClick={() => setShares(shares.filter((_, j) => j !== i))} aria-label="Remove share"><CloseIcon /></IconButton>
            </Stack>
          ))}
          {shares.length > 0 && <Typography variant="caption" color={Math.abs(shareSum - Number(f.amount || 0)) < 0.005 ? 'success.main' : 'error.main'}>Allocated {shareSum.toFixed(2)} of {Number(f.amount || 0).toFixed(2)} - shares must add up to the full amount</Typography>}
        </Box>
      )}
      <TextField label="Notes" value={f.notes} onChange={set('notes')} multiline minRows={1} />
      <Stack direction="row" spacing={1} justifyContent="flex-end">
        {onCancel && <Button onClick={onCancel}>Cancel</Button>}
        {claim && !initial && <Button onClick={() => save(false, false)} disabled={busy}>Save as draft</Button>}
        <Button type="submit" variant="contained" disabled={busy}>{claim ? 'Submit for approval' : initial ? 'Save changes' : 'Save'}</Button>
      </Stack>
    </Stack>
  )
}

export function AddTransaction({ type }: { type: string }) {
  const nav = useNavigate()
  const app = useApp()
  const [key, setKey] = useState(0)
  return (
    <Page title={type === 'income' ? 'Add income' : 'Add expense'} subtitle="Record it in a few seconds. Use the AI Assistant to add several at once by typing or speaking.">
      <Paper variant="outlined" sx={{ p: 3, maxWidth: 720 }}>
        <TxnForm key={key} type={type} onDone={() => { app.toast('Saved'); setKey(key + 1); nav('/transactions') }} />
      </Paper>
    </Page>
  )
}

export function TxnDetail({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const app = useApp()
  const { data, loading, error, reload } = useLoad(`/transactions/${id}`)
  const L = useLookups()
  const [editing, setEditing] = useState(false)
  const [reject, setReject] = useState(false)
  const [reason, setReason] = useState('')
  const [pay, setPay] = useState(false)
  const [acct, setAcct] = useState('')
  const [err, setErr] = useState('')
  const act = async (what: string, body: any = {}) => {
    setErr('')
    try { await api(`/transactions/${id}/${what}`, { body }); app.toast(what === 'approve' ? 'Approved' : what === 'pay' ? 'Marked as paid' : what === 'reject' ? 'Rejected' : 'Done'); setReject(false); setPay(false); reload(); onChanged() } catch (x) { setErr(errText(x)) }
  }
  const t = data
  const staff = app.can('txn.edit_any')
  const mine = t && t.created_by === app.me!.membership_id
  const canEdit = t && (staff || (mine && ['draft', 'rejected'].includes(t.status)))
  const canDelete = t && (app.can('txn.delete_any') || (mine && ['draft', 'rejected'].includes(t.status)))
  return (
    <Drawer anchor="right" open onClose={onClose} PaperProps={{ sx: { width: { xs: '100%', sm: 520 }, p: 2 } }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center"><Typography variant="h6">Transaction</Typography><IconButton onClick={onClose} aria-label="Close"><CloseIcon /></IconButton></Stack>
      <State loading={loading} error={error}>
        {t && !editing && (
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            {err && <Alert severity="error">{err}</Alert>}
            <Stack direction="row" justifyContent="space-between"><Typography variant="h5" fontWeight={700}>{inr(t.amount_minor)}</Typography><StatusChip status={t.status} /></Stack>
            <Typography>{t.description || '(no description)'}</Typography>
            <Typography variant="body2" color="text.secondary">{t.date} · {t.type}{t.merchant ? ` · ${t.merchant}` : ''}{t.sample ? ' · sample data' : ''}</Typography>
            <Typography variant="body2">Category: {L.name(L.categories, t.category_id) || '—'}{t.subcategory_id ? ` › ${L.name(L.categories, t.subcategory_id)}` : ''}</Typography>
            <Typography variant="body2">Account: {L.name(L.accounts, t.account_id) || '—'}{t.to_account_id ? ` → ${L.name(L.accounts, t.to_account_id)}` : ''}</Typography>
            {t.project_id && <Typography variant="body2">Project: {L.name(L.projects, t.project_id)}</Typography>}
            {t.department_id && <Typography variant="body2">Department: {L.name(L.departments, t.department_id)}</Typography>}
            {t.splits?.length > 0 && <Typography variant="body2">Allocated: {t.splits.map((s: any) => `${L.name(L.projects, s.project_id) || 'Unassigned'} ${s.amount}`).join(' · ')}</Typography>}
            {t.reject_reason && <Alert severity="error">Rejected: {t.reject_reason}</Alert>}
            {t.ai_assisted && <Alert severity="info" icon={false}>AI-assisted entry ({t.ai?.source}); confirmed by a person on {t.ai?.confirmed_at?.slice(0, 10)}. Original suggestion confidence {t.ai?.confidence ?? 'n/a'}.</Alert>}
            {t.attachments?.length > 0 && <Typography variant="body2">Attachments: {t.attachments.map((a: any) => a.filename).join(', ')}</Typography>}
            {t.steps?.length > 0 && (
              <>
                <Divider /><Typography variant="subtitle2">Approval trail</Typography>
                {t.steps.map((s: any, i: number) => (
                  <Typography key={i} variant="body2">Level {s.level} · {s.role.replace('_', ' ')} · <b>{s.status}</b>{s.by ? ` by ${s.by}` : ''}{s.reason ? ` — “${s.reason}”` : ''}</Typography>
                ))}
              </>
            )}
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {t.can_act && <Button variant="contained" onClick={() => act('approve')}>{t.steps.find((s: any) => s.status === 'pending')?.role === 'finance' ? 'Verify' : 'Approve'}</Button>}
              {t.can_act && <Button color="error" onClick={() => setReject(true)}>Reject</Button>}
              {app.can('approve.finance') && t.status === 'verified' && !mine && <Button variant="contained" color="success" onClick={() => setPay(true)}>Mark reimbursement paid</Button>}
              {mine && ['draft', 'rejected'].includes(t.status) && t.type === 'expense' && <Button variant="contained" onClick={() => act('submit')}>Submit for approval</Button>}
              {canEdit && <Button onClick={() => setEditing(true)}>Edit</Button>}
              {canDelete && <Button color="error" onClick={async () => { if (confirm('Delete this transaction? This is recorded in the audit history.')) { try { await api(`/transactions/${id}`, { method: 'DELETE' }); onChanged(); onClose() } catch (x) { setErr(errText(x)) } } }}>Delete</Button>}
            </Stack>
            <Divider /><Typography variant="subtitle2">History</Typography>
            {t.history.map((h: any, i: number) => <Typography key={i} variant="caption" display="block">{h.at.slice(0, 16).replace('T', ' ')} · {h.by} · {h.action.replace('_', ' ')}</Typography>)}
          </Stack>
        )}
        {t && editing && <Box sx={{ mt: 2 }}><TxnForm initial={t} onDone={() => { setEditing(false); reload(); onChanged(); app.toast('Saved') }} onCancel={() => setEditing(false)} /></Box>}
      </State>
      <Dialog open={reject} onClose={() => setReject(false)} fullWidth maxWidth="xs">
        <DialogTitle>Reject expense</DialogTitle>
        <DialogContent><TextField autoFocus fullWidth multiline minRows={2} label="Reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} sx={{ mt: 1 }} />{err && <Alert severity="error" sx={{ mt: 1 }}>{err}</Alert>}</DialogContent>
        <DialogActions><Button onClick={() => setReject(false)}>Cancel</Button><Button color="error" variant="contained" onClick={() => act('reject', { reason })}>Reject</Button></DialogActions>
      </Dialog>
      <Dialog open={pay} onClose={() => setPay(false)} fullWidth maxWidth="xs">
        <DialogTitle>Mark reimbursement paid</DialogTitle>
        <DialogContent><TextField select fullWidth label="Paid from account" value={acct} onChange={(e) => setAcct(e.target.value)} sx={{ mt: 1 }}>{L.accounts.filter((a: any) => a.status === 'active' && a.type !== 'credit_card').map((a: any) => <MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>)}</TextField>{err && <Alert severity="error" sx={{ mt: 1 }}>{err}</Alert>}</DialogContent>
        <DialogActions><Button onClick={() => setPay(false)}>Cancel</Button><Button variant="contained" color="success" onClick={() => act('pay', { account_id: acct })}>Confirm payment</Button></DialogActions>
      </Dialog>
    </Drawer>
  )
}

export function Transactions({ mineOnly }: { mineOnly?: boolean }) {
  const app = useApp()
  const L = useLookups()
  const [f, setF] = useState<any>({ q: '', type: '', category_id: '', account_id: '', project_id: '', status: '', date_from: '', date_to: '', member_id: '' })
  const [page, setPage] = useState(0)
  const [size, setSize] = useState(25)
  const [open, setOpen] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [imp, setImp] = useState(false)
  const path = `/transactions${qs({ ...f, mine: mineOnly || undefined, page: page + 1, page_size: size })}`
  const { data, loading, error, reload } = useLoad(path)
  const biz = app.me!.tenant.edition === 'business'
  const set = (k: string) => (e: any) => { setF({ ...f, [k]: e.target.value }); setPage(0) }
  return (
    <Page title={mineOnly ? 'My expenses' : 'Transactions'} subtitle={mineOnly ? 'Expenses you have claimed and where each one stands' : 'Search, filter and open any transaction you are allowed to see'}
      actions={<>
        {app.can('txn.create') && <Button variant="contained" onClick={() => setAdding(true)}>{biz && !app.can('txn.edit_any') ? 'New expense' : 'Add transaction'}</Button>}
        {app.can('txn.import') && <Button startIcon={<UploadIcon />} onClick={() => setImp(true)}>Import CSV</Button>}
        {app.can('txn.export') && <Button startIcon={<DownloadIcon />} onClick={() => download(`/transactions/export${qs({ ...f, mine: mineOnly || undefined })}`, 'transactions.csv')}>Export CSV</Button>}
      </>}>
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
          <TextField label="Search" value={f.q} onChange={set('q')} sx={{ minWidth: 200 }} />
          <TextField select label="Type" value={f.type} onChange={set('type')} sx={{ minWidth: 130 }}><MenuItem value="">All</MenuItem>{['income', 'expense', 'transfer', 'refund', 'reimbursement'].map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}</TextField>
          <TextField select label="Category" value={f.category_id} onChange={set('category_id')} sx={{ minWidth: 160 }}><MenuItem value="">All</MenuItem>{L.categories.filter((c: any) => !c.parent_id).map((c: any) => <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>)}</TextField>
          {app.can('scope.all') && <TextField select label="Account" value={f.account_id} onChange={set('account_id')} sx={{ minWidth: 160 }}><MenuItem value="">All</MenuItem>{L.accounts.map((c: any) => <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>)}</TextField>}
          {!biz && app.can('scope.all') && <TextField select label="Member" value={f.member_id} onChange={set('member_id')} sx={{ minWidth: 150 }}><MenuItem value="">All</MenuItem>{L.members.map((c: any) => <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>)}</TextField>}
          {biz && <TextField select label="Project" value={f.project_id} onChange={set('project_id')} sx={{ minWidth: 170 }}><MenuItem value="">All</MenuItem>{L.projects.map((c: any) => <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>)}</TextField>}
          {biz && <TextField select label="Status" value={f.status} onChange={set('status')} sx={{ minWidth: 150 }}><MenuItem value="">All</MenuItem>{['draft', 'submitted', 'pm_approved', 'verified', 'paid', 'posted', 'rejected'].map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}</TextField>}
          <TextField label="From" type="date" value={f.date_from} onChange={set('date_from')} InputLabelProps={{ shrink: true }} />
          <TextField label="To" type="date" value={f.date_to} onChange={set('date_to')} InputLabelProps={{ shrink: true }} />
        </Stack>
      </Paper>
      <State loading={loading && !data} error={error}>
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="Transactions">
            <TableHead><TableRow><TableCell>Date</TableCell><TableCell>Description</TableCell><TableCell>Category</TableCell>{biz && <TableCell>Project</TableCell>}<TableCell>Type</TableCell>{biz && <TableCell>Status</TableCell>}<TableCell align="right">Amount</TableCell></TableRow></TableHead>
            <TableBody>
              {(data?.items || []).map((t: any) => (
                <TableRow key={t.id} hover onClick={() => setOpen(t.id)} sx={{ cursor: 'pointer' }} data-testid={`txn-row`}>
                  <TableCell>{t.date}</TableCell>
                  <TableCell>{t.description}{t.shared && <Chip size="small" label="shared" sx={{ ml: 1 }} />}{t.ai_assisted && <Chip size="small" color="secondary" variant="outlined" label="AI" sx={{ ml: 1 }} />}</TableCell>
                  <TableCell>{L.name(L.categories, t.category_id)}</TableCell>
                  {biz && <TableCell>{L.name(L.projects, t.project_id)}</TableCell>}
                  <TableCell>{t.type}</TableCell>
                  {biz && <TableCell><StatusChip status={t.status} /></TableCell>}
                  <TableCell align="right" sx={{ fontWeight: 600, color: ['income', 'refund', 'reimbursement'].includes(t.type) ? 'success.main' : undefined }}>{t.type === 'expense' ? '−' : ['income', 'refund', 'reimbursement'].includes(t.type) ? '+' : ''}{inr(t.amount_minor)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {data && data.items.length === 0 && <Empty text="No transactions match these filters." />}
          <TablePagination component="div" count={data?.total || 0} page={page} onPageChange={(_, p) => setPage(p)} rowsPerPage={size} onRowsPerPageChange={(e) => { setSize(+e.target.value); setPage(0) }} rowsPerPageOptions={[10, 25, 50, 100]} />
        </TableContainer>
      </State>
      {open && <TxnDetail id={open} onClose={() => setOpen(null)} onChanged={reload} />}
      <Dialog open={adding} onClose={() => setAdding(false)} fullWidth maxWidth="sm">
        <DialogTitle>{biz && !app.can('txn.edit_any') ? 'New expense claim' : 'Add transaction'}</DialogTitle>
        <DialogContent sx={{ pt: 1 }}><Box sx={{ pt: 1 }}><TxnForm onDone={() => { setAdding(false); reload(); app.reload(); app.toast(biz && !app.can('txn.edit_any') ? 'Submitted for approval' : 'Saved') }} onCancel={() => setAdding(false)} /></Box></DialogContent>
      </Dialog>
      <ImportDialog open={imp} onClose={() => setImp(false)} onDone={reload} />
    </Page>
  )
}

function ImportDialog({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const app = useApp()
  const [file, setFile] = useState<File | null>(null)
  const [res, setRes] = useState<any>(null)
  const [err, setErr] = useState('')
  const run = async (commit: boolean) => {
    if (!file) return
    const form = new FormData(); form.append('file', file)
    try { const r = await api(`/transactions/import?commit=${commit}`, { method: 'POST', form }); setRes(r); setErr(''); if (commit) { app.toast(`${r.created} transactions imported`); onDone(); onClose() } } catch (x) { setErr(errText(x)) }
  }
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Import transactions from CSV</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 1 }}>Columns: date (YYYY-MM-DD), type, amount, category, description, merchant, account. Preview first — rows with errors or duplicates are skipped and reported.</Typography>
        <input type="file" accept=".csv" onChange={(e) => { setFile(e.target.files?.[0] || null); setRes(null) }} aria-label="CSV file" />
        {err && <Alert severity="error" sx={{ mt: 1 }}>{err}</Alert>}
        {res && <Box sx={{ mt: 2 }}><Alert severity={res.skipped ? 'warning' : 'success'}>{res.ok} ready · {res.skipped} skipped</Alert>{res.rows.filter((r: any) => r.status !== 'ok').map((r: any) => <Typography key={r.row} variant="body2">Row {r.row}: {r.message}</Typography>)}</Box>}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Close</Button><Button onClick={() => run(false)} disabled={!file}>Preview</Button><Button variant="contained" onClick={() => run(true)} disabled={!file || !res || !res.ok}>Import {res?.ok ?? ''} rows</Button></DialogActions>
    </Dialog>
  )
}
