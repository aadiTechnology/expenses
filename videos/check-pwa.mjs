/** Install-to-home-screen (PWA) checks on phone profiles. Env: SPENDOS_URL (default http://localhost:8002). */
import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'
const require = createRequire('C:/Users/lenovo/AadiTech/Product/AadiProduct/MultiTenant/Aadi-MultiTenant-Platform/frontend/package.json')
const { chromium } = require('playwright')
const origin = process.env.SPENDOS_URL ?? 'http://localhost:8002'
const shots = path.resolve('verification'); fs.mkdirSync(shots, { recursive: true })
let browser
for (const o of [{ channel: 'chrome' }, { channel: 'msedge' }, {}]) { try { browser = await chromium.launch({ headless: true, ...o }); break } catch { /* next */ } }

const ANDROID = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36'
const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1'
const results = []
const check = (name, ok, extra = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? ' - ' + extra : ''}`) }
const fire = (page) => page.evaluate(() => {
  const e = new Event('beforeinstallprompt', { cancelable: true })
  Object.assign(e, { prompt: async () => { window.__prompted = true }, userChoice: Promise.resolve({ outcome: 'accepted' }) })
  window.dispatchEvent(e)
})
const phone = (ua, extra = {}) => browser.newContext({ viewport: { width: 390, height: 844 }, userAgent: ua, isMobile: true, hasTouch: true, deviceScaleFactor: 2, ...extra })

// ---- 1. installability criteria as Chrome evaluates them ----
{
  const ctx = await phone(ANDROID); const page = await ctx.newPage()
  await page.goto(origin + '/'); await page.evaluate(() => navigator.serviceWorker.ready)
  const cdp = await ctx.newCDPSession(page)
  const { installabilityErrors: errors } = await cdp.send('Page.getInstallabilityErrors')
  const { errors: manifestErrors, data } = await cdp.send('Page.getAppManifest')
  const m = JSON.parse(data)
  // Playwright always runs in an incognito-style profile, and Chrome never installs from incognito; that one reason is a test artifact.
  const real = errors.filter((e) => e.errorId !== 'in-incognito')
  check('Chrome reports no installability errors (besides test-profile incognito)', real.length === 0, real.map((e) => e.errorId).join(', '))
  check('Manifest parses without errors', manifestErrors.length === 0, manifestErrors.map((e) => e.message).join('; '))
  check('Manifest: standalone, start_url, 192/512 + maskable icons', m.display === 'standalone' && m.start_url === '/' && m.icons.some((i) => i.sizes === '192x192') && m.icons.some((i) => i.sizes === '512x512') && m.icons.some((i) => i.purpose === 'maskable'))
  check('Service worker is active', await page.evaluate(async () => !!(await navigator.serviceWorker.ready).active))
  const cached = await page.evaluate(async () => { const out = []; for (const k of await caches.keys()) for (const r of await (await caches.open(k)).keys()) out.push(new URL(r.url).pathname); return out })
  check('Service worker caches only the app shell, never /api', cached.length > 0 && !cached.some((p) => p.startsWith('/api/')), `${cached.length} files cached`)
  // ---- 2. Android: banner appears, Install triggers the real prompt ----
  await page.waitForTimeout(500)
  check('Android: no banner until the browser offers install', (await page.getByTestId('install-banner').count()) === 0)
  await fire(page)
  await page.getByTestId('install-banner').waitFor({ timeout: 5000 })
  await page.screenshot({ path: path.join(shots, 'pwa-android-banner.png') })
  await page.getByRole('button', { name: 'Install', exact: true }).click()
  check('Android: Install opens the browser install prompt', await page.evaluate(() => window.__prompted === true))
  check('Android: banner closes after installing', (await page.getByTestId('install-banner').count()) === 0)
  // ---- 3. Not now is remembered ----
  await page.reload(); await page.evaluate(() => navigator.serviceWorker.ready); await fire(page)
  await page.getByTestId('install-banner').waitFor()
  await page.getByRole('button', { name: 'Not now', exact: true }).click()
  await page.reload(); await page.waitForTimeout(500); await fire(page); await page.waitForTimeout(500)
  check('"Not now" hides the banner on later visits (14 days)', (await page.getByTestId('install-banner').count()) === 0)
  // ---- 4. Offline: shell still opens, offline bar shown ----
  await page.evaluate(() => localStorage.clear())
  await ctx.setOffline(true)
  await page.reload({ waitUntil: 'domcontentloaded' }).catch(() => undefined)
  await page.waitForTimeout(2500)
  console.log('   offline page text:', (await page.locator('#root').innerText()).slice(0, 90).replace(/\s+/g, ' '), '| onLine', await page.evaluate(() => navigator.onLine))
  check('Offline: app shell still opens', (await page.locator('#root').innerText()).length > 0 && (await page.title()) === 'Aadi SpendOS')
  await ctx.setOffline(false)
  await ctx.close()
}
// ---- 4b. Offline warning bar (plain context: Chrome updates navigator.onLine reliably here) ----
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } }); const page = await ctx.newPage()
  await page.goto(origin + '/'); await page.evaluate(() => navigator.serviceWorker.ready); await page.waitForTimeout(800)
  await ctx.setOffline(true)
  await page.reload({ waitUntil: 'domcontentloaded' }).catch(() => undefined)
  await page.waitForTimeout(1500)
  check('Offline: app opens with a clear offline warning', (await page.getByText(/You are offline/).count()) === 1 && (await page.getByRole('button', { name: 'Sign in', exact: true }).count()) === 1)
  await page.screenshot({ path: path.join(shots, 'pwa-offline.png') })
  await ctx.close()
}
// ---- 5. iPhone: instructions, no install button ----
{
  const ctx = await phone(IPHONE); const page = await ctx.newPage()
  await page.goto(origin + '/')
  await page.getByTestId('install-banner').waitFor({ timeout: 5000 })
  const text = await page.getByTestId('install-banner').innerText()
  check('iPhone: banner explains Share > Add to Home Screen', /Add to Home Screen/.test(text) && (await page.getByRole('button', { name: 'Install', exact: true }).count()) === 0)
  check('iPhone: home-screen icon and title are declared', (await page.locator('link[rel=apple-touch-icon]').count()) === 1 && (await page.locator('meta[name=apple-mobile-web-app-title]').getAttribute('content')) === 'SpendOS')
  await page.screenshot({ path: path.join(shots, 'pwa-iphone-banner.png') })
  await ctx.close()
}
// ---- 6. Desktop and already-installed show nothing ----
{
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } }); const page = await ctx.newPage()
  await page.goto(origin + '/'); await page.waitForTimeout(500); await fire(page); await page.waitForTimeout(500)
  check('Desktop browser: no install banner', (await page.getByTestId('install-banner').count()) === 0)
  await ctx.close()
}
{
  const ctx = await phone(ANDROID); const page = await ctx.newPage()
  // an installed app runs with display-mode: standalone
  await page.addInitScript(() => { const mm = window.matchMedia.bind(window); window.matchMedia = (q) => (q.includes('display-mode: standalone') ? { matches: true, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false } : mm(q)) })
  await page.goto(origin + '/'); await page.waitForTimeout(500); await fire(page); await page.waitForTimeout(500)
  check('Already installed (standalone): no banner', (await page.getByTestId('install-banner').count()) === 0)
  await ctx.close()
}
await browser.close()
console.log(`\n${results.filter(Boolean).length}/${results.length} checks passed`)
process.exit(results.every(Boolean) ? 0 : 1)
