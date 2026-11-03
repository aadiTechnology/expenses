// Install support. The browser fires "beforeinstallprompt" very early, so it is captured here at import time (before React renders).
type Deferred = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }> }
let deferred: Deferred | null = null
const listeners = new Set<() => void>()
const notify = () => listeners.forEach((l) => l())

if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); deferred = e as Deferred; notify() })
  window.addEventListener('appinstalled', () => { deferred = null; try { localStorage.setItem('spendos.installed', '1') } catch { /* private mode */ } notify() })
}

export const subscribe = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn) } }
export const canPromptInstall = () => deferred !== null
export async function promptInstall() {
  if (!deferred) return 'unavailable' as const
  await deferred.prompt()
  const { outcome } = await deferred.userChoice
  deferred = null
  notify()
  return outcome
}
export const isStandalone = () => window.matchMedia('(display-mode: standalone)').matches || (navigator as any).standalone === true
export const isIos = () => /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
export const isPhoneOrTablet = () => /Android|iPhone|iPad|iPod/.test(navigator.userAgent) || isIos() || window.matchMedia('(max-width: 900px) and (pointer: coarse)').matches

const DISMISS_KEY = 'spendos.install.dismissed'
export const dismissedRecently = () => { try { const t = Number(localStorage.getItem(DISMISS_KEY) || 0); return Date.now() - t < 14 * 86400000 } catch { return false } }
export const dismissInstall = () => { try { localStorage.setItem(DISMISS_KEY, String(Date.now())) } catch { /* private mode */ } }

export function registerServiceWorker() {
  if ('serviceWorker' in navigator && (import.meta as any).env?.PROD) {
    window.addEventListener('load', () => { navigator.serviceWorker.register('/sw.js').catch(() => undefined) })
  }
}
