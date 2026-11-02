/**
 * Video 03 - Pillar 2 (Marketing & Sales spend) and platform entitlements (Sprint S1, FR-13 to FR-22 subset).
 * Synthetic demo data only. Run against a RECORDING database. Env: SPENDOS_URL (default http://localhost:8001).
 */
import path from 'node:path'
import { apiProbe, assertNoSecret, click, heading, nav, origin, password, pick, scroll, signInTyped, signOut, typeSlow } from './common.mjs'
import { here, recordVideo } from './lib.mjs'

const NAME = '03-spendos-growth-spend-and-entitlements'
const dialog = (page) => page.getByRole('dialog')
const asset = (f) => path.join(here, 'assets', f)

const scenes = [
  {
    chapter: 'Chapter 1 - Introduction', title: 'Three pillars, one engine',
    narration: 'Aadi products are assessed against three pillars: the software product, marketing and sales, and A I solutions. In Spend O S, marketing and sales means visibility into the money spent on growth, not a C R M. This video shows campaign spend against budget, the data import with its strict checks, and how the platform administrator switches modules on and off for each customer.',
    actions: 'Show the sign-in page.', expected: 'Sign-in form.',
    run: async (page) => { await page.goto(origin + '/', { waitUntil: 'domcontentloaded' }); await page.getByRole('button', { name: 'Sign in', exact: true }).waitFor() },
  },
  {
    chapter: 'Chapter 2 - Growth spend', title: 'Spend by campaign against budget',
    narration: 'Sanjay, the finance manager, opens Growth Spend. Each row is a campaign, a configurable dimension that the organization defined itself. It shows actual spend, budget, variance and utilisation. At the bottom, marketing spend without a campaign tag is listed separately, and the total reconciles to the marketing transactions: forty thousand rupees.',
    actions: 'Sign in as Sanjay and open Growth Spend for October.', expected: 'Campaign table with totals that reconcile.',
    run: async (page) => {
      await signInTyped(page, 'sanjay.kulkarni')
      await nav(page, 'Growth Spend')
      await page.getByLabel('Month').fill('2026-10')
      await page.getByRole('table', { name: 'Campaign spend' }).waitFor()
      await page.getByText('Total (reconciles to Marketing transactions)').waitFor()
    },
  },
  {
    chapter: 'Chapter 2 - Growth spend', title: 'Metrics are shown only when the data exists',
    narration: 'Look at the last three columns. For the internship campaign, leads and customers were imported, so cost per lead and an estimated acquisition cost are shown. For the school admissions campaign only leads exist, so the cost per lead is shown but acquisition cost says unavailable. For the webinar nothing was imported at all. The product never invents return on investment or acquisition cost without the data behind it, and says which source and attribution method any figure used.',
    actions: 'Highlight the metric columns.', expected: 'Some values numeric, others Unavailable.',
    run: async (page) => { await scroll(page, 400, 4); await page.getByText('Unavailable').first().waitFor() },
  },
  {
    chapter: 'Chapter 3 - Import', title: 'A bad file is rejected completely',
    narration: 'Finance imports results exported from the ad platform. This file has two rows, one valid and one naming a campaign that does not exist. The import is all or nothing: the system reports row three with its problem and imports nothing, so partial, misleading numbers can never appear.',
    actions: 'Import growth_bad.csv.', expected: 'Row-level error; nothing imported.',
    run: async (page) => {
      await click(page.getByRole('button', { name: 'Import growth data (CSV)' }))
      await page.getByLabel('Growth CSV file').setInputFiles(asset('growth_bad.csv'))
      await click(page.getByRole('button', { name: 'Validate and import' }))
      await page.getByText(/Row 3/).waitFor()
    },
  },
  {
    chapter: 'Chapter 3 - Import', title: 'A valid file is imported with provenance',
    narration: 'Now the corrected file. The source, the period, the currency and the attribution method, last touch self reported, are recorded with the import. The webinar row now shows fifty five leads and four customers, with cost per lead and an estimated acquisition cost, clearly labelled as estimates. The import history lists both attempts, the rejected one and the accepted one.',
    actions: 'Import growth_good.csv.', expected: 'Webinar row shows cost per lead; history lists two imports.',
    run: async (page) => {
      await page.getByLabel('Growth CSV file').setInputFiles(asset('growth_good.csv'))
      await click(page.getByRole('button', { name: 'Validate and import' }))
      await page.getByText('Growth data imported').waitFor()
      await page.getByText(/rejected/).first().waitFor()
      await scroll(page, 500, 4)
    },
  },
  {
    chapter: 'Chapter 4 - Tagging spend', title: 'Allocate an expense to a campaign',
    narration: 'Campaign and channel are optional tags on any expense. Finance records six thousand rupees of LinkedIn retargeting against the webinar campaign. The tag lives with the transaction as configuration, not as a new column in the core table, so another organization could use initiatives or regions instead.',
    actions: 'Add an expense tagged with campaign and channel.', expected: 'Saved; appears in the November growth report.',
    run: async (page) => {
      await nav(page, 'Transactions')
      await click(page.getByRole('button', { name: 'Add transaction' }))
      const d = dialog(page)
      await typeSlow(d.getByLabel('Amount'), '6000')
      await pick(d, 'Category', 'Marketing')
      await typeSlow(d.getByLabel('Description'), 'LinkedIn retargeting')
      await pick(d, 'Payment account', 'HDFC Current Account')
      await pick(d, 'Project', 'AI Product Factory')
      await pick(d, 'Campaign', 'AI Product Launch Webinar')
      await pick(d, 'Channel', 'LinkedIn')
      await click(d.getByRole('button', { name: 'Save', exact: true }))
      await page.getByText('Saved', { exact: true }).waitFor()
      await nav(page, 'Growth Spend')
      await page.getByLabel('Month').fill('2026-11')
      await page.getByText('AI Product Launch Webinar').first().waitFor()
    },
  },
  {
    chapter: 'Chapter 5 - Platform admin', title: 'Module catalogue and pillar classification',
    narration: 'The platform administrator has no access to any customer s financial records. Their screen lists every module with its pillar classification, priority, dependencies and the plans that include it. Changing a classification is itself recorded in the audit history.',
    actions: 'Sign in as the platform admin and view the catalogue.', expected: 'Module catalogue with pillars.',
    run: async (page) => {
      await signOut(page)
      await signInTyped(page, 'platform.admin')
      await page.getByRole('table', { name: 'Module catalogue' }).waitFor()
      await scroll(page, 500, 4)
    },
  },
  {
    chapter: 'Chapter 5 - Platform admin', title: 'Switch a module off for one customer',
    narration: 'Under tenant entitlements, every customer s effective decision is listed with its reason: plan, override, expired override or missing dependency. The administrator switches Growth Spend off for Aadi Technology. The data import module depends on it, so it switches off too. No code change, no separate build for that customer.',
    actions: 'Disable growth_spend for Aadi Technology.', expected: 'Override saved; dependent module off.',
    run: async (page) => {
      await click(page.getByRole('tab', { name: 'Tenant entitlements' }))
      await page.getByText('Aadi Technology (ILLUSTRATIVE DEMO)').first().waitFor()
      await click(page.getByRole('switch', { name: 'growth_spend for Aadi Technology (ILLUSTRATIVE DEMO)' }))
      await page.getByText(/Override saved: growth_spend disabled/).waitFor()
      await scroll(page, 300, 3)
    },
  },
  {
    chapter: 'Chapter 5 - Platform admin', title: 'The server enforces it',
    narration: 'Back as Sanjay, the Growth Spend menu item has disappeared. Opening its address directly shows that the page is not available. And a direct call to the interface returns forbidden with a consistent, non sensitive message. Hiding a button is not security; the server checks the subscription on every protected request.',
    actions: 'Sign in as Sanjay; try /growth; call /growth/spend directly.', expected: 'Not available; HTTP 403 ENTITLEMENT_DENIED.',
    run: async (page) => {
      await signOut(page)
      await signInTyped(page, 'sanjay.kulkarni')
      await page.goto(origin + '/growth')
      await page.getByText('Not available').waitFor()
      const t = await apiProbe(page, 'GET /growth/spend', '/api/v1/growth/spend')
      if (!t.includes('403') || !t.includes('ENTITLEMENT_DENIED')) throw new Error(t)
    },
  },
  {
    chapter: 'Chapter 5 - Platform admin', title: 'Restore the plan default',
    narration: 'The administrator clears the override, so the customer returns to what their plan includes. Growth Spend works again for Sanjay. Every override, who set it and why, is kept in the audit history.',
    actions: 'Clear the override; confirm Growth Spend is back.', expected: 'Growth Spend page loads.',
    run: async (page) => {
      await signOut(page)
      await signInTyped(page, 'platform.admin')
      await click(page.getByRole('tab', { name: 'Tenant entitlements' }))
      await click(page.getByText('clear', { exact: true }).first())
      await page.waitForTimeout(1200)
      await signOut(page)
      await signInTyped(page, 'sanjay.kulkarni')
      await nav(page, 'Growth Spend')
      await page.getByRole('table', { name: 'Campaign spend' }).waitFor()
    },
  },
  {
    chapter: 'Chapter 6 - Not in the plan', title: 'A personal customer is not entitled',
    narration: 'The personal household plan does not include marketing and sales spend. Rahul s menu has no such item, and the same direct call is refused by the server with the same forbidden answer. Different customers, same product, different entitlements.',
    actions: 'Sign in as Rahul; call /growth/spend directly.', expected: 'HTTP 403 ENTITLEMENT_DENIED.',
    run: async (page) => {
      await signOut(page)
      await signInTyped(page, 'rahul.sharma')
      const t = await apiProbe(page, 'GET /growth/spend as a personal customer', '/api/v1/growth/spend')
      if (!t.includes('403')) throw new Error(t)
    },
  },
  {
    chapter: 'Chapter 7 - Wrap up', title: 'Scope and limits',
    narration: 'To summarise the scope: marketing and sales here means spend visibility, budget variance, and metrics only when real data is imported. It is not a C R M, an ad platform, or a sales pipeline. Live integrations with ad platforms are not part of this release; the C S V import is the agreed boundary. Use Sanjay for the growth report and the import, and the platform admin account for entitlements.',
    actions: 'Sign out.', expected: 'Sign-in page.',
    run: async (page) => { await signOut(page) },
  },
]

await recordVideo({ name: NAME, scenes, password, check: assertNoSecret, fixedTime: '2026-11-02T10:30:00+05:30' })
