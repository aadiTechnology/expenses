import { useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import { Alert, Box, Button, Chip, LinearProgress, Stack, TextField, Typography } from '@mui/material'
import Grid from '@mui/material/Grid'
import { Bars, Card, Empty, Page, State, StatusChip, Utilization, inr, monthLabel, useApp, useLoad } from '../ui'

const Kpi = ({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) => (
  <Card><Typography variant="body2" color="text.secondary">{label}</Typography><Typography variant="h5" fontWeight={800} color={color}>{value}</Typography>{sub && <Typography variant="caption" color="text.secondary">{sub}</Typography>}</Card>
)

function change(cur: number, prev: number) {
  if (!prev) return undefined
  const p = ((cur - prev) / prev) * 100
  return `${p >= 0 ? '▲' : '▼'} ${Math.abs(p).toFixed(0)}% vs previous month`
}

function Trend({ monthly, daily }: { monthly: any[]; daily: any[] }) {
  const max = Math.max(1, ...monthly.flatMap((m) => [m.income, m.expense]))
  const dmax = Math.max(1, ...daily.map((d) => d.amount_minor))
  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="caption" color="text.secondary">Monthly: income vs expenses</Typography>
        <Stack direction="row" spacing={2} alignItems="flex-end" sx={{ height: 120, mt: 1 }}>
          {monthly.map((m) => (
            <Stack key={m.period} alignItems="center" sx={{ flex: 1 }}>
              <Stack direction="row" spacing={0.5} alignItems="flex-end" sx={{ height: 96 }}>
                <Box title={`Income ${inr(m.income)}`} sx={{ width: 16, height: `${(m.income / max) * 100}%`, bgcolor: 'success.main', borderRadius: '4px 4px 0 0' }} />
                <Box title={`Expenses ${inr(m.expense)}`} sx={{ width: 16, height: `${(m.expense / max) * 100}%`, bgcolor: 'error.main', borderRadius: '4px 4px 0 0' }} />
              </Stack>
              <Typography variant="caption">{m.period.slice(5)}/{m.period.slice(2, 4)}</Typography>
            </Stack>
          ))}
        </Stack>
      </Box>
      <Box>
        <Typography variant="caption" color="text.secondary">Daily spending this month</Typography>
        <Stack direction="row" alignItems="flex-end" spacing="2px" sx={{ height: 60, mt: 0.5 }}>
          {daily.map((d) => <Box key={d.day} title={`Day ${d.day}: ${inr(d.amount_minor)}`} sx={{ flex: 1, minWidth: 3, height: `${Math.max(4, (d.amount_minor / dmax) * 100)}%`, bgcolor: 'primary.main', opacity: 0.8 }} />)}
        </Stack>
      </Box>
    </Stack>
  )
}

export function InsightCard({ i, onReview }: { i: any; onReview?: (key: string, status: string) => void }) {
  const color = i.kind === 'estimate' ? 'warning' : i.kind === 'anomaly' ? 'error' : 'success'
  const label = i.kind === 'estimate' ? 'Estimate' : i.kind === 'anomaly' ? 'Advisory flag' : 'Fact'
  return (
    <Alert severity={color === 'success' ? 'info' : color as any} icon={false} sx={{ alignItems: 'flex-start' }} data-testid={`insight-${i.kind}`}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
        <Chip size="small" color={color as any} label={label} /><Chip size="small" variant="outlined" label="AI-assisted" />
        {i.review_status !== 'open' && <Chip size="small" label={i.review_status} />}
      </Stack>
      <Typography fontWeight={600}>{i.title}</Typography>
      <Typography variant="body2">{i.body}</Typography>
      {i.supporting?.map((t: any) => <Typography key={t.id} variant="caption" display="block">Supporting record: {t.date} · {t.description} · {inr(t.amount_minor)}</Typography>)}
      {onReview && i.review_status === 'open' && (i.kind === 'anomaly' || i.kind === 'estimate') && (
        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
          <Button size="small" variant="outlined" onClick={() => onReview(i.key, 'acknowledged')}>Acknowledge</Button>
          <Button size="small" onClick={() => onReview(i.key, 'dismissed')}>Dismiss</Button>
        </Stack>
      )}
    </Alert>
  )
}

export default function Dashboard() {
  const app = useApp()
  const [period, setPeriod] = useState('')
  const { data, error, loading } = useLoad(`/dashboard${period ? `?period=${period}` : ''}`)
  const d = data?.data || {}
  const biz = app.me!.tenant.edition === 'business'
  return (
    <Page title="Dashboard" subtitle={data ? monthLabel(data.period) : ''} actions={<TextField type="month" label="Month" value={period || data?.period || ''} onChange={(e) => setPeriod(e.target.value)} InputLabelProps={{ shrink: true }} />}>
      <State loading={loading && !data} error={error}>
        <Grid container spacing={2}>
          {d.kpis && (
            <>
              <Grid size={{ xs: 12, sm: 6, md: 3 }}><Kpi label="Income" value={inr(d.kpis.income)} sub={change(d.kpis.income, d.kpis.previous.income)} color="success.main" /></Grid>
              <Grid size={{ xs: 12, sm: 6, md: 3 }}><Kpi label="Expenses (net of refunds)" value={inr(d.kpis.expense)} sub={change(d.kpis.expense, d.kpis.previous.expense)} color="error.main" /></Grid>
              <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                {biz ? <Kpi label="Operating surplus (simplified)" value={inr(d.kpis.savings)} sub="Before tax and accounting adjustments; not audited profit" />
                  : <Kpi label="Savings" value={inr(d.kpis.savings)} sub={d.kpis.savings_rate !== null ? `Savings rate ${d.kpis.savings_rate}%` : undefined} />}
              </Grid>
              <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                {d.kpis.available_balance !== null ? <Kpi label="Available balance" value={inr(d.kpis.available_balance)} sub={d.kpis.credit_outstanding ? `Card outstanding ${inr(d.kpis.credit_outstanding)}` : 'All active non-card accounts'} />
                  : <Kpi label="Refunds this month" value={inr(d.kpis.refunds)} />}
              </Grid>
            </>
          )}
          {d.pending && (
            <Grid size={{ xs: 12, md: 4 }}>
              <Card title="Pending">
                <Stack spacing={1}>
                  <Stack direction="row" justifyContent="space-between"><Typography>Awaiting approval</Typography><Chip label={d.pending.approvals} color={d.pending.approvals ? 'warning' : 'default'} /></Stack>
                  <Stack direction="row" justifyContent="space-between"><Typography>Reimbursements to pay</Typography><Chip label={d.pending.reimbursements} color={d.pending.reimbursements ? 'info' : 'default'} /></Stack>
                  <Typography variant="body2" color="text.secondary">Value in flight: {inr(d.pending.amount_minor)}</Typography>
                  <Button component={RouterLink} to="/approvals" size="small">Open approvals</Button>
                </Stack>
              </Card>
            </Grid>
          )}
          {d.category_spend && <Grid size={{ xs: 12, md: biz ? 4 : 6 }}><Card title="Category-wise spending"><Bars rows={d.category_spend.slice(0, 8)} /></Card></Grid>}
          {d.department_spend && <Grid size={{ xs: 12, md: 4 }}><Card title="Department-wise expenses"><Bars rows={d.department_spend} color="#00897b" /></Card></Grid>}
          {d.project_spend && <Grid size={{ xs: 12, md: 4 }}><Card title="Project-wise expenses"><Bars rows={d.project_spend} color="#8e24aa" /></Card></Grid>}
          {d.trend && <Grid size={{ xs: 12, md: 6 }}><Card title="Trends"><Trend monthly={d.trend.monthly} daily={d.trend.daily} /></Card></Grid>}
          {d.budgets && (
            <Grid size={{ xs: 12, md: 6 }}>
              <Card title="Budget utilisation" action={<Button component={RouterLink} to="/budgets" size="small">All budgets</Button>}>
                {d.budgets.length === 0 ? <Empty text="No budgets visible to you for this month." /> : (
                  <Stack spacing={1.5}>{d.budgets.map((b: any) => (
                    <Box key={b.id}><Stack direction="row" justifyContent="space-between"><Typography variant="body2">{b.name}</Typography><Typography variant="body2">{inr(b.actual_minor)} / {inr(b.budget_minor)}</Typography></Stack><Utilization pct={b.utilization} /></Box>
                  ))}</Stack>
                )}
              </Card>
            </Grid>
          )}
          {d.recent && (
            <Grid size={{ xs: 12, md: 6 }}>
              <Card title="Recent transactions" action={<Button component={RouterLink} to="/transactions" size="small">View all</Button>}>
                {d.recent.length === 0 ? <Empty text="No transactions yet. Add your first expense." /> : d.recent.map((t: any) => (
                  <Stack key={t.id} direction="row" justifyContent="space-between" sx={{ py: 0.6, borderBottom: 1, borderColor: 'divider' }}>
                    <Box><Typography variant="body2">{t.description}</Typography><Typography variant="caption" color="text.secondary">{t.date} · {t.type}</Typography></Box>
                    <Typography fontWeight={600} color={t.type === 'income' || t.type === 'refund' || t.type === 'reimbursement' ? 'success.main' : 'text.primary'}>{t.type === 'expense' ? '−' : t.type === 'transfer' ? '' : '+'}{inr(t.amount_minor)}</Typography>
                  </Stack>
                ))}
              </Card>
            </Grid>
          )}
          {d.goals && d.goals.length > 0 && (
            <Grid size={{ xs: 12, md: 6 }}>
              <Card title="Savings goals" action={<Button component={RouterLink} to="/goals" size="small">Manage</Button>}>
                <Stack spacing={1.5}>{d.goals.map((g: any) => (
                  <Box key={g.name}><Stack direction="row" justifyContent="space-between"><Typography variant="body2">{g.name}</Typography><Typography variant="body2">{inr(g.saved_minor)} of {inr(g.target_minor)}</Typography></Stack>
                    <LinearProgress variant="determinate" aria-label={`${g.name} progress`} value={Math.min(100, (g.saved_minor / g.target_minor) * 100)} sx={{ height: 8, borderRadius: 4 }} /></Box>
                ))}</Stack>
              </Card>
            </Grid>
          )}
          {d.growth && d.growth.length > 0 && (
            <Grid size={{ xs: 12, md: 6 }}>
              <Card title="Growth spend by campaign" action={<Button component={RouterLink} to="/growth" size="small">Open report</Button>}>
                {d.growth.map((g: any) => (
                  <Stack key={g.value_id} direction="row" justifyContent="space-between" alignItems="center" sx={{ py: 0.5 }}>
                    <Typography variant="body2">{g.name}</Typography><Typography variant="body2">{inr(g.actual_minor)}</Typography><Utilization pct={g.utilization} />
                  </Stack>
                ))}
              </Card>
            </Grid>
          )}
          {d.insights && d.insights.length > 0 && (
            <Grid size={12}>
              <Card title="AI-generated observations" action={<Button component={RouterLink} to="/ai" size="small">All insights</Button>}>
                <Stack spacing={1}>{d.insights.map((i: any) => <InsightCard key={i.key} i={i} />)}</Stack>
              </Card>
            </Grid>
          )}
        </Grid>
      </State>
    </Page>
  )
}
