import { useState } from 'react'
import { Button, Chip, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material'
import Grid from '@mui/material/Grid'
import { Card, Empty, Page, State, StatusChip, inr, useLoad } from '../ui'
import { Transactions, TxnDetail, useLookups } from './Transactions'

export const MyExpenses = () => <Transactions mineOnly />

export function Approvals() {
  const { data, loading, error, reload } = useLoad('/approvals')
  const [open, setOpen] = useState<string | null>(null)
  const L = useLookups()
  return (
    <Page title="Approvals" subtitle="Expenses waiting for you. Each approval is checked on the server against your role, project and department.">
      <State loading={loading} error={error}>
        {data?.length === 0 ? <Paper variant="outlined"><Empty text="Nothing is waiting for your approval." /></Paper> : (
          <TableContainer component={Paper} variant="outlined">
            <Table size="small" aria-label="Pending approvals">
              <TableHead><TableRow><TableCell>Date</TableCell><TableCell>Employee</TableCell><TableCell>Description</TableCell><TableCell>Project</TableCell><TableCell>Your step</TableCell><TableCell align="right">Amount</TableCell><TableCell /></TableRow></TableHead>
              <TableBody>
                {data?.map((t: any) => (
                  <TableRow key={t.id} hover>
                    <TableCell>{t.date}</TableCell><TableCell>{t.employee}</TableCell><TableCell>{t.description}</TableCell><TableCell>{t.project_name}</TableCell>
                    <TableCell>{t.action === 'pay' ? <Chip size="small" color="info" label="Pay reimbursement" /> : <Chip size="small" color="warning" label={t.waiting_for === 'finance' ? 'Finance verification' : t.waiting_for.replace('_', ' ')} />}</TableCell>
                    <TableCell align="right">{inr(t.amount_minor)}</TableCell>
                    <TableCell align="right"><Button size="small" variant="contained" onClick={() => setOpen(t.id)}>Review</Button></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </State>
      {open && <TxnDetail id={open} onClose={() => setOpen(null)} onChanged={reload} />}
    </Page>
  )
}

export function Reimbursements() {
  const { data, loading, error, reload } = useLoad('/reimbursements')
  const [open, setOpen] = useState<string | null>(null)
  return (
    <Page title="Reimbursements" subtitle="Employee expense claims from submission to payment">
      <State loading={loading} error={error}>
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid size={{ xs: 12, sm: 6 }}><Card><Typography variant="body2" color="text.secondary">Pending reimbursement</Typography><Typography variant="h5" fontWeight={800} color="warning.main">{inr(data?.pending_minor)}</Typography></Card></Grid>
          <Grid size={{ xs: 12, sm: 6 }}><Card><Typography variant="body2" color="text.secondary">Paid</Typography><Typography variant="h5" fontWeight={800} color="success.main">{inr(data?.paid_minor)}</Typography></Card></Grid>
        </Grid>
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="Reimbursements">
            <TableHead><TableRow><TableCell>Date</TableCell><TableCell>Employee</TableCell><TableCell>Description</TableCell><TableCell>Status</TableCell><TableCell align="right">Amount</TableCell></TableRow></TableHead>
            <TableBody>
              {data?.items.map((t: any) => (
                <TableRow key={t.id} hover sx={{ cursor: 'pointer' }} onClick={() => setOpen(t.id)}>
                  <TableCell>{t.date}</TableCell><TableCell>{t.employee}</TableCell><TableCell>{t.description}</TableCell><TableCell><StatusChip status={t.status} /></TableCell><TableCell align="right">{inr(t.amount_minor)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {data?.items.length === 0 && <Empty text="No reimbursement claims yet." />}
        </TableContainer>
      </State>
      {open && <TxnDetail id={open} onClose={() => setOpen(null)} onChanged={reload} />}
    </Page>
  )
}
