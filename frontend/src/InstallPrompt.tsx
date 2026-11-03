import { useEffect, useState } from 'react'
import { Box, Button, IconButton, Paper, Stack, Typography } from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import IosShareIcon from '@mui/icons-material/IosShare'
import GetAppIcon from '@mui/icons-material/GetApp'
import { canPromptInstall, dismissInstall, dismissedRecently, isIos, isPhoneOrTablet, isStandalone, promptInstall, subscribe } from './pwa'

/** "Install this app" banner for people who open SpendOS in a phone browser. Android/Chrome: one-tap install. iPhone/iPad: how-to (Safari has no install button). */
export function InstallPrompt() {
  const [, force] = useState(0)
  const [hidden, setHidden] = useState(false)
  useEffect(() => subscribe(() => force((n) => n + 1)), [])
  if (hidden || isStandalone() || !isPhoneOrTablet() || dismissedRecently()) return null
  const ios = isIos()
  if (!ios && !canPromptInstall()) return null
  const close = () => { dismissInstall(); setHidden(true) }
  return (
    <Paper elevation={8} role="dialog" aria-label="Install Aadi SpendOS" data-testid="install-banner"
      sx={{ position: 'fixed', left: 12, right: 12, bottom: 'calc(12px + env(safe-area-inset-bottom))', zIndex: 1400, p: 1.5, borderRadius: 3, maxWidth: 480, mx: 'auto' }}>
      <Stack direction="row" spacing={1.5} alignItems="center">
        <Box component="img" src="/icons/icon-192.png" alt="" sx={{ width: 48, height: 48, borderRadius: 2 }} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography fontWeight={700}>Install Aadi SpendOS</Typography>
          {ios
            ? <Typography variant="body2" color="text.secondary">Tap <IosShareIcon sx={{ fontSize: 16, verticalAlign: 'text-bottom' }} /> Share, then <b>Add to Home Screen</b>, to open it like an app.</Typography>
            : <Typography variant="body2" color="text.secondary">Add it to your home screen for one-tap access, full screen.</Typography>}
        </Box>
        <IconButton size="small" onClick={close} aria-label="Close install banner"><CloseIcon fontSize="small" /></IconButton>
      </Stack>
      {!ios && (
        <Stack direction="row" spacing={1} justifyContent="flex-end" sx={{ mt: 1 }}>
          <Button size="small" onClick={close}>Not now</Button>
          <Button size="small" variant="contained" startIcon={<GetAppIcon />} onClick={async () => { const r = await promptInstall(); if (r !== 'unavailable') { r === 'dismissed' ? close() : setHidden(true) } }}>Install</Button>
        </Stack>
      )}
    </Paper>
  )
}

/** Thin bar shown while the device has no connection (data is always live, so nothing can be saved offline). */
export function OfflineBar() {
  const [online, setOnline] = useState(navigator.onLine)
  useEffect(() => {
    const on = () => setOnline(true), off = () => setOnline(false)
    window.addEventListener('online', on); window.addEventListener('offline', off)
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off) }
  }, [])
  if (online) return null
  return <Box role="status" sx={{ position: 'sticky', top: 0, zIndex: 1500, bgcolor: 'warning.main', color: '#fff', textAlign: 'center', py: 0.5, fontSize: 14 }}>You are offline. Figures shown may be out of date and changes cannot be saved.</Box>
}
