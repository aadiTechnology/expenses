import { createRequire } from 'node:module'
import fs from 'node:fs'
const require = createRequire('C:/Users/lenovo/AadiTech/Product/AadiProduct/MultiTenant/Aadi-MultiTenant-Platform/frontend/package.json')
const { chromium } = require('playwright')
const axeSource = fs.readFileSync(new URL('./node_modules/axe-core/axe.min.js', import.meta.url), 'utf8')
const b = await chromium.launch({ channel: 'chrome', headless: true })
const page = await (await b.newContext({ viewport: { width: 1400, height: 900 } })).newPage()
await page.goto('http://localhost:8001/')
await page.getByLabel('Email').fill('sanjay.kulkarni@spendos.demo.test'); await page.getByLabel('Password').fill('SpendOS@Demo26')
await page.getByRole('button', { name: 'Sign in', exact: true }).click(); await page.getByRole('navigation').first().waitFor()
for (const href of ['/', '/budgets', '/growth']) {
  await page.goto('http://localhost:8001' + href); await page.waitForLoadState('networkidle'); await page.evaluate(axeSource)
  const res = await page.evaluate(() => axe.run(document, { runOnly: ['wcag21a','wcag21aa'] }))
  for (const v of res.violations.filter((x) => ['label-content-name-mismatch','list'].includes(x.id))) {
    for (const n of v.nodes.slice(0, 4)) console.log(href, v.id, '|', n.html.slice(0, 110), '|', (n.any[0]?.message || '').slice(0, 140))
  }
}
await b.close()
