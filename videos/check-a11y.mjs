/** Automated accessibility scan (axe-core, WCAG 2.x A/AA rules) of every page in each persona's menu. Automated checks find only part of the issues; this is not a full WCAG audit. */
import { createRequire } from 'node:module'
import fs from 'node:fs'
const require = createRequire('C:/Users/lenovo/AadiTech/Product/AadiProduct/MultiTenant/Aadi-MultiTenant-Platform/frontend/package.json')
const { chromium } = require('playwright')
const axeSource = fs.readFileSync(new URL('./node_modules/axe-core/axe.min.js', import.meta.url), 'utf8')
const origin = process.env.SPENDOS_URL ?? 'http://localhost:8000'
const people = (process.env.PEOPLE ?? 'rahul.sharma,sanjay.kulkarni,arjun.mehta,platform.admin').split(',')
let browser
for (const o of [{ channel: 'chrome' }, { channel: 'msedge' }, {}]) { try { browser = await chromium.launch({ headless: true, ...o }); break } catch { /* next */ } }
const totals = {}; let scanned = 0, rulesPassed = 0, incomplete = 0
for (const p of people) {
  const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage()
  await page.goto(origin + '/')
  await page.getByLabel('Email').fill(p + '@spendos.demo.test'); await page.getByLabel('Password').fill('SpendOS@Demo26')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('navigation').first().waitFor()
  const links = [...new Set(await page.locator('[role=navigation] a').evaluateAll((e) => e.map((x) => x.getAttribute('href'))))]
  for (const href of links) {
    await page.goto(origin + href); await page.waitForLoadState('networkidle')
    await page.evaluate(axeSource)
    const res = await page.evaluate(() => axe.run(document, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] }))
    scanned = (typeof scanned === 'number' ? scanned : 0) + 1; rulesPassed = res.passes.length; incomplete = (incomplete ?? 0) + res.incomplete.length
    for (const v of res.violations) {
      const k = `${v.impact} ${v.id}`
      totals[k] ??= { help: v.help, pages: new Set(), nodes: 0, sample: v.nodes[0]?.target?.join(' ') }
      totals[k].pages.add(href); totals[k].nodes += v.nodes.length
    }
  }
}
await browser.close()
console.log(`Scanned ${scanned} page views; last page passed ${rulesPassed} rules; ${incomplete} items need manual review (axe 'incomplete').`)
const keys = Object.keys(totals)
if (!keys.length) console.log('No axe violations found on the scanned pages.')
for (const k of keys) console.log(`${k.padEnd(34)} ${String(totals[k].nodes).padStart(4)} nodes on ${totals[k].pages.size} page(s) - ${totals[k].help}\n    e.g. ${totals[k].sample}`)
