import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, MenuItem, Paper, Stack, Switch, Tab, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tabs, TextField, Typography,
} from '@mui/material'
import { api, download } from '../api'
import { Card, Empty, Page, State, inr, useApp, useLoad } from '../ui'
import { FormDialog } from './Setup'
import { useLookups } from './Transactions'

const ROLES = [['org_admin', 'Organization Admin'], ['finance_manager', 'Finance Manager'], ['department_manager', 'Department Manager'], ['project_manager', 'Project Manager'], ['employee', 'Employee'], ['auditor', 'Auditor']]

function Members() {
  const app = useApp()
  const { data, loading, error, reload } = useLoad('/members')
  const L = useLookups()
  const [dlg, setDlg] = useState<any>(null)
  const [issued, setIssued] = useState<any>(null)
  return (
    <State loading={loading} error={error}>
      {app.can('member.manage') && <Button variant="contained" sx={{ mb: 2 }} onClick={() => setDlg({ name: '', email: '', role: 'employee', department_id: '', project_ids: [] })}>Invite member</Button>}
      <TableContainer component={Paper} variant="outlined"><Table size="small" aria-label="Members">
        <TableHead><TableRow><TableCell>Name</TableCell><TableCell>Role</TableCell><TableCell>Department</TableCell><TableCell>Projects</TableCell><TableCell>Status</TableCell></TableRow></TableHead>
        <TableBody>{data?.map((m: any) => (
          <TableRow key={m.id}><TableCell>{m.name}<br /><Typography variant="caption" color="text.secondary">{m.email}</Typography></TableCell><TableCell>{m.role_label}</TableCell><TableCell>{L.name(L.departments, m.department_id)}</TableCell>
            <TableCell>{m.project_ids.map((p: string) => L.name(L.projects, p)).join(', ')}</TableCell><TableCell>{m.status}</TableCell></TableRow>))}</TableBody></Table></TableContainer>
      {dlg && <FormDialog open title="Invite member" onClose={() => setDlg(null)} submitLabel="Create member" onSubmit={async () => { const r = await api('/members', { body: { ...dlg, department_id: dlg.department_id || null } }); setDlg(null); setIssued(r); reload() }}>
        <TextField label="Name" value={dlg.name} onChange={(e) => setDlg({ ...dlg, name: e.target.value })} required autoFocus />
        <TextField label="Email" type="email" value={dlg.email} onChange={(e) => setDlg({ ...dlg, email: e.target.value })} required />
        <TextField select label="Role" value={dlg.role} onChange={(e) => setDlg({ ...dlg, role: e.target.value })}>{ROLES.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}</TextField>
        <TextField select label="Department" value={dlg.department_id} onChange={(e) => setDlg({ ...dlg, department_id: e.target.value })}><MenuItem value="">None</MenuItem>{L.departments.map((d: any) => <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>)}</TextField>
        <TextField select SelectProps={{ multiple: true }} label="Projects" value={dlg.project_ids} onChange={(e) => setDlg({ ...dlg, project_ids: e.target.value })}>{L.projects.map((p: any) => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}</TextField>
      </FormDialog>}
      <Dialog open={!!issued} onClose={() => setIssued(null)}><DialogTitle>Member created</DialogTitle><DialogContent>{issued?.invite_emailed ? <Typography>{issued.note}</Typography> : issued?.temporary_password ? <Typography>Temporary password (shown once, share securely): <b>{issued.temporary_password}</b></Typography> : <Typography>They already have an account.</Typography>}</DialogContent><DialogActions><Button onClick={() => setIssued(null)}>Done</Button></DialogActions></Dialog>
    </State>
  )
}

function Notifications() {
  const app = useApp()
  const { data, loading, error, reload } = useLoad('/notifications')
  const labels: Record<string, string> = { budget_alert: 'Budget alerts', approval: 'Pending approvals', rejected: 'Rejected expenses', reimbursement: 'Reimbursement updates', reminder: 'Recurring payment reminders', summary: 'Monthly summary' }
  return (
    <State loading={loading} error={error}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
        <Card title="Your notifications" sx={{ flex: 2 }} action={<Button size="small" onClick={async () => { await api('/notifications/read', { method: 'POST' }); reload(); app.reload() }}>Mark all read</Button>}>
          {data?.items.length === 0 && <Empty text="No notifications." />}
          {data?.items.map((n: any) => <Box key={n.id} sx={{ py: 0.8, borderBottom: 1, borderColor: 'divider', opacity: n.read ? 0.6 : 1 }}><Typography variant="body2" fontWeight={n.read ? 400 : 700}>{n.title}</Typography><Typography variant="caption" color="text.secondary">{n.body}</Typography></Box>)}
        </Card>
        <Card title="Preferences" sx={{ flex: 1 }}>
          {data && Object.entries(data.preferences).map(([k, v]) => (
            <FormControlLabel key={k} sx={{ display: 'block' }} label={labels[k]} control={<Switch checked={!!v} onChange={async (e) => { await api('/notifications/preferences', { method: 'PUT', body: { ...data.preferences, [k]: e.target.checked } }); reload() }} />} />
          ))}
        </Card>
      </Stack>
    </State>
  )
}

function Dimensions() {
  const app = useApp()
  const { data, loading, error, reload } = useLoad('/dimensions')
  const [dim, setDim] = useState<any>(null)
  const [val, setVal] = useState<any>(null)
  if (!app.has('growth_dimensions')) return <Alert severity="info">Marketing &amp; sales dimensions are not part of your subscription.</Alert>
  return (
    <State loading={loading} error={error}>
      <Alert severity="info" sx={{ mb: 2 }}>Campaign, channel or initiative are configurable dimensions — they are stored as tags on transactions, not as fixed columns, and are optional unless you make them required.</Alert>
      {app.can('config.manage') && <Button variant="contained" sx={{ mb: 2 }} onClick={() => setDim({ key: '', name: '', required: false })}>Add dimension</Button>}
      <Stack spacing={2}>{data?.map((d: any) => (
        <Card key={d.id} title={`${d.name}${d.required ? ' · required on expenses' : ' · optional'}`} action={app.can('config.manage') && <Button size="small" onClick={() => setVal({ dimension_id: d.id, name: '' })}>Add value</Button>}>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>{d.values.map((v: any) => <Chip key={v.id} label={v.name} onDelete={app.can('config.manage') ? async () => { await api(`/dimensions/values/${v.id}`, { method: 'DELETE' }); reload() } : undefined} />)}</Stack>
        </Card>))}</Stack>
      {dim && <FormDialog open title="Add dimension" onClose={() => setDim(null)} onSubmit={async () => { await api('/dimensions', { body: dim }); setDim(null); reload() }}>
        <TextField label="Key (e.g. initiative)" value={dim.key} onChange={(e) => setDim({ ...dim, key: e.target.value })} required autoFocus /><TextField label="Display name" value={dim.name} onChange={(e) => setDim({ ...dim, name: e.target.value })} required />
        <FormControlLabel control={<Switch checked={dim.required} onChange={(e) => setDim({ ...dim, required: e.target.checked })} />} label="Required on every expense" /></FormDialog>}
      {val && <FormDialog open title="Add value" onClose={() => setVal(null)} onSubmit={async () => { await api(`/dimensions/${val.dimension_id}/values`, { body: { name: val.name } }); setVal(null); reload() }}>
        <TextField label="Value name" value={val.name} onChange={(e) => setVal({ ...val, name: e.target.value })} required autoFocus /></FormDialog>}
    </State>
  )
}

function Policies() {
  const app = useApp()
  const { data, loading, error, reload } = useLoad('/policies')
  const L = useLookups()
  const [dlg, setDlg] = useState<any>(null)
  return (
    <State loading={loading} error={error}>
      <Alert severity="info" sx={{ mb: 2 }}>Rules are evaluated on the server when an expense is submitted: the most specific matching policy (project, then department, then amount range) decides the approval levels.</Alert>
      {app.can('config.manage') && <Button variant="contained" sx={{ mb: 2 }} onClick={() => setDlg({ name: '', min_amount: '0', max_amount: '', levels: ['project_manager', 'finance'], project_id: '', department_id: '' })}>New policy</Button>}
      <TableContainer component={Paper} variant="outlined"><Table size="small" aria-label="Approval policies"><TableHead><TableRow><TableCell>Policy</TableCell><TableCell>Amount range</TableCell><TableCell>Applies to</TableCell><TableCell>Approval levels</TableCell></TableRow></TableHead>
        <TableBody>{data?.map((p: any) => <TableRow key={p.id}><TableCell>{p.name}</TableCell><TableCell>{inr(p.min_minor)} – {p.max_minor ? inr(p.max_minor) : 'no limit'}</TableCell><TableCell>{L.name(L.projects, p.project_id) || L.name(L.departments, p.department_id) || 'All'}</TableCell>
          <TableCell>{p.levels.map((l: string, i: number) => <Chip key={i} size="small" label={`${i + 1}. ${l.replace('_', ' ')}`} sx={{ mr: 0.5 }} />)}</TableCell></TableRow>)}</TableBody></Table></TableContainer>
      {dlg && <FormDialog open title="New approval policy" onClose={() => setDlg(null)} onSubmit={async () => { await api('/policies', { body: { ...dlg, max_amount: dlg.max_amount || null, project_id: dlg.project_id || null, department_id: dlg.department_id || null } }); setDlg(null); reload(); app.toast('Policy created') }}>
        <TextField label="Name" value={dlg.name} onChange={(e) => setDlg({ ...dlg, name: e.target.value })} required autoFocus />
        <Stack direction="row" spacing={1}><TextField label="From amount" value={dlg.min_amount} onChange={(e) => setDlg({ ...dlg, min_amount: e.target.value })} /><TextField label="Up to (blank = no limit)" value={dlg.max_amount} onChange={(e) => setDlg({ ...dlg, max_amount: e.target.value })} /></Stack>
        <TextField select SelectProps={{ multiple: true }} label="Approval levels (in order selected)" value={dlg.levels} onChange={(e) => setDlg({ ...dlg, levels: e.target.value })}>{['department_manager', 'project_manager', 'finance'].map((l) => <MenuItem key={l} value={l}>{l.replace('_', ' ')}</MenuItem>)}</TextField>
        <TextField select label="Only for project" value={dlg.project_id} onChange={(e) => setDlg({ ...dlg, project_id: e.target.value })}><MenuItem value="">Any</MenuItem>{L.projects.map((p: any) => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}</TextField>
      </FormDialog>}
    </State>
  )
}

function Audit() {
  const { data, loading, error } = useLoad('/audit?limit=150')
  return (
    <State loading={loading} error={error}>
      <TableContainer component={Paper} variant="outlined"><Table size="small" aria-label="Audit log"><TableHead><TableRow><TableCell>When</TableCell><TableCell>Who</TableCell><TableCell>What</TableCell><TableCell>Detail</TableCell></TableRow></TableHead>
        <TableBody>{data?.map((a: any) => <TableRow key={a.id}><TableCell>{a.at.slice(0, 16).replace('T', ' ')}</TableCell><TableCell>{a.actor}</TableCell><TableCell>{a.entity} · {a.action.replace('_', ' ')}</TableCell><TableCell sx={{ maxWidth: 380 }}><Typography variant="caption" sx={{ wordBreak: 'break-word' }}>{JSON.stringify(a.detail)}</Typography></TableCell></TableRow>)}</TableBody></Table></TableContainer>
    </State>
  )
}

function Recurring() {
  const app = useApp()
  const { data, loading, error, reload } = useLoad('/recurring')
  const L = useLookups()
  const [dlg, setDlg] = useState<any>(null)
  const manage = app.can('config.manage') || app.can('budget.manage')
  return (
    <State loading={loading} error={error}>
      <Alert severity="info" sx={{ mb: 2 }}>Payments you expect every month. Three days before each one, the people who manage money get a reminder, and early each month they get the previous month summary. Each reminder is sent once.</Alert>
      {manage && <Button variant="contained" sx={{ mb: 2 }} onClick={() => setDlg({ description: '', amount: '', day_of_month: 1, category_id: '' })}>Add recurring payment</Button>}
      <TableContainer component={Paper} variant="outlined"><Table size="small" aria-label="Recurring payments">
        <TableHead><TableRow><TableCell>Payment</TableCell><TableCell>Day of month</TableCell><TableCell>Category</TableCell><TableCell align="right">Amount</TableCell><TableCell /></TableRow></TableHead>
        <TableBody>{data?.map((r: any) => <TableRow key={r.id}><TableCell>{r.description}</TableCell><TableCell>{r.day_of_month}</TableCell><TableCell>{r.category || '—'}</TableCell><TableCell align="right">{inr(r.amount_minor)}</TableCell>
          <TableCell align="right">{manage && <Button size="small" color="error" onClick={async () => { await api(`/recurring/${r.id}`, { method: 'DELETE' }); reload() }}>Remove</Button>}</TableCell></TableRow>)}</TableBody></Table>
        {data?.length === 0 && <Empty text="No recurring payments yet." />}</TableContainer>
      {dlg && <FormDialog open title="Add recurring payment" onClose={() => setDlg(null)} onSubmit={async () => { await api('/recurring', { body: { ...dlg, day_of_month: Number(dlg.day_of_month), category_id: dlg.category_id || null } }); setDlg(null); reload(); app.toast('Recurring payment added') }}>
        <TextField label="What is it for?" value={dlg.description} onChange={(e) => setDlg({ ...dlg, description: e.target.value })} required autoFocus />
        <TextField label="Amount" value={dlg.amount} onChange={(e) => setDlg({ ...dlg, amount: e.target.value })} required />
        <TextField label="Day of month (1-31)" type="number" value={dlg.day_of_month} onChange={(e) => setDlg({ ...dlg, day_of_month: e.target.value })} required />
        <TextField select label="Category" value={dlg.category_id} onChange={(e) => setDlg({ ...dlg, category_id: e.target.value })}><MenuItem value="">None</MenuItem>{L.categories.filter((c: any) => !c.parent_id && c.kind === 'expense').map((c: any) => <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>)}</TextField>
      </FormDialog>}
    </State>
  )
}

function Privacy() {
  const [pw, setPw] = useState<string | null>(null)
  return (
    <Stack spacing={2} sx={{ maxWidth: 720 }}>
      <Card title="Download my data">
        <Typography variant="body2" sx={{ mb: 1 }}>A JSON file with your profile, your memberships and the transactions your role lets you see in this workspace.</Typography>
        <Button variant="outlined" onClick={() => download('/me/export', 'my-spendos-data.json')}>Download my data</Button>
      </Card>
      <Card title="Delete my account">
        <Typography variant="body2" sx={{ mb: 1 }}>Your sign-in is closed and your name and email are removed. If you are the only member of a workspace, the whole workspace and its records are deleted. If you administer a workspace with other members you must hand over the administrator role first. Records that belong to an organization stay in its audit trail. Demo accounts cannot be deleted.</Typography>
        <Button color="error" variant="outlined" onClick={() => setPw('')}>Delete my account</Button>
      </Card>
      {pw !== null && <FormDialog open title="Delete my account" submitLabel="Delete permanently" onClose={() => setPw(null)} onSubmit={async () => { await api('/me/delete', { body: { password: pw } }); sessionStorage.removeItem('spendos.token'); window.location.assign('/') }}>
        <Alert severity="warning">This cannot be undone.</Alert>
        <TextField label="Confirm with your password" type="password" value={pw} onChange={(e) => setPw(e.target.value)} required autoFocus />
      </FormDialog>}
    </Stack>
  )
}

function Plan() {
  const app = useApp()
  const mods = ['transactions', 'accounts', 'categories', 'budgets', 'approvals', 'org_structure', 'reports', 'audit', 'growth_dimensions', 'growth_spend', 'growth_import', 'ai_capture', 'ai_insights', 'ai_anomaly', 'ai_forecast']
  const pillar = (m: string) => (m.startsWith('growth') ? 'Pillar 2 · Marketing & Sales' : m.startsWith('ai') ? 'Pillar 3 · AI Solutions' : 'Pillar 1 · Software Product')
  const usage = useLoad(app.can('audit.read') ? '/usage' : null)
  return (
    <Stack spacing={2}>
      <Card title={`Plan: ${app.me!.tenant.plan_code.replace('_', ' ')}`}>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>{mods.map((m) => <Chip key={m} label={`${m.replace('_', ' ')} · ${pillar(m).split(' · ')[0]}`} color={app.has(m) ? 'success' : 'default'} variant={app.has(m) ? 'filled' : 'outlined'} />)}</Stack>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>Green = available to this organization. Availability is enforced by the server for every protected operation; a platform administrator can change it.</Typography>
      </Card>
      {usage.data && <Card title="Your adoption by pillar"><Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>{Object.entries(usage.data).map(([k, v]: any) => <Box key={k}><Typography variant="h5" fontWeight={800}>{v}</Typography><Typography variant="caption" color="text.secondary">{k.replace('_', ' ')}</Typography></Box>)}</Stack></Card>}
    </Stack>
  )
}

export function OrgSettings() {
  const app = useApp()
  const [sp, setSp] = useSearchParams()
  const biz = app.me!.tenant.edition === 'business'
  const tabs = [
    ...(app.can('member.manage') || biz ? [['members', biz ? 'Members & roles' : 'Members']] : []),
    ['notifications', 'Notifications'],
    ['recurring', 'Recurring payments'],
    ...(biz && app.has('approvals') ? [['policies', 'Approval policies']] : []),
    ...(biz ? [['dimensions', 'Growth dimensions']] : []),
    ...(app.can('audit.read') ? [['audit', 'Audit log']] : []),
    ['plan', 'Plan & modules'],
    ['privacy', 'Privacy & data'],
  ]
  const tab = sp.get('tab') || tabs[0][0]
  return (
    <Page title={biz ? 'Organization settings' : 'Settings'} subtitle={`${app.me!.tenant.name} · ${app.me!.tenant.config?.template_label || ''}`}>
      <Tabs value={tabs.some((t) => t[0] === tab) ? tab : tabs[0][0]} onChange={(_, v) => setSp({ tab: v })} variant="scrollable" sx={{ mb: 2 }}>{tabs.map(([v, l]) => <Tab key={v} value={v} label={l} />)}</Tabs>
      {tab === 'members' && <Members />}{tab === 'notifications' && <Notifications />}{tab === 'policies' && <Policies />}{tab === 'dimensions' && <Dimensions />}{tab === 'audit' && <Audit />}{tab === 'plan' && <Plan />}{tab === 'recurring' && <Recurring />}{tab === 'privacy' && <Privacy />}
    </Page>
  )
}
