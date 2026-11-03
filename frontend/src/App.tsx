import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Link as RouterLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import {
  AppBar, Badge, Box, Button, Chip, Divider, Drawer, IconButton, List, ListItemButton, ListItemIcon, ListItemText, Menu, MenuItem, Stack, Toolbar, Typography, useMediaQuery,
} from '@mui/material'
import MenuIcon from '@mui/icons-material/Menu'
import DashboardIcon from '@mui/icons-material/SpaceDashboard'
import ReceiptIcon from '@mui/icons-material/ReceiptLong'
import AddIcon from '@mui/icons-material/AddCircle'
import PaymentsIcon from '@mui/icons-material/Payments'
import AccountBalanceIcon from '@mui/icons-material/AccountBalanceWallet'
import CategoryIcon from '@mui/icons-material/Category'
import SavingsIcon from '@mui/icons-material/Savings'
import FamilyIcon from '@mui/icons-material/FamilyRestroom'
import FlagIcon from '@mui/icons-material/Flag'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import AssessmentIcon from '@mui/icons-material/Assessment'
import SettingsIcon from '@mui/icons-material/Settings'
import ApprovalIcon from '@mui/icons-material/FactCheck'
import ApartmentIcon from '@mui/icons-material/Apartment'
import FolderIcon from '@mui/icons-material/Folder'
import CampaignIcon from '@mui/icons-material/Campaign'
import AdminIcon from '@mui/icons-material/AdminPanelSettings'
import NotificationsIcon from '@mui/icons-material/Notifications'
import { visuallyHidden } from '@mui/utils'
import { api, getToken, setToken } from './api'
import { LANGS } from './i18n'
import { InstallPrompt, OfflineBar } from './InstallPrompt'
import { ToastHost, useApp, type Session } from './ui'
import { Forgot, Login, Register } from './pages/Auth'
import Dashboard from './pages/Dashboard'
import { AddTransaction, Transactions } from './pages/Transactions'
import { Approvals, MyExpenses, Reimbursements } from './pages/Approvals'
import { Accounts, Budgets, Categories, Departments, Family, Goals, Projects } from './pages/Setup'
import { OrgSettings } from './pages/Settings'
import { Reports, GrowthSpend } from './pages/Reports'
import AiAssistant from './pages/AI'
import Platform from './pages/Platform'

interface NavItem { to: string; label: string; icon: ReactNode; show?: (a: ReturnType<typeof useApp>) => boolean }

function navFor(a: ReturnType<typeof useApp>): NavItem[] {
  const me = a.me!
  if (me.user.is_platform_admin && !me.tenant) return [{ to: '/platform', label: 'Platform Admin', icon: <AdminIcon /> }]
  const personal = me.tenant.edition === 'personal'
  const items: NavItem[] = personal
    ? [
        { to: '/', label: 'Dashboard', icon: <DashboardIcon /> },
        { to: '/transactions', label: 'Transactions', icon: <ReceiptIcon /> },
        { to: '/add', label: 'Add Expense', icon: <AddIcon />, show: () => a.can('txn.create') },
        { to: '/income', label: 'Income', icon: <PaymentsIcon />, show: () => a.can('txn.create') },
        { to: '/accounts', label: 'Accounts', icon: <AccountBalanceIcon />, show: () => a.can('scope.all') },
        { to: '/categories', label: 'Categories', icon: <CategoryIcon /> },
        { to: '/budgets', label: 'Budgets', icon: <SavingsIcon /> },
        { to: '/family', label: 'Family', icon: <FamilyIcon /> },
        { to: '/goals', label: 'Goals', icon: <FlagIcon />, show: () => a.can('scope.all') },
        { to: '/ai', label: 'AI Assistant', icon: <AutoAwesomeIcon />, show: () => a.can('ai.use') },
        { to: '/reports', label: 'Reports', icon: <AssessmentIcon />, show: () => a.can('report.read') },
        { to: '/settings', label: 'Settings', icon: <SettingsIcon />, show: () => a.can('scope.all') },
      ]
    : [
        { to: '/', label: 'Dashboard', icon: <DashboardIcon /> },
        { to: '/transactions', label: 'Transactions', icon: <ReceiptIcon /> },
        { to: '/my-expenses', label: 'My Expenses', icon: <AddIcon />, show: () => a.can('txn.create') },
        { to: '/approvals', label: 'Approvals', icon: <ApprovalIcon />, show: () => ['approve.project', 'approve.department', 'approve.finance'].some(a.can) },
        { to: '/reimbursements', label: 'Reimbursements', icon: <PaymentsIcon /> },
        { to: '/departments', label: 'Departments', icon: <ApartmentIcon /> },
        { to: '/projects', label: 'Projects', icon: <FolderIcon /> },
        { to: '/growth', label: 'Growth Spend', icon: <CampaignIcon />, show: () => a.has('growth_spend') && a.can('growth.read') },
        { to: '/categories', label: 'Categories', icon: <CategoryIcon /> },
        { to: '/budgets', label: 'Budgets', icon: <SavingsIcon />, show: () => a.can('budget.manage') || a.can('scope.department') || a.can('scope.project') },
        { to: '/accounts', label: 'Accounts', icon: <AccountBalanceIcon />, show: () => a.can('account.manage') },
        { to: '/ai', label: 'AI Assistant', icon: <AutoAwesomeIcon />, show: () => a.can('ai.use') },
        { to: '/reports', label: 'Reports', icon: <AssessmentIcon />, show: () => a.can('report.read') },
        { to: '/settings', label: 'Organization Settings', icon: <SettingsIcon />, show: () => a.can('config.manage') || a.can('audit.read') || a.can('member.manage') },
      ]
  return items.filter((i) => !i.show || i.show(a))
}

function Shell({ children }: { children: ReactNode }) {
  const app = useApp()
  const me = app.me!
  const nav = useNavigate()
  const loc = useLocation()
  const wide = useMediaQuery('(min-width:900px)')
  const [open, setOpen] = useState(false)
  const [menu, setMenu] = useState<HTMLElement | null>(null)
  const items = navFor(app)
  const drawer = (
    <Box sx={{ width: 250 }} role="navigation" aria-label="Main navigation">
      <Toolbar><Typography variant="h6" fontWeight={800} color="primary">Aadi SpendOS</Typography></Toolbar>
      <List dense component="div">
        {items.map((i) => (
          <ListItemButton key={i.to} component={RouterLink} to={i.to} selected={loc.pathname === i.to} onClick={() => setOpen(false)}>
            <ListItemIcon sx={{ minWidth: 36 }}>{i.icon}</ListItemIcon>
            <ListItemText primary={app.t(i.label)} />
          </ListItemButton>
        ))}
      </List>
    </Box>
  )
  const logout = async () => { try { await api('/auth/logout', { method: 'POST' }) } catch { /* already ended */ } setToken(null); nav('/login'); await app.reload() }
  const switchTo = async (id: string) => { const r = await api(`/auth/switch/${id}`, { method: 'POST' }); setToken(r.token); setMenu(null); nav('/'); await app.reload() }
  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      {wide ? <Drawer variant="permanent" sx={{ width: 250, '& .MuiDrawer-paper': { width: 250, boxSizing: 'border-box' } }}>{drawer}</Drawer>
        : <Drawer open={open} onClose={() => setOpen(false)}>{drawer}</Drawer>}
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <AppBar position="sticky" color="inherit" elevation={0} sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Toolbar>
            {!wide && <IconButton edge="start" onClick={() => setOpen(true)} aria-label="Open menu"><MenuIcon /></IconButton>}
            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
              <Typography fontWeight={700} noWrap>{me.tenant ? me.tenant.name : 'Platform administration'}</Typography>
              {me.tenant?.is_demo && <Typography variant="caption" color="warning.main">Demo environment · synthetic sample data</Typography>}
            </Box>
            {me.tenant && (
              <IconButton component={RouterLink} to="/settings?tab=notifications">
                <Badge badgeContent={me.unread} color="error"><NotificationsIcon /></Badge><Box component="span" sx={visuallyHidden}>Notifications</Box>
              </IconButton>
            )}
            <Button onClick={(e) => setMenu(e.currentTarget)} data-testid="account-menu">
              <Stack alignItems="flex-end"><Typography variant="body2" fontWeight={600}>{me.user.name}</Typography><Typography variant="caption" color="text.secondary">{me.role_label || 'Platform Admin'}</Typography></Stack>
            </Button>
            <Menu anchorEl={menu} open={!!menu} onClose={() => setMenu(null)}>
              {me.memberships.filter((m) => m.tenant_id !== me.tenant?.id).map((m) => <MenuItem key={m.tenant_id} onClick={() => switchTo(m.tenant_id)}>Switch to {m.tenant_name}</MenuItem>)}
              <MenuItem disabled sx={{ opacity: '1 !important', fontSize: 12 }}>{app.t('Language')}</MenuItem>
              {LANGS.map((l) => <MenuItem key={l.code} selected={app.lang === l.code} onClick={() => { app.setLang(l.code); setMenu(null) }} data-testid={`lang-${l.code}`}>{l.label}</MenuItem>)}
              <Divider />
              <MenuItem onClick={logout}>{app.t('Sign out')}</MenuItem>
            </Menu>
          </Toolbar>
        </AppBar>
        <Box component="main" sx={{ p: { xs: 2, md: 3 }, maxWidth: 1400 }}>{children}</Box>
      </Box>
    </Box>
  )
}

function Gate({ perm, module, children }: { perm?: string; module?: string; children: ReactNode }) {
  const a = useApp()
  if ((perm && !a.can(perm)) || (module && !a.has(module))) return <Box sx={{ p: 4 }}><Typography variant="h6">Not available</Typography><Typography color="text.secondary">Your role or subscription does not include this area.</Typography></Box>
  return <>{children}</>
}

export default function App() {
  const [me, setMe] = useState<Session | null>(null)
  const [ready, setReady] = useState(false)
  const reload = useCallback(async () => {
    if (!getToken()) { setMe(null); setReady(true); return }
    try { setMe(await api('/me')) } catch { setToken(null); setMe(null) }
    setReady(true)
  }, [])
  useEffect(() => { reload() }, [reload])
  useEffect(() => {
    if (me?.tenant) api('/notifications/refresh', { body: { today: new Date().toISOString().slice(0, 10) } }).then((r) => r.created && reload()).catch(() => undefined)
  }, [me?.tenant?.id])
  if (!ready) return null
  return (
    <ToastHost me={me} reload={reload}>
      <OfflineBar />
      <InstallPrompt />
      {!me ? (
        <Routes>
          <Route path="/register" element={<Register />} />
          <Route path="/forgot" element={<Forgot />} />
          <Route path="/reset" element={<Forgot />} />
          <Route path="*" element={<Login />} />
        </Routes>
      ) : (
        <Shell>
          <Routes>
            {me.user.is_platform_admin && !me.tenant ? (
              <><Route path="/platform" element={<Platform />} /><Route path="*" element={<Navigate to="/platform" />} /></>
            ) : (
              <>
                <Route path="/" element={<Dashboard />} />
                <Route path="/transactions" element={<Transactions />} />
                <Route path="/add" element={<Gate perm="txn.create"><AddTransaction type="expense" /></Gate>} />
                <Route path="/income" element={<Gate perm="txn.create"><AddTransaction type="income" /></Gate>} />
                <Route path="/my-expenses" element={<MyExpenses />} />
                <Route path="/approvals" element={<Approvals />} />
                <Route path="/reimbursements" element={<Reimbursements />} />
                <Route path="/accounts" element={<Gate perm="scope.all"><Accounts /></Gate>} />
                <Route path="/categories" element={<Categories />} />
                <Route path="/departments" element={<Departments />} />
                <Route path="/projects" element={<Projects />} />
                <Route path="/budgets" element={<Budgets />} />
                <Route path="/family" element={<Family />} />
                <Route path="/goals" element={<Goals />} />
                <Route path="/growth" element={<Gate module="growth_spend" perm="growth.read"><GrowthSpend /></Gate>} />
                <Route path="/ai" element={<Gate perm="ai.use"><AiAssistant /></Gate>} />
                <Route path="/reports" element={<Gate perm="report.read"><Reports /></Gate>} />
                <Route path="/settings" element={<OrgSettings />} />
                <Route path="*" element={<Navigate to="/" />} />
              </>
            )}
          </Routes>
        </Shell>
      )}
    </ToastHost>
  )
}
