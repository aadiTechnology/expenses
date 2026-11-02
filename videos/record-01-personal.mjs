/**
 * Video 01 - Personal edition (Sprint S1, parts M1-M3, M6): a household replaces its expense notebook.
 * Uses the real running app and the synthetic "Rahul Sharma" demo tenant. Run against a RECORDING database
 * (it creates transactions), never the demo you browse. Env: SPENDOS_URL (default http://localhost:8001).
 */
import { assertNoSecret, click, email, heading, nav, origin, password, pick, scroll, signInTyped, signOut, typeSlow } from './common.mjs'
import { recordVideo } from './lib.mjs'

const NAME = '01-spendos-personal-edition'
const dialog = (page) => page.getByRole('dialog')

const scenes = [
  {
    chapter: 'Chapter 1 - Introduction', title: 'What this video covers',
    narration: 'This is Aadi Spend O S, a spend management platform. This video shows the personal edition, used by a household in place of a paper expense notebook. Everything you see is synthetic demo data for a fictional family, the Sharmas, in October twenty twenty six. We start on the sign in page, where a demo accounts panel lists every sample person, so a reviewer can browse on their own.',
    actions: 'Open the sign-in page and show the demo accounts panel.', expected: 'The demo personas are listed; no password is displayed.',
    run: async (page) => {
      await page.goto(origin + '/', { waitUntil: 'domcontentloaded' })
      await page.getByRole('button', { name: 'Sign in', exact: true }).waitFor()
      await click(page.getByTestId('toggle-demo'))
      await page.getByTestId('demo-accounts').waitFor()
    },
  },
  {
    chapter: 'Chapter 2 - Dashboard', title: 'Sign in as the owner',
    narration: 'Rahul Sharma is the household owner. Choosing his name fills the sign in form, and the password stays hidden behind dots. After signing in, the dashboard shows the month at a glance: income, expenses net of refunds, savings with the savings rate, and the balance across active accounts. Credit card dues are shown separately, so the card is never mistaken for cash.',
    actions: 'Pick Rahul Sharma, sign in, view the dashboard KPIs.', expected: 'Dashboard for October 2026 with four figures.',
    run: async (page) => {
      await click(page.getByRole('button', { name: 'Use Rahul Sharma' }))
      const field = page.getByLabel('Password')
      if ((await field.getAttribute('type')) !== 'password') throw new Error('The password field is not masked')
      await click(page.getByRole('button', { name: 'Sign in', exact: true }))
      await heading(page, 'Dashboard')
      await page.getByText('Category-wise spending').waitFor()
    },
  },
  {
    chapter: 'Chapter 2 - Dashboard', title: 'Spending, budgets and observations',
    narration: 'Scrolling down: spending by category, daily and monthly trends, the most recent transactions, and budget utilisation, each bar coloured by how much of the budget is used. The savings goals sit beside them. At the bottom are AI generated observations. Each one is labelled as a fact, an estimate, or an advisory flag, and always marked AI assisted.',
    actions: 'Scroll the dashboard.', expected: 'Category bars, trends, budgets, goals and labelled insights are visible.',
    run: async (page) => { await scroll(page, 900, 8) },
  },
  {
    chapter: 'Chapter 3 - Transactions', title: 'Find and inspect a transaction',
    narration: 'The transactions page lists every record the signed in person may see, ten at a time or more, with filters for type, category, account, family member and date range. Typing petrol in the search box narrows the list immediately. Opening a transaction shows its full details and its history. Every create, edit and delete is recorded in the audit history with who did it and when.',
    actions: 'Open Transactions, search for Petrol, open the first result.', expected: 'Filtered list and a detail drawer with history.',
    run: async (page) => {
      await nav(page, 'Transactions')
      await typeSlow(page.getByLabel('Search'), 'Petrol')
      await page.waitForTimeout(1200)
      await click(page.getByTestId('txn-row').first())
      await page.getByText('History').waitFor()
    },
  },
  {
    chapter: 'Chapter 4 - Recording expenses', title: 'Validation before saving',
    narration: 'Adding an expense is a short form. If someone presses save with nothing entered, the screen explains what is missing, instead of failing silently. Amounts must be positive and can have at most two decimal places, because money is stored as whole paise, never as floating point numbers.',
    actions: 'Open Add Expense and press Save on an empty form.', expected: 'Inline messages for amount and category.',
    run: async (page) => {
      await click(page.getByRole('button', { name: 'Close' }))
      await nav(page, 'Add Expense')
      await click(page.getByRole('button', { name: 'Save', exact: true }))
      await page.getByText('Enter an amount greater than zero').waitFor()
    },
  },
  {
    chapter: 'Chapter 4 - Recording expenses', title: 'Add an expense in seconds',
    narration: 'Now a real entry: three hundred and twenty rupees for an auto fare, category transport, paid from cash. The date defaults to today. One press on save records it, and the cash balance falls by exactly that amount.',
    actions: 'Fill amount, category, description and account; save.', expected: 'A "Saved" confirmation and the transaction list.',
    run: async (page) => {
      await typeSlow(page.getByLabel('Amount'), '320')
      await pick(page, 'Category', 'Transport')
      await typeSlow(page.getByLabel('Description'), 'Auto fare to the market')
      await pick(page, 'Payment account', 'Cash in Hand')
      await click(page.getByRole('button', { name: 'Save', exact: true }))
      await page.getByText('Saved', { exact: true }).waitFor()
    },
  },
  {
    chapter: 'Chapter 4 - Recording expenses', title: 'Duplicate detection',
    narration: 'The system guards against double entry. Here we try to record seven hundred rupees of petrol on the twentieth of October, which already exists. A warning appears, and nothing is saved unless the person deliberately chooses save anyway.',
    actions: 'Enter an existing petrol expense again.', expected: 'A duplicate warning with a Save anyway option; nothing saved.',
    run: async (page) => {
      await nav(page, 'Add Expense')
      await typeSlow(page.getByLabel('Amount'), '700')
      await page.getByLabel('Date').fill('2026-10-20')
      await pick(page, 'Category', 'Transport › Petrol')
      await typeSlow(page.getByLabel('Description'), 'Petrol')
      await pick(page, 'Payment account', 'PhonePe UPI')
      await click(page.getByRole('button', { name: 'Save', exact: true }))
      await page.getByText(/looks like a duplicate/).waitFor()
    },
  },
  {
    chapter: 'Chapter 5 - Accounts', title: 'Accounts and transfers',
    narration: 'The accounts page shows five accounts: cash, a bank account, a UPI wallet, a credit card and a digital wallet. Balances are calculated from the transactions, never typed in. Moving a thousand rupees from the bank to cash is a transfer. It changes both balances, but it is not counted as income or expense, and paying the card bill works the same way, so card purchases are never counted twice.',
    actions: 'Open Accounts and transfer 1000 from HDFC Savings to Cash in Hand.', expected: 'Transfer recorded; balances updated.',
    run: async (page) => {
      await nav(page, 'Accounts')
      await page.getByText('Calculated balance').first().waitFor()
      await click(page.getByRole('button', { name: 'Transfer between accounts' }))
      const d = dialog(page)
      await pick(d, 'From', 'HDFC Savings')
      await pick(d, 'To', 'Cash in Hand')
      await typeSlow(d.getByLabel('Amount'), '1000')
      await click(d.getByRole('button', { name: 'Transfer', exact: true }))
      await page.getByText(/not counted as income or expense/).waitFor()
    },
  },
  {
    chapter: 'Chapter 6 - Budgets', title: 'Monthly budgets and alerts',
    narration: 'Budgets are set for the household and for categories such as groceries or transport. Actual spend is computed from the very same transactions, so budgets and reports can never disagree. Alerts are raised at fifty, seventy five, ninety and one hundred percent, and each alert is raised only once, not repeated on every new entry.',
    actions: 'Open Budgets.', expected: 'Budget table with utilisation bars.',
    run: async (page) => { await nav(page, 'Budgets'); await page.getByLabel('Month').fill('2026-10'); await page.getByRole('table', { name: 'Budgets' }).waitFor(); await scroll(page, 300, 3) },
  },
  {
    chapter: 'Chapter 7 - AI assistant', title: 'Speak or type several expenses at once',
    narration: 'The AI assistant turns a sentence into reviewable expenses. We type: today vegetables two fifty, milk sixty and petrol five hundred. It finds three entries, suggests a category for each, and shows a confidence score. Nothing has been saved yet. The AI only suggests; a person confirms.',
    actions: 'Open AI Assistant, enter a sentence, press Find expenses.', expected: 'Three suggestions with confidence; nothing saved.',
    run: async (page) => {
      await nav(page, 'AI Assistant')
      await typeSlow(page.getByLabel('What did you spend?'), 'Today vegetables 250, milk 60 and petrol 500')
      await click(page.getByRole('button', { name: 'Find expenses' }))
      await page.getByTestId('suggestions').waitFor()
    },
  },
  {
    chapter: 'Chapter 7 - AI assistant', title: 'Confirm before saving',
    narration: 'The person can correct any date, description, category or amount, then chooses the account and confirms. Only now are the three transactions created, and each keeps a record that it was AI assisted and who confirmed it. Lines that the assistant is unsure about stay unticked until a person marks that they checked them.',
    actions: 'Choose Cash in Hand and confirm all three.', expected: 'Three transactions saved with an AI-assisted marker.',
    run: async (page) => {
      await pick(page, 'Paid from', 'Cash in Hand')
      await click(page.getByRole('button', { name: /Confirm and save 3 selected/ }))
      await page.getByText(/3 transaction\(s\) saved/).waitFor()
    },
  },
  {
    chapter: 'Chapter 7 - AI assistant', title: 'Low confidence is never saved silently',
    narration: 'Here the sentence has an item the assistant cannot categorise: pooja items four fifty. It is shown with low confidence, left unticked, and cannot be saved until the person reviews it. Low confidence results are never saved silently.',
    actions: 'Enter an unclear item.', expected: 'Row marked low confidence, unticked, requires "I checked this".',
    run: async (page) => {
      await typeSlow(page.getByLabel('What did you spend?'), 'Today pooja items 450')
      await click(page.getByRole('button', { name: 'Find expenses' }))
      await page.getByText('I checked this').waitFor()
    },
  },
  {
    chapter: 'Chapter 7 - AI assistant', title: 'Insights, estimates and advisory flags',
    narration: 'The insights tab shows facts such as the change from last month, the highest spending category and recurring payments. An unusual amount is flagged as an advisory signal, with its reason and the supporting record, and explicitly not as an error or fraud. The person can acknowledge or dismiss it, and that decision is written to the audit history. Forecasts, when present, are labelled as estimates with their assumption.',
    actions: 'Discard the unclear item, open Insights and acknowledge a flag.', expected: 'Labelled insight cards; flag acknowledged.',
    run: async (page) => {
      await click(page.getByRole('button', { name: 'Discard all' }))
      await click(page.getByRole('tab', { name: 'Insights' }))
      await page.getByTestId('insight-fact').first().waitFor()
      const ack = page.getByRole('button', { name: 'Acknowledge' }).first()
      if (await ack.count()) await click(ack)
      await scroll(page, 500, 4)
    },
  },
  {
    chapter: 'Chapter 7 - AI assistant', title: 'Ask a question',
    narration: 'Questions in plain language are answered only from records the signed in person is allowed to see. Asking how much was spent on groceries returns the total together with the source transactions it was calculated from.',
    actions: 'Open Ask a question and use the groceries example.', expected: 'An answer with source transactions.',
    run: async (page) => {
      await click(page.getByRole('tab', { name: 'Ask a question' }))
      await click(page.getByRole('button', { name: 'How much did I spend on groceries?' }))
      await page.getByText(/Groceries in/).waitFor()
    },
  },
  {
    chapter: 'Chapter 8 - Reports', title: 'Monthly reports and exports',
    narration: 'The reports page offers monthly income and expense, category wise expenses, account balances, spending per family member, budget against actual and a monthly comparison. Every report is calculated on the server from the same transactions, and can be downloaded as a C S V file or a P D F.',
    actions: 'Open Reports and switch to Budget vs actual.', expected: 'Report table with CSV and PDF buttons.',
    run: async (page) => {
      await nav(page, 'Reports')
      await page.getByRole('table').first().waitFor()
      await pick(page, 'Report', 'Budget vs actual')
      await page.getByRole('table', { name: /Budget vs actual/ }).waitFor()
    },
  },
  {
    chapter: 'Chapter 9 - Permissions', title: 'A read-only family viewer',
    narration: 'Now Sunita, the grandmother, signs in as a family viewer. The server only returns items that the family marked as shared, her menu has no add or settings pages, and even typing the add expense address directly shows that it is not available. These limits are enforced by the backend, not just by hiding buttons.',
    actions: 'Sign out; sign in as Sunita; open Transactions; try /add.', expected: 'Only shared items; /add says Not available.',
    run: async (page) => {
      await signOut(page)
      await signInTyped(page, 'sunita.sharma')
      await nav(page, 'Transactions')
      await page.getByTestId('txn-row').first().waitFor()
      await page.goto(origin + '/add')
      await page.getByText('Not available').waitFor()
    },
  },
  {
    chapter: 'Chapter 10 - Wrap up', title: 'What to browse next',
    narration: 'That was the personal edition. To explore yourself, use the demo accounts panel on the sign in page. Rahul has full access, Priya and Aarav are family members, and Sunita is a viewer. This release shows the web application. The phone application is not part of this sprint, but the web pages are responsive, which the next video shows. The following videos cover the business edition and the marketing and A I pillars.',
    actions: 'Sign out.', expected: 'Sign-in page.',
    run: async (page) => { await signOut(page) },
  },
]

await recordVideo({ name: NAME, scenes, password, check: assertNoSecret, fixedTime: '2026-10-27T10:30:00+05:30' })
