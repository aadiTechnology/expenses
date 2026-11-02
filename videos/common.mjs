/** Helpers shared by the SpendOS sprint recorders. The demo password is typed only into masked fields. */
import { click, loadPassword, origin } from './lib.mjs'

export const password = loadPassword()
export const email = (key) => `${key}@spendos.demo.test`

export async function signInTyped(page, key) {
  await page.goto(origin + '/', { waitUntil: 'domcontentloaded' })
  await page.getByLabel('Email').fill(email(key))
  const field = page.getByLabel('Password')
  await field.fill(password)
  if ((await field.getAttribute('type')) !== 'password') throw new Error('The password field is not masked')
  await click(page.getByRole('button', { name: 'Sign in', exact: true }))
  await page.getByRole('navigation').first().waitFor()
}

export async function signOut(page) {
  // close any open side panel or dialog first, otherwise it covers the account menu
  while (await page.locator('.MuiDrawer-paperAnchorRight, .MuiDialog-container').count()) {
    await page.keyboard.press('Escape')
    await page.waitForTimeout(500)
  }
  await click(page.getByTestId('account-menu'))
  await click(page.getByRole('menuitem', { name: 'Sign out' }))
  await page.getByRole('button', { name: 'Sign in', exact: true }).waitFor()
}

export const nav = async (page, name) => {
  await click(page.getByRole('navigation').getByRole('link', { name, exact: true }))
  await page.waitForLoadState('networkidle')
}

/** Open a MUI select by its label and choose an option. `scope` limits the search (a dialog, the main area...). */
export async function pick(scope, label, option) {
  // required fields render their label as "From *", so match with an optional asterisk
  const box = scope.getByLabel(new RegExp(`^${label}\\b`)).first()
  await click(box)
  await (typeof scope.page === 'function' ? scope.page() : scope).getByRole('option', { name: option, exact: true }).click()
}

export async function scroll(page, pixels, steps = 6) {
  for (let i = 0; i < steps; i += 1) {
    await page.mouse.wheel(0, pixels / steps)
    await page.waitForTimeout(220)
  }
}

export async function typeSlow(locator, text) {
  await locator.click()
  await locator.pressSequentially(text, { delay: 55 })
}

export async function assertNoSecret(page) {
  if ((await page.locator('body').innerText()).includes(password)) throw new Error('The demo password is visible on screen')
}

export const heading = (page, name) => page.getByRole('heading', { name, exact: true }).waitFor()
export { click, origin }

/** Call an API path directly from the signed-in page and show the raw status on screen (proves server-side enforcement). */
export async function apiProbe(page, label, path) {
  const text = await page.evaluate(async ({ label, path }) => {
    const r = await fetch(path, { headers: { Authorization: `Bearer ${sessionStorage.getItem('spendos.token')}` } })
    const b = await r.json().catch(() => ({}))
    const d = b.detail
    const msg = typeof d === 'object' ? `${d.code}: ${d.message}` : d
    const t = `Direct API call - ${label}: HTTP ${r.status} - ${msg}`
    document.getElementById('probe')?.remove()
    const el = document.createElement('div')
    el.id = 'probe'
    el.textContent = t
    el.setAttribute('style', 'position:fixed;left:20px;right:20px;bottom:20px;z-index:99999;background:#1b1f3b;color:#fff;padding:16px 20px;border-radius:10px;font:600 16px Segoe UI')
    document.body.appendChild(el)
    return t
  }, { label, path })
  return text
}
