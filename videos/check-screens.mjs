/** Smoke test: sign in as every demo persona through the browser and open every page in its navigation.
 *  Fails on console errors, failed API calls (other than expected 403/404 probes) or visible error alerts. */
import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'
const require = createRequire('C:/Users/lenovo/AadiTech/Product/AadiProduct/MultiTenant/Aadi-MultiTenant-Platform/frontend/package.json')
const { chromium } = require('playwright')
const origin = process.env.SPENDOS_URL ?? 'http://localhost:8000'
const password = 'SpendOS@Demo26'
const shots = path.resolve('verification'); fs.mkdirSync(shots, { recursive: true })
const people = ['rahul.sharma', 'priya.sharma', 'aarav.sharma', 'sunita.sharma', 'anita.deshmukh', 'sanjay.kulkarni', 'vikram.joshi', 'neha.kapoor', 'rohit.patil', 'sneha.iyer', 'arjun.mehta', 'meera.nair', 'kiran.shah', 'divya.rao', 'sameer.patil', 'ravi.menon', 'platform.admin']
let browser
for (const o of [{ channel: 'chrome' }, { channel: 'msedge' }, {}]) { try { browser = await chromium.launch({ headless: true, ...o }); break } catch { /* try next */ } }
let failed = 0
for (const p of people) {
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 900 } })
  const page = await ctx.newPage()
  const problems = []
  page.on('console', (m) => m.type() === 'error' && !/status of (403|404)/.test(m.text()) && problems.push('console: ' + m.text()))
  page.on('pageerror', (e) => problems.push('pageerror: ' + e.message))
  page.on('response', (r) => r.url().includes('/api/') && r.status() >= 500 && problems.push(`HTTP ${r.status()} ${r.url()}`))
  await page.goto(origin + '/')
  await page.getByLabel('Email').fill(p + '@spendos.demo.test')
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('navigation').first().waitFor()
  const links = await page.locator('nav a, [role=navigation] a').evaluateAll((els) => els.map((e) => e.getAttribute('href')))
  for (const href of [...new Set(links)]) {
    await page.goto(origin + href)
    await page.waitForLoadState('networkidle')
    const err = await page.locator('.MuiAlert-standardError:not([data-testid^=insight])').allInnerTexts()
    if (err.length) problems.push(`${href}: ${err.join(' | ')}`)
  }
  if (['rahul.sharma', 'sanjay.kulkarni', 'platform.admin'].includes(p)) await page.screenshot({ path: path.join(shots, `smoke-${p}.png`) })
  console.log(`${problems.length ? 'FAIL' : 'PASS'} ${p} (${links.length} pages)`, problems.slice(0, 4).join('\n   '))
  failed += problems.length ? 1 : 0
  await ctx.close()
}
await browser.close()
process.exit(failed ? 1 : 0)
