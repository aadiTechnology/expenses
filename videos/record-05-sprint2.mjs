/**
 * Video 05 - Sprint S2 gap closure: sign-in lockout, recurring payments with reminders and monthly summary, family allocation of
 * shared expenses and contributions, personal data download and account deletion, Hindi/Marathi navigation.
 * Synthetic data only. Run against a RECORDING database. Env: SPENDOS_URL (default http://localhost:8001).
 */
import { assertNoSecret, click, heading, nav, origin, password, pick, scroll, signInTyped, signOut, typeSlow } from './common.mjs'
import { recordVideo } from './lib.mjs'

const NAME = '05-spendos-sprint-2-gap-closure'
const dialog = (page) => page.getByRole('dialog')
const throwaway = 'Throwaway2026'

async function register(page, name, mail) {
  await page.goto(origin + '/', { waitUntil: 'domcontentloaded' })
  await click(page.getByRole('link', { name: 'Create an account' }))
  await typeSlow(page.getByLabel('Your name'), name)
  await typeSlow(page.getByLabel('Email'), mail)
  await typeSlow(page.getByLabel('Password'), throwaway)
  await click(page.getByRole('button', { name: 'Create account', exact: true }))
  await page.getByRole('navigation').first().waitFor()
}

const scenes = [
  {
    chapter: 'Chapter 1 - Introduction', title: 'What this sprint adds',
    narration: 'This second sprint closes gaps that were listed at the end of the first one. It adds sign in lockout, recurring payments with reminders and a monthly summary, family allocation of shared expenses with a contributions report, a personal data download and account deletion, and Hindi and Marathi navigation. It also reports a first performance measurement and an accessibility scan. As before, everything is synthetic demo data.',
    actions: 'Show the sign-in page.', expected: 'Sign-in form.',
    run: async (page) => { await page.goto(origin + '/', { waitUntil: 'domcontentloaded' }); await page.getByRole('button', { name: 'Sign in', exact: true }).waitFor() },
  },
  {
    chapter: 'Chapter 2 - Sign-in protection', title: 'Lockout after repeated failures',
    narration: 'First, protection against password guessing. We create a throwaway account, sign out, and then try the wrong password five times. Each attempt gets the same neutral message, which does not reveal whether the email exists. On the sixth attempt, even the correct password is refused, because the account is locked for fifteen minutes. Resetting the password through the email link unlocks it earlier.',
    actions: 'Register a throwaway account; sign out; five wrong passwords; then the correct one.', expected: 'Neutral error five times, then a lockout message.',
    run: async (page) => {
      await register(page, 'Lock Demo', 'lock.demo@example.test')
      await signOut(page)
      for (let i = 0; i < 5; i += 1) {
        await page.getByLabel('Email').fill('lock.demo@example.test')
        await page.getByLabel('Password').fill('wrong-guess-' + i)
        await click(page.getByRole('button', { name: 'Sign in', exact: true }))
        await page.getByText('Email or password is incorrect').waitFor()
      }
      await page.getByLabel('Password').fill(throwaway)
      await click(page.getByRole('button', { name: 'Sign in', exact: true }))
      await page.getByText(/Too many failed attempts/).waitFor()
    },
  },
  {
    chapter: 'Chapter 3 - Notifications', title: 'Reminders and the monthly summary',
    narration: 'Back as Rahul, the household owner. Rahul has told the system about his monthly house rent on the eighteenth. Because today, in this recording, is the sixteenth of October, the system raised a reminder two days ahead, and also a summary of the previous month with income, expenses and the difference. Both are created only once, however many times the app is opened, and each can be switched off in the preferences.',
    actions: 'Sign in as Rahul and open Settings, Notifications.', expected: 'A rent reminder and a September summary.',
    run: async (page) => {
      await signInTyped(page, 'rahul.sharma')
      await page.waitForTimeout(1500)
      await nav(page, 'Settings')
      await click(page.getByRole('tab', { name: 'Notifications' }))
      await page.getByText(/Payment due 18 Oct: House rent/).waitFor()
      await page.getByText(/Monthly summary for 2026-09/).waitFor()
    },
  },
  {
    chapter: 'Chapter 3 - Notifications', title: 'Managing recurring payments',
    narration: 'The recurring payments tab lists what the household expects every month: rent, internet and an entertainment subscription. Rahul adds a gym membership of fifteen hundred rupees due on the twentieth. The day is validated, so a thirty fifth of the month would be refused. Only people who manage money can change this list; an employee in the business edition cannot.',
    actions: 'Open Recurring payments and add a gym membership.', expected: 'New row in the table.',
    run: async (page) => {
      await click(page.getByRole('tab', { name: 'Recurring payments' }))
      await page.getByRole('table', { name: 'Recurring payments' }).waitFor()
      await click(page.getByRole('button', { name: 'Add recurring payment' }))
      const d = dialog(page)
      await typeSlow(d.getByLabel('What is it for?'), 'Gym membership')
      await typeSlow(d.getByLabel('Amount'), '1500')
      await d.getByLabel('Day of month (1-31)').fill('20')
      await click(d.getByRole('button', { name: 'Save', exact: true }))
      await page.getByText('Recurring payment added').waitFor()
      await page.getByRole('cell', { name: 'Gym membership' }).waitFor()
    },
  },
  {
    chapter: 'Chapter 4 - Family', title: 'Allocating a shared expense',
    narration: 'Now shared household costs. Rahul records a two thousand rupee pantry order and marks it as a shared household expense. A new option lets him allocate the cost between family members. Split equally divides it three ways, down to the paisa. If he changes one share so the total no longer matches, the screen turns red and the server would refuse to save, because allocations must add up to the full amount.',
    actions: 'Add a shared expense and split it between members.', expected: 'Shares shown; mismatch highlighted.',
    run: async (page) => {
      await nav(page, 'Add Expense')
      await typeSlow(page.getByLabel('Amount'), '2000')
      await pick(page, 'Category', 'Household')
      await typeSlow(page.getByLabel('Description'), 'Shared pantry order')
      await pick(page, 'Payment account', 'Cash in Hand')
      await click(page.getByLabel('Shared household expense'))
      await click(page.getByRole('button', { name: 'Allocate between family members' }))
      await click(page.getByRole('button', { name: 'Split equally' }))
      await page.getByText(/Allocated 2000.00 of 2000.00/).waitFor()
      await page.getByLabel('Share', { exact: true }).first().fill('700')
      await page.getByText(/shares must add up/).waitFor()
    },
  },
  {
    chapter: 'Chapter 4 - Family', title: 'Save the corrected split',
    narration: 'Pressing save with the wrong total is refused with a clear message. Rahul corrects it by splitting equally again, and the expense is saved. Each share is stored against the member who bears it.',
    actions: 'Save with a mismatch, then fix and save.', expected: 'Refusal, then Saved.',
    run: async (page) => {
      await click(page.getByRole('button', { name: 'Save', exact: true }))
      await page.getByText(/must match/).waitFor()
      await click(page.getByRole('button', { name: 'Split equally' }))
      await page.getByText(/Allocated 2000.00 of 2000.00/).waitFor()
      await click(page.getByRole('button', { name: 'Save', exact: true }))
      await page.getByText('Saved', { exact: true }).waitFor()
    },
  },
  {
    chapter: 'Chapter 4 - Family', title: 'Contributions report',
    narration: 'The new family contributions report compares what each member earned with their share of the shared expenses for the month. The share column adds up to the total of the shared expenses, which is checked by an automated test, and refunds on shared items reduce it. Spending by member also uses these allocations.',
    actions: 'Open Reports, Family contributions for October.', expected: 'Contribution table.',
    run: async (page) => {
      await nav(page, 'Reports')
      await pick(page, 'Report', 'Family contributions')
      await page.getByLabel('Month').fill('2026-10')
      await page.getByRole('table', { name: /Family contributions/ }).waitFor()
    },
  },
  {
    chapter: 'Chapter 5 - Privacy', title: 'Download my data',
    narration: 'Under privacy and data, anyone can download a file with their own profile, memberships and the transactions their role lets them see. The download itself is recorded in the audit history.',
    actions: 'Open Settings, Privacy and data, download.', expected: 'Download starts.',
    run: async (page) => {
      await nav(page, 'Settings')
      await click(page.getByRole('tab', { name: 'Privacy & data' }))
      const [dl] = await Promise.all([page.waitForEvent('download'), click(page.getByRole('button', { name: 'Download my data' }))])
      if (!dl.suggestedFilename().endsWith('.json')) throw new Error('Unexpected download')
    },
  },
  {
    chapter: 'Chapter 5 - Privacy', title: 'Demo accounts are protected',
    narration: 'Deleting an account asks for the password again. This is a shared demo account, so the system refuses, and the demo cannot be broken by accident. Real accounts are deleted, as the next scene shows.',
    actions: 'Try to delete the demo account.', expected: 'Refusal message.',
    run: async (page) => {
      await click(page.getByRole('button', { name: 'Delete my account' }))
      await page.getByLabel('Confirm with your password').fill(password)
      await click(dialog(page).getByRole('button', { name: 'Delete permanently' }))
      await page.getByText(/Demo accounts cannot be deleted/).waitFor()
    },
  },
  {
    chapter: 'Chapter 5 - Privacy', title: 'Deleting a real account',
    narration: 'We create another throwaway account and delete it. The sign in is closed, the name and email are removed, and because this person is the only member of their workspace, the whole workspace is deleted with it. Trying to sign in afterwards fails. An administrator of a workspace with other members must first hand over the role.',
    actions: 'Register, delete the account, try to sign in again.', expected: 'Back on sign-in; login refused.',
    run: async (page) => {
      await page.keyboard.press('Escape')
      await signOut(page)
      await register(page, 'Delete Demo', 'delete.demo@example.test')
      await nav(page, 'Settings')
      await click(page.getByRole('tab', { name: 'Privacy & data' }))
      await click(page.getByRole('button', { name: 'Delete my account' }))
      await page.getByLabel('Confirm with your password').fill(throwaway)
      await click(dialog(page).getByRole('button', { name: 'Delete permanently' }))
      await page.getByRole('button', { name: 'Sign in', exact: true }).waitFor()
      await page.getByLabel('Email').fill('delete.demo@example.test')
      await page.getByLabel('Password').fill(throwaway)
      await click(page.getByRole('button', { name: 'Sign in', exact: true }))
      await page.getByText('Email or password is incorrect').waitFor()
    },
  },
  {
    chapter: 'Chapter 6 - Languages', title: 'Hindi and Marathi navigation',
    narration: 'The language menu under the person s name switches the navigation and page titles to Hindi or Marathi. This is a first draft that covers menus and page titles only, and the wording needs review by a native speaker before release. The choice is remembered on this device.',
    actions: 'Sign in as Rahul and switch the language to Hindi, then Marathi, then English.', expected: 'Navigation in Hindi, then Marathi.',
    run: async (page) => {
      await signInTyped(page, 'rahul.sharma')
      await click(page.getByTestId('account-menu'))
      await click(page.getByTestId('lang-hi'))
      await page.getByRole('link', { name: 'डैशबोर्ड' }).waitFor()
      await page.waitForTimeout(1800)
      await click(page.getByTestId('account-menu'))
      await click(page.getByTestId('lang-mr'))
      await page.getByRole('link', { name: 'अहवाल' }).waitFor()
      await page.waitForTimeout(1800)
      await click(page.getByTestId('account-menu'))
      await click(page.getByTestId('lang-en'))
      await page.getByRole('link', { name: 'Reports', exact: true }).waitFor()
    },
  },
  {
    chapter: 'Chapter 7 - Business', title: 'Recurring payments for an organization',
    narration: 'The same feature serves the business edition. Sanjay, the finance manager, sees the organization s recurring payments, Azure hosting, office rent and the GitHub subscription, and is reminded three days before each is due. The reminders go to the people who manage money, not to every employee.',
    actions: 'Sign in as Sanjay; open Settings, Recurring payments.', expected: 'Three recurring payments.',
    run: async (page) => {
      await signOut(page)
      await signInTyped(page, 'sanjay.kulkarni')
      await nav(page, 'Organization Settings')
      await click(page.getByRole('tab', { name: 'Recurring payments' }))
      await page.getByRole('cell', { name: 'Azure hosting' }).waitFor()
    },
  },
  {
    chapter: 'Chapter 8 - Wrap up', title: 'Measured results and what remains',
    narration: 'Two measurements accompany this sprint, both written up in the sprint report. With twenty five thousand transactions in one organization on PostgreSQL, the dashboard took about one point three seconds, down from eight seconds before the queries were rewritten, and the transaction list about twenty milliseconds. An automated accessibility scan of thirty five page views found no violations after fixes, though it is not a full audit. Still open: a native phone app, a real O C R and language model provider, Redis and S three storage, live ad platform connections, and native speaker review of the translations.',
    actions: 'Sign out.', expected: 'Sign-in page.',
    run: async (page) => { await signOut(page) },
  },
]

await recordVideo({ name: NAME, scenes, password, check: assertNoSecret, fixedTime: '2026-10-16T10:00:00+05:30' })
