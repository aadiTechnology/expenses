/**
 * Video 04 - the responsive web app on a 390 x 844 phone viewport (touch emulation). This is the WEB app on a phone;
 * the native React Native / Expo app is not part of this sprint. Run against a RECORDING database.
 */
import { assertNoSecret, click, email, origin, password, pick, scroll, typeSlow } from './common.mjs'
import { recordVideo } from './lib.mjs'

const NAME = '04-spendos-on-your-phone'
const menu = (page, name) => click(page.getByRole('link', { name, exact: true }))

const scenes = [
  {
    chapter: 'Chapter 1 - Introduction', title: 'The web app on a phone',
    narration: 'This short video shows Aadi Spend O S in a phone sized browser. The native phone application is not part of this release, so this is the responsive web application, which adapts its layout to a narrow screen. We sign in as Rahul Sharma, the household owner.',
    actions: 'Open the sign-in page on a phone viewport and sign in.', expected: 'Dashboard in a single column.',
    run: async (page) => {
      await page.goto(origin + '/', { waitUntil: 'domcontentloaded' })
      await page.getByLabel('Email').fill(email('rahul.sharma'))
      const f = page.getByLabel('Password')
      await f.fill(password)
      if ((await f.getAttribute('type')) !== 'password') throw new Error('The password field is not masked')
      await click(page.getByRole('button', { name: 'Sign in', exact: true }))
      await page.getByRole('heading', { name: 'Dashboard', exact: true }).waitFor()
    },
  },
  {
    chapter: 'Chapter 2 - Dashboard', title: 'Figures stack into one column',
    narration: 'The dashboard figures stack into one column, and the charts and lists follow below, readable without zooming. The menu moves into a drawer behind the menu button at the top left.',
    actions: 'Scroll the dashboard.', expected: 'Single-column cards.',
    run: async (page) => { await scroll(page, 1400, 8) },
  },
  {
    chapter: 'Chapter 3 - Navigation', title: 'The menu drawer',
    narration: 'Opening the menu shows the same navigation as on a desktop, filtered by the signed in person s role. Choosing add expense closes the drawer and opens the form.',
    actions: 'Open the menu and choose Add Expense.', expected: 'Add expense form.',
    run: async (page) => {
      await page.evaluate(() => window.scrollTo(0, 0))
      await click(page.getByRole('button', { name: 'Open menu' }))
      await page.getByRole('navigation', { name: 'Main navigation' }).waitFor()
      await menu(page, 'Add Expense')
      await page.getByLabel('Amount').waitFor()
    },
  },
  {
    chapter: 'Chapter 4 - Recording', title: 'Add an expense with a thumb',
    narration: 'The form uses large touch targets and the numeric keypad for amounts. We record one hundred and eighty rupees for vegetables paid in cash, and save. The goal in the product requirements is under fifteen seconds for a typical entry.',
    actions: 'Fill the form and save.', expected: 'Saved; transactions list.',
    run: async (page) => {
      await typeSlow(page.getByLabel('Amount'), '180')
      await pick(page, 'Category', 'Groceries')
      await typeSlow(page.getByLabel('Description'), 'Vegetables from the market')
      await pick(page, 'Payment account', 'Cash in Hand')
      await click(page.getByRole('button', { name: 'Save', exact: true }))
      await page.getByText('Saved', { exact: true }).waitFor()
    },
  },
  {
    chapter: 'Chapter 5 - Wrap up', title: 'Limits of this video',
    narration: 'The transactions list shows the new entry at the top. Wide tables scroll sideways on a phone. To be clear about scope: there is no native iOS or Android app yet, no offline mode, and no camera integration beyond the browser s file picker. Those are open decisions in the product requirements.',
    actions: 'Show the transactions list.', expected: 'List with the new entry.',
    run: async (page) => { await page.getByTestId('txn-row').first().waitFor(); await scroll(page, 300, 3) },
  },
]

await recordVideo({ name: NAME, scenes, password, check: assertNoSecret, mobile: true, fixedTime: '2026-10-27T10:30:00+05:30' })
