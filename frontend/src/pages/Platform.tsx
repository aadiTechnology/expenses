import { useState } from 'react'
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Paper, Stack, Switch, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tab, Tabs, TextField, Tooltip, Typography } from '@mui/material'
import { api } from '../api'
import { Card, Page, State, errText, useApp, useLoad } from '../ui'
import { FormDialog } from './Setup'

export default function Platform() {
  const app = useApp()
  const mods = useLoad('/platform/modules')
  const tenants = useLoad('/platform/tenants')
  const usage = useLoad('/platform/usage')
  const [tab, setTab] = useState('modules')
  const [err, setErr] = useState('')
  const [org, setOrg] = useState<any>(null)
  const [created, setCreated] = useState<any>(null)
  const classify = async (code: string, primary: string, secondary: string | null) => {
    try { await api(`/platform/modules/${code}`, { method: 'PATCH', body: { primary_pillar: primary, secondary_pillar: secondary } }); app.toast('Classification changed and audited'); mods.reload() } catch (x) { setErr(errText(x)) }
  }
  const toggle = async (tid: string, code: string, enabled: boolean) => {
    try { await api(`/platform/tenants/${tid}/entitlements/${code}`, { method: 'PUT', body: { enabled, reason: 'Set by platform administrator' } }); app.toast(`Override saved: ${code} ${enabled ? 'enabled' : 'disabled'}`); tenants.reload(); usage.reload() } catch (x) { setErr(errText(x)) }
  }
  const clear = async (tid: string, code: string) => { await api(`/platform/tenants/${tid}/entitlements/${code}`, { method: 'DELETE' }); tenants.reload(); usage.reload() }
  const pillarName: Record<string, string> = { P1: 'Software Product', P2: 'Marketing & Sales', P3: 'AI Solutions' }
  return (
    <Page title="Platform administration" subtitle="Module catalogue, pillar classification and tenant entitlements. No tenant financial records are shown here.">
      {err && <Alert severity="error" onClose={() => setErr('')} sx={{ mb: 2 }}>{err}</Alert>}
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}><Tab value="modules" label="Modules & pillars" /><Tab value="tenants" label="Tenant entitlements" /><Tab value="usage" label="Adoption (aggregated)" /><Tab value="orgs" label="Organizations" /></Tabs>
      {tab === 'modules' && (
        <State loading={mods.loading} error={mods.error}>
          <TableContainer component={Paper} variant="outlined"><Table size="small" aria-label="Module catalogue">
            <TableHead><TableRow><TableCell>Module</TableCell><TableCell>Entitlement key</TableCell><TableCell>Primary pillar</TableCell><TableCell>Secondary</TableCell><TableCell>Priority</TableCell><TableCell>Depends on</TableCell><TableCell>Plans</TableCell></TableRow></TableHead>
            <TableBody>{mods.data?.modules.map((m: any) => (
              <TableRow key={m.code}><TableCell><b>{m.name}</b><Typography variant="caption" display="block" color="text.secondary">{m.description}</Typography></TableCell><TableCell><code>{m.entitlement_key}</code></TableCell>
                <TableCell><TextField select size="small" value={m.primary_pillar} onChange={(e) => classify(m.code, e.target.value, m.secondary_pillar)} slotProps={{ select: { SelectDisplayProps: { 'aria-label': `Primary pillar for ${m.name}` } as any } }}>{['P1', 'P2', 'P3'].map((p) => <MenuItem key={p} value={p}>{p} · {pillarName[p]}</MenuItem>)}</TextField></TableCell>
                <TableCell><TextField select size="small" value={m.secondary_pillar || ''} onChange={(e) => classify(m.code, m.primary_pillar, e.target.value || null)} slotProps={{ select: { SelectDisplayProps: { 'aria-label': `Secondary pillar for ${m.name}` } as any } }}><MenuItem value="">—</MenuItem>{['P1', 'P2', 'P3'].map((p) => <MenuItem key={p} value={p}>{p}</MenuItem>)}</TextField></TableCell>
                <TableCell>{m.priority}</TableCell><TableCell>{m.depends_on.join(', ') || '—'}</TableCell><TableCell>{m.plans.map((p: string) => <Chip key={p} size="small" label={p.replace('_', ' ')} sx={{ mr: 0.5 }} />)}</TableCell></TableRow>))}</TableBody></Table></TableContainer>
        </State>
      )}
      {tab === 'tenants' && (
        <State loading={tenants.loading} error={tenants.error}>
          <Stack spacing={2}>{tenants.data?.map((t: any) => (
            <Card key={t.id} title={`${t.name} · plan ${t.plan_code.replace('_', ' ')}`}>
              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr 1fr' }, gap: 0.5 }}>
                {Object.entries(t.entitlements).map(([code, e]: any) => (
                  <Stack key={code} direction="row" alignItems="center" justifyContent="space-between" sx={{ borderBottom: 1, borderColor: 'divider', py: 0.3 }}>
                    <Box><Typography variant="body2">{code.replace('_', ' ')}</Typography><Tooltip title="Effective decision and why"><Typography variant="caption" color="text.secondary">{e.source}</Typography></Tooltip></Box>
                    <Stack direction="row" alignItems="center">
                      {e.source.startsWith('override') && <Chip size="small" label="clear" onClick={() => clear(t.id, code)} sx={{ mr: 0.5 }} />}
                      <Switch size="small" checked={e.enabled} onChange={(ev) => toggle(t.id, code, ev.target.checked)} slotProps={{ input: { 'aria-label': `${code} for ${t.name}` } as any }} />
                    </Stack>
                  </Stack>))}
              </Box>
            </Card>))}</Stack>
        </State>
      )}
      {tab === 'orgs' && (
        <State loading={tenants.loading} error={tenants.error}>
          <Alert severity="info" sx={{ mb: 2 }}>Onboarding is by invitation: create the workspace here and the first administrator receives an email to choose their password.</Alert>
          <Button variant="contained" sx={{ mb: 2 }} onClick={() => setOrg({ name: '', edition: 'business', template: 'it_company', admin_name: '', admin_email: '' })}>Create organization</Button>
          <TableContainer component={Paper} variant="outlined"><Table size="small" aria-label="Organizations">
            <TableHead><TableRow><TableCell>Organization</TableCell><TableCell>Edition</TableCell><TableCell>Plan</TableCell><TableCell>Demo data</TableCell></TableRow></TableHead>
            <TableBody>{tenants.data?.map((t: any) => <TableRow key={t.id}><TableCell>{t.name}</TableCell><TableCell>{t.edition}</TableCell><TableCell>{t.plan_code.replace('_', ' ')}</TableCell><TableCell>{t.is_demo ? 'yes' : 'no'}</TableCell></TableRow>)}</TableBody></Table></TableContainer>
          {org && <FormDialog open title="Create organization" submitLabel="Create and invite" onClose={() => setOrg(null)} onSubmit={async () => { const r = await api('/platform/organizations', { body: org }); setOrg(null); setCreated(r); tenants.reload() }}>
            <TextField label="Organization name" value={org.name} onChange={(e) => setOrg({ ...org, name: e.target.value })} required autoFocus />
            <TextField select label="Edition" value={org.edition} onChange={(e) => setOrg({ ...org, edition: e.target.value, template: e.target.value === 'personal' ? 'personal' : 'it_company' })}><MenuItem value="business">Business</MenuItem><MenuItem value="personal">Personal</MenuItem></TextField>
            {org.edition === 'business' && <TextField select label="Template" value={org.template} onChange={(e) => setOrg({ ...org, template: e.target.value })}><MenuItem value="it_company">IT Company</MenuItem><MenuItem value="education">Education</MenuItem></TextField>}
            <TextField label="Administrator name" value={org.admin_name} onChange={(e) => setOrg({ ...org, admin_name: e.target.value })} required />
            <TextField label="Administrator email" type="email" value={org.admin_email} onChange={(e) => setOrg({ ...org, admin_email: e.target.value })} required />
          </FormDialog>}
          <Dialog open={!!created} onClose={() => setCreated(null)} fullWidth maxWidth="sm"><DialogTitle>Organization created</DialogTitle><DialogContent>
            {created?.invite_emailed ? <Typography>An invitation email was sent to {created.admin_email}.</Typography>
              : created?.invite_link ? <><Alert severity="warning" sx={{ mb: 1 }}>No mail server is configured, so send this link to {created.admin_email} yourself. It works once and expires in 7 days.</Alert><Typography sx={{ wordBreak: 'break-all' }}>{created.invite_link}</Typography></>
              : <Typography>{created?.admin_email} already has an account; the organization now appears in their workspace menu.</Typography>}
          </DialogContent><DialogActions><Button onClick={() => setCreated(null)}>Done</Button></DialogActions></Dialog>
        </State>
      )}
      {tab === 'usage' && (
        <State loading={usage.loading} error={usage.error}>
          <Card title="Entitled modules by pillar (counts only)"><Stack direction="row" spacing={4}>{Object.entries(usage.data?.entitled_modules_by_pillar || {}).map(([p, n]: any) => <Box key={p}><Typography variant="h4" fontWeight={800}>{n}</Typography><Typography variant="caption">{p} · {pillarName[p]}</Typography></Box>)}</Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{usage.data?.tenants} tenants. Aggregated so no tenant's records are exposed to another.</Typography></Card>
        </State>
      )}
    </Page>
  )
}
