import { useState, type ReactNode } from 'react'
import { Link as RouterLink, useNavigate, useSearchParams } from 'react-router-dom'
import { Alert, Box, Button, Chip, Link, MenuItem, Paper, Stack, TextField, Typography, ToggleButton, ToggleButtonGroup, Collapse } from '@mui/material'
import { api, setToken } from '../api'
import { errText, useApp, useLoad } from '../ui'

function Frame({ title, children, wide }: { title: string; children: ReactNode; wide?: boolean }) {
  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', p: 2, bgcolor: 'background.default' }}>
      <Paper sx={{ p: 4, width: '100%', maxWidth: wide ? 920 : 440 }} elevation={2}>
        <Typography variant="h5" fontWeight={800} color="primary">Aadi SpendOS</Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>Know where your money goes. Understand why you spend it.</Typography>
        <Typography variant="h6" component="h1" sx={{ mb: 2 }}>{title}</Typography>
        {children}
      </Paper>
    </Box>
  )
}

export function Login() {
  const app = useApp()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [showDemo, setShowDemo] = useState(false)
  const demo = useLoad(showDemo ? '/demo/accounts' : null)
  const cfg = useLoad('/auth/config')
  const submit = async (e?: any) => {
    e?.preventDefault()
    setBusy(true); setErr('')
    try {
      const r = await api('/auth/login', { body: { email, password } })
      setToken(r.token); await app.reload(); nav('/')
    } catch (x) { setErr(errText(x)) }
    setBusy(false)
  }
  const groups: Record<string, any[]> = {}
  ;(demo.data?.accounts || []).forEach((a: any) => (groups[a.tenant] ||= []).push(a))
  return (
    <Frame title="Sign in" wide={showDemo}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={4}>
        <Box component="form" onSubmit={submit} sx={{ flex: 1 }}>
          <Stack spacing={2}>
            {err && <Alert severity="error">{err}</Alert>}
            <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus autoComplete="username" required />
            <TextField label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
            <Button type="submit" variant="contained" disabled={busy}>Sign in</Button>
            <Stack direction="row" justifyContent="space-between">
              <Link component={RouterLink} to="/forgot">Forgot password?</Link>
              {cfg.data?.registration !== false && <Link component={RouterLink} to="/register">Create an account</Link>}
            </Stack>
            {cfg.data?.registration === false && <Typography variant="caption" color="text.secondary">Accounts are by invitation. Ask your administrator to invite you.</Typography>}
            {cfg.data?.demo && <Button size="small" onClick={() => setShowDemo((s) => !s)} data-testid="toggle-demo">{showDemo ? 'Hide' : 'Show'} demo accounts</Button>}
          </Stack>
        </Box>
        <Collapse in={showDemo} orientation="horizontal" unmountOnExit sx={{ flex: showDemo ? 1.4 : 0 }}>
          <Box sx={{ minWidth: 380, maxHeight: 420, overflow: 'auto' }} data-testid="demo-accounts">
            <Alert severity="info" sx={{ mb: 1 }}>Demo environment only. All people and data are synthetic. Choose a persona to fill the sign-in form.</Alert>
            {demo.error && <Alert severity="warning">Demo accounts are not available in this environment.</Alert>}
            {Object.entries(groups).map(([tenant, list]) => (
              <Box key={tenant} sx={{ mb: 1.5 }}>
                <Typography variant="subtitle2">{tenant}</Typography>
                {list.map((a) => (
                  <Stack key={a.email} direction="row" alignItems="center" spacing={1} sx={{ py: 0.3 }}>
                    <Button size="small" variant="outlined" onClick={() => { setEmail(a.email); setPassword(demo.data.password_hint) }} aria-label={`Use ${a.name}`}>Use</Button>
                    <Typography variant="body2" sx={{ flex: 1 }}>{a.name}</Typography>
                    <Chip size="small" label={a.role} />
                  </Stack>
                ))}
              </Box>
            ))}
          </Box>
        </Collapse>
      </Stack>
    </Frame>
  )
}

export function Register() {
  const app = useApp()
  const nav = useNavigate()
  const cfg = useLoad('/auth/config')
  const tpl = useLoad('/templates')
  const [f, setF] = useState({ name: '', email: '', password: '', edition: 'personal', template: 'personal', organization_name: '' })
  const [err, setErr] = useState('')
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value })
  const submit = async (e: any) => {
    e.preventDefault(); setErr('')
    try { const r = await api('/auth/register', { body: f }); setToken(r.token); await app.reload(); nav('/'); app.toast('Welcome! Your starter categories and an account are ready.') } catch (x) { setErr(errText(x)) }
  }
  const templates = (tpl.data || []).filter((t: any) => t.edition === f.edition)
  if (cfg.data?.registration === false) return <Frame title="Invitation only"><Alert severity="info">Self-registration is turned off. Ask your administrator to invite you; you will receive an email with a link to choose your password.</Alert><Link component={RouterLink} to="/" sx={{ display: 'block', mt: 2 }}>Back to sign in</Link></Frame>
  return (
    <Frame title="Create your account">
      <Box component="form" onSubmit={submit}>
        <Stack spacing={2}>
          {err && <Alert severity="error">{err}</Alert>}
          <ToggleButtonGroup exclusive fullWidth value={f.edition} onChange={(_, v) => v && setF({ ...f, edition: v, template: v === 'personal' ? 'personal' : 'it_company' })} aria-label="Edition">
            <ToggleButton value="personal">Personal / Family</ToggleButton>
            <ToggleButton value="business">Business</ToggleButton>
          </ToggleButtonGroup>
          <TextField label="Your name" value={f.name} onChange={set('name')} required />
          <TextField label="Email" type="email" value={f.email} onChange={set('email')} required />
          <TextField label="Password" type="password" value={f.password} onChange={set('password')} helperText="At least 8 characters with letters and numbers" required />
          <TextField select label="Configuration template" value={f.template} onChange={set('template')} helperText="Copied into your own settings; later template changes never overwrite yours">
            {templates.map((t: any) => <MenuItem key={t.code} value={t.code}>{t.label}</MenuItem>)}
          </TextField>
          {f.edition === 'business' && <TextField label="Organization name" value={f.organization_name} onChange={set('organization_name')} required />}
          <Button type="submit" variant="contained">Create account</Button>
          <Link component={RouterLink} to="/">Back to sign in</Link>
        </Stack>
      </Box>
    </Frame>
  )
}

export function Forgot() {
  const [sp] = useSearchParams()
  const linkToken = sp.get('token') || ''
  const [email, setEmail] = useState('')
  const [token, setTokenV] = useState(linkToken)
  const [password, setPassword] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [stage, setStage] = useState(linkToken ? 2 : 1)
  const ask = async (e: any) => {
    e.preventDefault(); setErr('')
    try { const r = await api('/auth/forgot', { body: { email } }); setMsg(r.message); if (r.demo_reset_token) { setTokenV(r.demo_reset_token); setMsg(r.message + ' (Demo mode: no mail server, so the reset code is filled in for you.)') } setStage(2) } catch (x) { setErr(errText(x)) }
  }
  const reset = async (e: any) => {
    e.preventDefault(); setErr('')
    try { await api('/auth/reset', { body: { token, password } }); setMsg('Password saved. You can sign in now.'); setStage(3) } catch (x) { setErr(errText(x)) }
  }
  return (
    <Frame title={linkToken ? 'Choose your password' : 'Reset your password'}>
      <Stack spacing={2} component="form" onSubmit={stage === 1 ? ask : reset}>
        {err && <Alert severity="error">{err}</Alert>}
        {msg && <Alert severity="info">{msg}</Alert>}
        {stage === 1 && <><TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /><Button type="submit" variant="contained">Send reset link</Button></>}
        {stage === 2 && <>{!linkToken && <TextField label="Reset code" value={token} onChange={(e) => setTokenV(e.target.value)} required />}<TextField label="New password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /><Button type="submit" variant="contained">Save password</Button></>}
        <Link component={RouterLink} to="/">Back to sign in</Link>
      </Stack>
    </Frame>
  )
}
