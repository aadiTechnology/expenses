import { useState } from 'react'
import { Alert, Box, Button, Checkbox, Chip, FormControlLabel, IconButton, MenuItem, Paper, Stack, Tab, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tabs, TextField, Typography } from '@mui/material'
import MicIcon from '@mui/icons-material/Mic'
import { api } from '../api'
import { Card, Empty, Page, State, errText, inr, useApp, useLoad } from '../ui'
import { InsightCard } from './Dashboard'
import { categoryOptions, useLookups } from './Transactions'

function Suggestions({ result, onDone }: { result: any; onDone: () => void }) {
  const app = useApp()
  const L = useLookups()
  const [items, setItems] = useState<any[]>(() => result.items.map((i: any) => ({ ...i, include: !i.needs_review && !i.duplicate_of, reviewed: false, cat: i.category_id || '' })))
  const [account, setAccount] = useState('')
  const [err, setErr] = useState('')
  const biz = app.me!.tenant.edition === 'business'
  const claim = biz && !app.can('txn.edit_any')
  const [project, setProject] = useState('')
  const upd = (i: number, patch: any) => setItems(items.map((x, j) => (j === i ? { ...x, ...patch } : x)))
  const confirm = async () => {
    setErr('')
    try {
      const r = await api(`/ai/extractions/${result.extraction_id}/confirm`, { body: { account_id: account || null, items: items.map((i) => ({ ...i, category_id: i.cat || null, project_id: project || null, allow_duplicate: !!i.duplicate_of && i.include })) } })
      app.toast(`${r.created.length} transaction(s) saved after your confirmation`); onDone()
    } catch (x) { setErr(errText(x)) }
  }
  return (
    <Stack spacing={2} data-testid="suggestions">
      <Alert severity="warning">{result.notice} Suggestions are made by a {result.engine}. Lines with low confidence stay unticked until you review them.</Alert>
      {err && <Alert severity="error">{err}</Alert>}
      <TableContainer component={Paper} variant="outlined">
        <Table size="small" aria-label="AI suggestions">
          <TableHead><TableRow><TableCell>Save</TableCell><TableCell>Date</TableCell><TableCell>Description</TableCell><TableCell>Category</TableCell><TableCell align="right">Amount</TableCell><TableCell>Confidence</TableCell><TableCell>Review</TableCell></TableRow></TableHead>
          <TableBody>{items.map((i, n) => (
            <TableRow key={n} sx={{ bgcolor: i.needs_review ? 'warning.50' : undefined }}>
              <TableCell><Checkbox checked={i.include} onChange={(e) => upd(n, { include: e.target.checked })} slotProps={{ input: { 'aria-label': `Save ${i.description}` } as any }} /></TableCell>
              <TableCell><TextField type="date" value={i.date} onChange={(e) => upd(n, { date: e.target.value })} variant="standard" /></TableCell>
              <TableCell><TextField value={i.description} onChange={(e) => upd(n, { description: e.target.value })} variant="standard" />{i.duplicate_of && <Chip size="small" color="warning" label="Possible duplicate" sx={{ ml: 1 }} />}</TableCell>
              <TableCell><TextField select value={i.cat} onChange={(e) => upd(n, { cat: e.target.value.split('|')[0] })} variant="standard" sx={{ minWidth: 150 }}>{categoryOptions(L.categories, i.type === 'income' ? 'income' : 'expense').filter((o) => !o.value.includes('|')).map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}</TextField></TableCell>
              <TableCell align="right"><TextField value={i.amount ?? ''} onChange={(e) => upd(n, { amount: e.target.value })} variant="standard" sx={{ width: 90 }} inputProps={{ style: { textAlign: 'right' } }} /></TableCell>
              <TableCell><Chip size="small" color={i.confidence >= 0.75 ? 'success' : 'warning'} label={`${Math.round(i.confidence * 100)}%`} /></TableCell>
              <TableCell>{i.needs_review ? <FormControlLabel control={<Checkbox checked={i.reviewed} onChange={(e) => upd(n, { reviewed: e.target.checked, include: e.target.checked })} />} label="I checked this" /> : <Chip size="small" variant="outlined" label="clear" />}</TableCell>
            </TableRow>))}</TableBody>
        </Table>
        {items.length === 0 && <Empty text="Nothing could be extracted. Try rewording, e.g. “vegetables 250, milk 60”." />}
      </TableContainer>
      {items[0]?.note && <Typography variant="caption" color="text.secondary">{items[0].note}</Typography>}
      <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
        {!claim && <TextField select label="Paid from" value={account} onChange={(e) => setAccount(e.target.value)} sx={{ minWidth: 200 }} required>{L.accounts.filter((a: any) => a.status === 'active').map((a: any) => <MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>)}</TextField>}
        {biz && <TextField select label="Project" value={project} onChange={(e) => setProject(e.target.value)} sx={{ minWidth: 200 }}><MenuItem value="">None</MenuItem>{L.projects.map((p: any) => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}</TextField>}
        <Button variant="contained" onClick={confirm} disabled={!items.some((i) => i.include)}>Confirm and save {items.filter((i) => i.include).length} selected</Button>
        <Button onClick={async () => { await api(`/ai/extractions/${result.extraction_id}/discard`, { method: 'POST' }); onDone() }}>Discard all</Button>
      </Stack>
    </Stack>
  )
}

function Capture() {
  const [text, setText] = useState('')
  const [mode, setMode] = useState<'voice' | 'register'>('voice')
  const [res, setRes] = useState<any>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [listening, setListening] = useState(false)
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  const listen = () => {
    const r = new SR(); r.lang = 'en-IN'; r.onresult = (e: any) => setText((t) => (t ? t + ', ' : '') + e.results[0][0].transcript); r.onend = () => setListening(false); setListening(true); r.start()
  }
  const run = async () => { setBusy(true); setErr(''); try { setRes(await api('/ai/parse', { body: { text, source: mode, today: new Date().toISOString().slice(0, 10) } })) } catch (x) { setErr(errText(x)) } setBusy(false) }
  const receipt = async (file?: File | null) => {
    if (!file) return
    setBusy(true); setErr('')
    const form = new FormData(); form.append('file', file)
    try { setRes(await api('/ai/receipt', { method: 'POST', form })) } catch (x) { setErr(errText(x)) }
    setBusy(false)
  }
  if (res) return <Suggestions result={res} onDone={() => { setRes(null); setText('') }} />
  return (
    <Stack spacing={2}>
      {err && <Alert severity="error">{err}</Alert>}
      <Card title="Type or speak your expenses">
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1}><Chip label="Voice / quick text" color={mode === 'voice' ? 'primary' : 'default'} onClick={() => setMode('voice')} /><Chip label="Notebook register lines" color={mode === 'register' ? 'primary' : 'default'} onClick={() => setMode('register')} /></Stack>
          <TextField multiline minRows={mode === 'register' ? 6 : 2} label={mode === 'voice' ? 'What did you spend?' : 'Paste or type lines from your register, one per line'} placeholder={mode === 'voice' ? 'Today vegetables 250, milk 60 and petrol 500' : 'Oct 5 school fees 5000\nOct 6 doctor 600'} value={text} onChange={(e) => setText(e.target.value)} />
          <Stack direction="row" spacing={1}>
            <Button variant="contained" onClick={run} disabled={!text.trim() || busy}>Find expenses</Button>
            {SR && mode === 'voice' && <Button startIcon={<MicIcon />} onClick={listen} disabled={listening}>{listening ? 'Listening…' : 'Speak'}</Button>}
          </Stack>
          {mode === 'register' && <Alert severity="info">Photo upload and handwriting recognition need an OCR service, which is not connected in this version (open decision DEC-04). Type or paste the lines and they go through the same review, confidence and duplicate checks.</Alert>}
        </Stack>
      </Card>
      <Card title="Scan a receipt">
        <Stack spacing={1}>
          <Typography variant="body2" color="text.secondary">Upload a JPG, PNG or PDF (up to 5 MB). Merchant, date, total and tax are suggested; you confirm before anything is saved. Extraction here is simulated and reads text embedded in the file.</Typography>
          <input type="file" accept="image/jpeg,image/png,application/pdf" onChange={(e) => receipt(e.target.files?.[0])} aria-label="Receipt file" />
        </Stack>
      </Card>
    </Stack>
  )
}

function Insights() {
  const app = useApp()
  const { data, loading, error, reload } = useLoad('/ai/insights')
  return (
    <State loading={loading} error={error}>
      <Alert severity="info" sx={{ mb: 2 }}>Insights use only records you are allowed to see. <b>Facts</b> come from posted figures; <b>estimates</b> state their assumptions and are never actual balances; <b>advisory flags</b> are not findings of error or fraud.</Alert>
      <Stack spacing={1.5}>
        {data?.items.map((i: any) => <InsightCard key={i.key} i={i} onReview={async (k, s) => { await api(`/ai/insights/${encodeURIComponent(k)}/review`, { body: { status: s } }); app.toast(`Marked ${s}; recorded in the audit history`); reload() }} />)}
        {data?.items.length === 0 && <Empty text="Not enough data yet for insights." />}
      </Stack>
    </State>
  )
}

function Ask() {
  const [q, setQ] = useState('')
  const [log, setLog] = useState<any[]>([])
  const [busy, setBusy] = useState(false)
  const app = useApp()
  const biz = app.me!.tenant.edition === 'business'
  const ask = async (text: string) => {
    if (!text.trim()) return
    setBusy(true)
    try { const r = await api('/ai/ask', { body: { question: text } }); setLog((l) => [...l, { q: text, r }]) } catch (x) { setLog((l) => [...l, { q: text, err: errText(x) }]) }
    setQ(''); setBusy(false)
  }
  const examples = biz ? ['How much did we spend on Multitenant CRM?', 'Top spending categories', 'What is pending approval?', 'How much did Digital Marketing spend?'] : ['How much did I spend on groceries?', 'Top spending categories', 'What is my total spending this month?']
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>{examples.map((e) => <Chip key={e} label={e} onClick={() => ask(e)} variant="outlined" />)}</Stack>
      <Stack spacing={1.5} data-testid="chat">
        {log.map((m, i) => (
          <Box key={i}>
            <Typography sx={{ textAlign: 'right' }}><Chip label={m.q} color="primary" /></Typography>
            <Paper variant="outlined" sx={{ p: 1.5, mt: 0.5, maxWidth: 720 }}>
              {m.err ? <Alert severity="error">{m.err}</Alert> : <>
                <Typography>{m.r.answer}</Typography>
                {m.r.citations?.map((c: any) => <Typography key={c.id} variant="caption" display="block" color="text.secondary">Source: {c.date} · {c.description} · {inr(c.amount_minor)}</Typography>)}
                <Typography variant="caption" color="text.secondary">AI-assisted answer from records you can access · {m.r.kind === 'help' ? 'help' : 'based on posted figures'}</Typography></>}
            </Paper>
          </Box>))}
      </Stack>
      <Stack direction="row" spacing={1} component="form" onSubmit={(e) => { e.preventDefault(); ask(q) }}>
        <TextField fullWidth label="Ask about your spending" value={q} onChange={(e) => setQ(e.target.value)} />
        <Button type="submit" variant="contained" disabled={busy}>Ask</Button>
      </Stack>
    </Stack>
  )
}

export default function AiAssistant() {
  const app = useApp()
  const tabs = [...(app.has('ai_capture') ? [['capture', 'Capture expenses']] : []), ...(app.has('ai_insights') ? [['insights', 'Insights'], ['ask', 'Ask a question']] : [])]
  const [tab, setTab] = useState(tabs[0]?.[0] || 'capture')
  if (!tabs.length) return <Alert severity="info">AI features are not part of your subscription.</Alert>
  return (
    <Page title="AI Assistant" subtitle="Assistive only: it suggests, you confirm. It never saves, approves or pays anything on its own.">
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>{tabs.map(([v, l]) => <Tab key={v} value={v} label={l} />)}</Tabs>
      {tab === 'capture' && <Capture />}{tab === 'insights' && <Insights />}{tab === 'ask' && <Ask />}
    </Page>
  )
}
