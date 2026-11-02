// Two-origin check: UI served from one host, API on another (like expenses.* and expensesapi.*).
import { createRequire } from 'node:module'
const require = createRequire('C:/Users/lenovo/AadiTech/Product/AadiProduct/MultiTenant/Aadi-MultiTenant-Platform/frontend/package.json')
const { chromium } = require('playwright')
const ui = process.env.UI ?? 'http://127.0.0.1:8010'
let b; for (const o of [{ channel: 'chrome' }, { channel: 'msedge' }, {}]) { try { b = await chromium.launch({ headless: true, ...o }); break } catch { /* next */ } }
const page = await b.newPage()
const apiHosts = new Set(); const errors = []
page.on('request', (r) => r.url().includes('/api/v1/') && apiHosts.add(new URL(r.url()).origin))
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
await page.goto(ui + '/')
await page.getByTestId('toggle-demo').waitFor()
console.log('Create-an-account link shown:', await page.getByRole('link', { name: 'Create an account' }).count())
await page.getByLabel('Email').fill('sanjay.kulkarni@spendos.demo.test'); await page.getByLabel('Password').fill('SpendOS@Demo26')
await page.getByRole('button', { name: 'Sign in', exact: true }).click()
await page.getByRole('heading', { name: 'Dashboard', exact: true }).waitFor()
await page.getByText('Category-wise spending').waitFor()
console.log('UI origin:', new URL(page.url()).origin, '| API origins used:', [...apiHosts].join(', '), '| console errors:', errors.length, errors.slice(0, 2))
await b.close()
