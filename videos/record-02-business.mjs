/**
 * Video 02 - Business edition (Sprint S1, parts M4-M5): Aadi Technology expense, approval and reimbursement workflow,
 * budgets, role-based visibility and permission-aware AI. Synthetic illustrative demo data only.
 * Run against a RECORDING database. Env: SPENDOS_URL (default http://localhost:8001).
 */
import { assertNoSecret, click, heading, nav, origin, password, pick, scroll, signInTyped, signOut, typeSlow } from './common.mjs'
import { recordVideo } from './lib.mjs'

const NAME = '02-spendos-business-edition'
const dialog = (page) => page.getByRole('dialog')
const drawer = (page) => page.locator('.MuiDrawer-paperAnchorRight')

const scenes = [
  {
    chapter: 'Chapter 1 - Introduction', title: 'Aadi Technology and the approval chain',
    narration: 'This video shows the business edition of Aadi Spend O S, using Aadi Technology, an illustrative I T company with five departments and six projects. The numbers are demonstration figures, not real accounts. We follow one travel expense through its full life: an employee submits it, the project manager approves it, finance verifies it, and finance marks the reimbursement paid. We also see what each role is not allowed to do.',
    actions: 'Show the sign-in page.', expected: 'Sign-in form.',
    run: async (page) => { await page.goto(origin + '/', { waitUntil: 'domcontentloaded' }); await page.getByRole('button', { name: 'Sign in', exact: true }).waitFor() },
  },
  {
    chapter: 'Chapter 2 - Employee', title: 'Employee sees only their own work',
    narration: 'Arjun Mehta is a software engineer. His menu is short: dashboard, his own transactions, my expenses and reimbursements. He sees no budgets, no approvals, no settings and no one else s expenses. His dashboard figures are his own claims only.',
    actions: 'Sign in as Arjun Mehta and view Dashboard and My Expenses.', expected: 'Own claims only; limited menu.',
    run: async (page) => {
      await signInTyped(page, 'arjun.mehta')
      await heading(page, 'Dashboard')
      await nav(page, 'My Expenses')
      await page.getByRole('table', { name: 'Transactions' }).waitFor()
    },
  },
  {
    chapter: 'Chapter 2 - Employee', title: 'Validation: project is required',
    narration: 'Arjun records a taxi and train trip to a client site. The form is simpler for employees: no payment account, because he paid out of his own pocket. This organization requires every expense to be charged to a project, so submitting without one is refused with a clear message.',
    actions: 'Open New expense and submit without a project.', expected: 'Validation message for project.',
    run: async (page) => {
      await click(page.getByRole('button', { name: 'New expense' }))
      const d = dialog(page)
      await typeSlow(d.getByLabel('Amount'), '3500')
      await pick(d, 'Category', 'Travel')
      await typeSlow(d.getByLabel('Description'), 'Client site visit - Greenfield School')
      await click(d.getByRole('button', { name: 'Submit for approval' }))
      await page.getByText('Choose the project to charge').waitFor()
    },
  },
  {
    chapter: 'Chapter 2 - Employee', title: 'Submit the expense',
    narration: 'Choosing the project R I T e School and submitting creates the claim. The server picks the approval policy: amounts of one thousand rupees or more need the project manager first, then finance. Small claims go straight to finance. The claim now shows awaiting approval.',
    actions: 'Choose RITeSchool and submit.', expected: 'Claim appears with "Awaiting approval".',
    run: async (page) => {
      const d = dialog(page)
      await pick(d, 'Project', 'RITeSchool')
      await click(d.getByRole('button', { name: 'Submit for approval' }))
      await page.getByText('Submitted for approval').waitFor()
      await page.getByText('Client site visit - Greenfield School').first().waitFor()
    },
  },
  {
    chapter: 'Chapter 3 - Approver', title: 'A different project manager cannot approve it',
    narration: 'Rohit Patil manages other projects. Even though he is a project manager, the claim for R I T e School does not appear in his approvals, and the server would refuse the action if he tried to call it directly. Approval rights depend on the project, not just the job title.',
    actions: 'Sign in as Rohit Patil and open Approvals.', expected: 'No claim for RITeSchool in his list.',
    run: async (page) => {
      await signOut(page)
      await signInTyped(page, 'rohit.patil')
      await nav(page, 'Approvals')
      await page.getByText(/Nothing is waiting|Pending approvals/).first().waitFor()
    },
  },
  {
    chapter: 'Chapter 3 - Approver', title: 'The right project manager approves',
    narration: 'Sneha Iyer manages R I T e School. Her approvals list shows the new claim and the marketing team s event stall deposit. Opening one shows the amount, the employee, the history and the approval trail. She cannot reject without giving a reason, which is shown next, and then she approves.',
    actions: 'Sign in as Sneha Iyer; open the stall deposit claim; press Reject without a reason.', expected: 'Reject dialog requires a reason.',
    run: async (page) => {
      await signOut(page)
      await signInTyped(page, 'sneha.iyer')
      await nav(page, 'Approvals')
      await page.getByRole('table', { name: 'Pending approvals' }).waitFor()
      await click(page.getByRole('row', { name: /Event stall deposit/ }).getByRole('button', { name: 'Review' }))
      await page.getByText('Approval trail').waitFor()
      await click(drawer(page).getByRole('button', { name: 'Reject', exact: true }))
      await click(dialog(page).getByRole('button', { name: 'Reject', exact: true }))
      await page.getByText('A rejection reason is required').last().waitFor()
    },
  },
  {
    chapter: 'Chapter 3 - Approver', title: 'Rejecting with a reason, and approving',
    narration: 'First, a different claim, the event stall deposit from the marketing team, is rejected with the reason: please get a second quote. The employee will see that reason and can resubmit. Back on Arjun s claim, Sneha presses approve. It moves on to finance.',
    actions: 'Reject the stall deposit with a reason; approve Arjun s claim.', expected: 'Rejected with reason; approved claim moves to finance.',
    run: async (page) => {
      await typeSlow(dialog(page).getByLabel('Reason (required)'), 'Please get a second quote first')
      await click(dialog(page).getByRole('button', { name: 'Reject', exact: true }))
      await page.getByText('Rejected', { exact: true }).first().waitFor()
      await page.keyboard.press('Escape')
      await page.reload()
      await page.getByRole('table', { name: 'Pending approvals' }).waitFor()
      await click(page.getByRole('row', { name: /Client site visit - Greenfield School/ }).getByRole('button', { name: 'Review' }))
      await click(drawer(page).getByRole('button', { name: 'Approve' }))
      await page.getByText('Approved', { exact: true }).first().waitFor()
    },
  },
  {
    chapter: 'Chapter 4 - Finance', title: 'Finance verifies and pays',
    narration: 'Sanjay Kulkarni is the finance manager. The claim is waiting for finance verification. He verifies it, which confirms the receipts are in order, and the claim becomes ready to pay. Finance cannot skip the project manager step, and nobody can approve their own claim.',
    actions: 'Sign in as Sanjay; open the claim; Verify.', expected: 'Status becomes Ready to pay.',
    run: async (page) => {
      await signOut(page)
      await signInTyped(page, 'sanjay.kulkarni')
      await nav(page, 'Approvals')
      await page.getByRole('table', { name: 'Pending approvals' }).waitFor()
      await click(page.getByRole('row', { name: /Client site visit - Greenfield School/ }).getByRole('button', { name: 'Review' }))
      await click(drawer(page).getByRole('button', { name: 'Verify' }))
      await page.getByText('Ready to pay').first().waitFor()
    },
  },
  {
    chapter: 'Chapter 4 - Finance', title: 'Mark the reimbursement paid',
    narration: 'Now finance marks the reimbursement paid and chooses the account it came from, the H D F C current account. Only now does the expense count in actual spend and reduce that account s balance, by exactly three thousand five hundred rupees. The approval trail and the history record every step with who did it.',
    actions: 'Mark reimbursement paid from HDFC Current Account.', expected: 'Status Paid; trail shows two approved levels.',
    run: async (page) => {
      await click(drawer(page).getByRole('button', { name: 'Mark reimbursement paid' }))
      await pick(dialog(page), 'Paid from account', 'HDFC Current Account')
      await click(dialog(page).getByRole('button', { name: 'Confirm payment' }))
      await page.getByText('Marked as paid').waitFor()
      await page.waitForTimeout(800)
    },
  },
  {
    chapter: 'Chapter 4 - Finance', title: 'Reimbursements overview',
    narration: 'The reimbursements page totals what is still pending and what has been paid, with every claim listed and its status. The pending figure excludes paid claims, and the paid figure excludes anything still moving through approval.',
    actions: 'Open Reimbursements.', expected: 'Pending and paid totals.',
    run: async (page) => { await page.keyboard.press('Escape'); await nav(page, 'Reimbursements'); await page.getByRole('table', { name: 'Reimbursements' }).waitFor(); await scroll(page, 300, 3) },
  },
  {
    chapter: 'Chapter 5 - Budgets and reports', title: 'Budget against actual',
    narration: 'Finance compares each budget with actual spend. The organization wide budget is five lakh fifty thousand rupees against five lakh of expenses in October, ninety one percent used, which crossed the ninety percent alert threshold once. Department, project and campaign budgets are listed too, each with remaining amount and utilisation.',
    actions: 'Open Budgets for October 2026.', expected: 'Budget table with utilisation.',
    run: async (page) => {
      await nav(page, 'Budgets')
      await page.getByLabel('Month').fill('2026-10')
      await page.getByRole('table', { name: 'Budgets' }).waitFor()
      await scroll(page, 400, 4)
    },
  },
  {
    chapter: 'Chapter 5 - Budgets and reports', title: 'Business dashboard',
    narration: 'The business dashboard totals income and expenses, shows the simplified operating surplus with a reminder that it is not audited profit, then expenses by department and by project, pending approvals, and the budget utilisation. October income is eight lakh fifty thousand and expenses five lakh, matching the illustrative monthly summary.',
    actions: 'Open the Dashboard for October 2026.', expected: 'Business dashboard widgets.',
    run: async (page) => {
      await nav(page, 'Dashboard')
      await page.getByLabel('Month').fill('2026-10')
      await page.getByText('Department-wise expenses').waitFor()
      await scroll(page, 700, 6)
    },
  },
  {
    chapter: 'Chapter 6 - Administrator', title: 'Admin creates a project budget',
    narration: 'Anita Deshmukh is the organization admin. She creates a new budget for the Preschool E R P project for November: eighty thousand rupees. Budgets use the same engine as personal budgets, with thresholds at fifty, seventy five, ninety and one hundred percent.',
    actions: 'Sign in as Anita; create a project budget.', expected: 'New budget appears in the list.',
    run: async (page) => {
      await signOut(page)
      await signInTyped(page, 'anita.deshmukh')
      await nav(page, 'Budgets')
      await click(page.getByRole('button', { name: 'New budget' }))
      const d = dialog(page)
      await typeSlow(d.getByLabel('Budget name'), 'Preschool ERP - November')
      await pick(d, 'Applies to', 'A project')
      await pick(d, 'Which one', 'Preschool ERP')
      await d.getByLabel('Month').fill('2026-11')
      await typeSlow(d.getByLabel('Amount'), '80000')
      await click(d.getByRole('button', { name: 'Save', exact: true }))
      await page.getByText('Budget created').waitFor()
      await page.getByLabel('Month').first().fill('2026-11')
      await page.getByText('Preschool ERP - November').waitFor()
    },
  },
  {
    chapter: 'Chapter 6 - Administrator', title: 'Project-wise financial reports',
    narration: 'The admin reviews project wise expenditure. Shared costs such as the office rent are allocated across three projects, ten thousand, six thousand and four thousand, and the allocations must add up exactly to the original twenty thousand rupees, or the system refuses to save. The project totals add up to the five lakh of total expenses.',
    actions: 'Open Reports, Project expenditure for October.', expected: 'Project table that totals five lakh.',
    run: async (page) => {
      await nav(page, 'Reports')
      await pick(page, 'Report', 'Project expenditure')
      await page.getByLabel('Month').fill('2026-10')
      await page.getByRole('table', { name: /Project expenditure/ }).waitFor()
    },
  },
  {
    chapter: 'Chapter 6 - Administrator', title: 'Roles, policies and audit',
    narration: 'In organization settings the admin manages members and roles, the approval policies that decide who approves what, and the audit log. The log lists every financial and configuration change with who made it, including the payment we just made.',
    actions: 'Open Organization Settings, Approval policies, Audit log.', expected: 'Policies and audit entries.',
    run: async (page) => {
      await nav(page, 'Organization Settings')
      await click(page.getByRole('tab', { name: 'Approval policies' }))
      await page.getByRole('table', { name: 'Approval policies' }).waitFor()
      await click(page.getByRole('tab', { name: 'Audit log' }))
      await page.getByRole('table', { name: 'Audit log' }).waitFor()
    },
  },
  {
    chapter: 'Chapter 7 - Managers', title: 'A department manager sees only their department',
    narration: 'Vikram Joshi heads Software Development. His department expenditure report lists only Software Development. Marketing, Administration and the others are not included, because the server filters every query to what his role may see.',
    actions: 'Sign in as Vikram; open Reports, Department expenditure.', expected: 'Single department in the report.',
    run: async (page) => {
      await signOut(page)
      await signInTyped(page, 'vikram.joshi')
      await nav(page, 'Reports')
      await pick(page, 'Report', 'Department expenditure')
      await page.getByLabel('Month').fill('2026-10')
      await page.getByRole('table', { name: /Department expenditure/ }).waitFor()
    },
  },
  {
    chapter: 'Chapter 8 - AI questions', title: 'AI answers within permissions',
    narration: 'The assistant answers questions about project spending, but only from records the person may see. Rohit Patil manages Multitenant C R M, so he gets the total and the source transactions.',
    actions: 'Sign in as Rohit; ask about Multitenant CRM.', expected: 'Answer with source transactions.',
    run: async (page) => {
      await signOut(page)
      await signInTyped(page, 'rohit.patil')
      await nav(page, 'AI Assistant')
      await click(page.getByRole('tab', { name: 'Ask a question' }))
      await click(page.getByRole('button', { name: 'How much did we spend on Multitenant CRM?' }))
      await page.getByText(/Multitenant CRM spending/).waitFor()
    },
  },
  {
    chapter: 'Chapter 8 - AI questions', title: 'The same question from an unauthorised employee',
    narration: 'Arjun asks the identical question. The answer is that there is no spending he is authorised to see. The assistant does not reveal that the project exists or any of its figures, because it can never read more than the person s own permissions allow.',
    actions: 'Sign in as Arjun; ask the same question.', expected: 'No spending visible to him.',
    run: async (page) => {
      await signOut(page)
      await signInTyped(page, 'arjun.mehta')
      await nav(page, 'AI Assistant')
      await click(page.getByRole('tab', { name: 'Ask a question' }))
      await click(page.getByRole('button', { name: 'How much did we spend on Multitenant CRM?' }))
      await page.getByText(/no spending/).waitFor()
    },
  },
  {
    chapter: 'Chapter 8 - AI questions', title: 'Server-side enforcement',
    narration: 'Finally, a direct test of the server. From inside Arjun s signed in browser we call the audit log interface and a colleague s transaction directly, bypassing the screens. The server answers forbidden and not found. Permissions are enforced by the backend, not by hiding buttons.',
    actions: 'Call /audit and a colleague transaction directly from the page.', expected: 'HTTP 403 and 404 shown on screen.',
    run: async (page) => {
      const out = await page.evaluate(async () => {
        const t = sessionStorage.getItem('spendos.token')
        const h = { Authorization: `Bearer ${t}` }
        const a = await fetch('/api/v1/audit', { headers: h })
        const b = await fetch('/api/v1/transactions/txn_aadi_c2', { headers: h })
        const text = `Direct API test as Arjun:  GET /audit -> ${a.status} ${(await a.json()).detail}   |   GET colleague transaction -> ${b.status} ${(await b.json()).detail}`
        const el = document.createElement('div')
        el.textContent = text
        el.setAttribute('style', 'position:fixed;left:260px;right:20px;bottom:20px;z-index:99999;background:#1b1f3b;color:#fff;padding:16px 20px;border-radius:10px;font:600 16px Segoe UI')
        document.body.appendChild(el)
        return text
      })
      if (!out.includes('403') || !out.includes('404')) throw new Error('Unexpected API answers: ' + out)
    },
  },
  {
    chapter: 'Chapter 9 - Wrap up', title: 'What to browse next',
    narration: 'That was the business edition. To reproduce it yourself, use Arjun for the employee view, Sneha for approvals, Sanjay for finance, Anita for administration, Vikram for a department view and Ravi, the auditor, for read only access. All use the demo accounts panel. This video shows the responsive web application. The native phone application is not part of this sprint.',
    actions: 'Sign out.', expected: 'Sign-in page.',
    run: async (page) => { await signOut(page) },
  },
]

await recordVideo({ name: NAME, scenes, password, check: assertNoSecret, fixedTime: '2026-11-02T10:30:00+05:30' })
