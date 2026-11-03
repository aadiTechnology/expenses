# Deploying Aadi SpendOS staging on Coolify

Target: **staging with demo data**, UI at `https://expenses.aaditechnology.com`, API at `https://expensesapi.aaditechnology.com`, invite-only sign-up, SMTP email. Repository: `https://github.com/aadiTechnology/expenses`.

What was verified locally (Docker, fresh PostgreSQL 16): the image builds; production mode refuses to start without a 32+ character secret; migrations run on start; demo data loads in demo mode and never in production; the health check passes; CORS allows only the UI origin; a browser served from one address talks to the API on another with no errors; 49 automated tests pass. **Since then (2 Nov 2026):** deployed to Coolify with `python deploy/coolify_deploy.py`; HTTPS certificates issued; all 17 demo logins pass against the live site; a real invitation email sent through Brevo SMTP was received.

## 1. DNS (at your DNS provider)

Create two records pointing to your Coolify server's public IP:

| Name | Type | Value |
|---|---|---|
| `expenses.aaditechnology.com` | A | `<Coolify server IP>` |
| `expensesapi.aaditechnology.com` | A | `<Coolify server IP>` |

## 2. Create the resource in Coolify

1. **Project -> New Resource -> Docker Compose** (private repository via your GitHub App, or public repository).
2. Repository `aadiTechnology/expenses`, branch `main`, compose file location **`/docker-compose.coolify-staging.yml`**.
3. Open the `app` service and set **Domains** to both addresses, comma separated, on port 8000:
   `https://expenses.aaditechnology.com:8000,https://expensesapi.aaditechnology.com:8000`
4. **Environment variables** (Coolify generates `SERVICE_PASSWORD_*` itself). Add these under Environment Variables:

| Variable | Value |
|---|---|
| `SPENDOS_SMTP_HOST` | your SMTP server host |
| `SPENDOS_SMTP_PORT` | `587` (STARTTLS) or `465` (SSL) |
| `SPENDOS_SMTP_SECURITY` | `starttls` (587), `ssl` (465) or `none` |
| `SPENDOS_SMTP_USER` | SMTP username |
| `SPENDOS_SMTP_PASSWORD` | SMTP password (mark as secret) |
| `SPENDOS_SMTP_FROM` | e.g. `Aadi SpendOS <no-reply@aaditechnology.com>` |

   The defaults already in the file: `SPENDOS_ENV=demo`, `SPENDOS_SEED_DEMO=true`, `SPENDOS_ALLOW_REGISTRATION=false`, `SPENDOS_CORS` and `SPENDOS_PUBLIC_URL` = the UI address, and the web app is built to call `https://expensesapi.aaditechnology.com`.
5. **Deploy.** First start creates the tables and loads the demo data.

## 3. Check

* `https://expensesapi.aaditechnology.com/api/health` -> `{"status":"ok"}`
* `https://expenses.aaditechnology.com` -> sign-in page (no "Create an account" link). Logins: `docs/demo/DEMO_ACCESS.md`.
* Sign in as `platform.admin@spendos.demo.test`, open **Organizations -> Create organization**, invite a real person: they receive an email with a link to choose a password (if SMTP is not set up yet, the screen shows the link to send manually).
* Try "Forgot password" for a real mailbox to confirm email delivery.

## Staging cautions

* **A demo-mode server shows its demo logins and shared password on the sign-in page, so anyone who can open the URL can sign in.** Put Coolify's basic authentication in front of the resource (Resource -> Basic Auth) or restrict by IP until you are ready to share it.
* Demo mode also returns password-reset codes in the response for the demo accounts. Do not store real data in this staging database.
* Before going to production: use `docker-compose.coolify.yml` (production mode, empty database), then create the first administrator in the `app` terminal:
  `SPENDOS_ADMIN_PASSWORD='<12+ characters>' python -m app.create_admin you@aaditechnology.com "Your Name"`

## Known gaps

* Receipts live on a Docker volume (no S3); enable backups for both volumes (`spendos_pgdata`, `spendos_files`) in Coolify.
* No error monitoring, no multi-user load test, AI is rule-based (no OCR/LLM provider), no native mobile app.
