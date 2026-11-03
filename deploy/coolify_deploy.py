"""Create or update the SpendOS staging resource in Coolify through its API, then deploy it. Idempotent.
Reads ../.env (never printed). Usage:  python deploy/coolify_deploy.py [--no-deploy]
Needs: COOLIFY_URL, COOLIFY_API_TOKEN, and a server/project/GitHub App (picked automatically when there is exactly one choice)."""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
env = {}
for line in ENV_FILE.read_text(encoding="utf8").splitlines():
    if line.strip() and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

BASE = env["COOLIFY_URL"].rstrip("/") + "/api/v1"
NAME = "spendos-staging"
REPO, BRANCH = "aadiTechnology/expenses", "main"
COMPOSE = "/docker-compose.coolify-staging.yml"
UI, API = env.get("SPENDOS_UI_URL", "https://expenses.aaditechnology.com"), env.get("SPENDOS_API_URL", "https://expensesapi.aaditechnology.com")


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + env["COOLIFY_API_TOKEN"], "Accept": "application/json", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            t = r.read().decode()
            return r.status, (json.loads(t) if t[:1] in "{[" else t)
    except urllib.error.HTTPError as e:
        t = e.read().decode()
        try:
            return e.code, json.loads(t)
        except ValueError:
            return e.code, t[:400]


def pick(label, items, configured):
    if configured:
        return configured
    if len(items) == 1:
        return items[0]["uuid"]
    raise SystemExit(f"Set {label} in .env. Choices: " + ", ".join(f"{i['name']}={i['uuid']}" for i in items))


def main(deploy=True):
    st, servers = call("GET", "/servers")
    server = pick("COOLIFY_SERVER_UUID", servers, env.get("COOLIFY_SERVER_UUID"))
    st, projects = call("GET", "/projects")
    project = pick("COOLIFY_PROJECT_UUID", projects, env.get("COOLIFY_PROJECT_UUID"))
    st, apps = call("GET", "/applications")
    existing = next((a for a in apps if a.get("name", "").startswith(NAME)), None)
    domains = [{"name": "app", "domain": f"{UI},{API}"}]
    if existing:
        uuid = existing["uuid"]
        print("Updating existing resource", NAME)
        st, r = call("PATCH", f"/applications/{uuid}", {"docker_compose_domains": domains, "git_branch": BRANCH, "docker_compose_location": COMPOSE})
        print("  update:", st)
    else:
        st, ghs = call("GET", "/github-apps")
        ghs = [g for g in ghs if g["name"] != "Public GitHub"] or ghs
        gh = env.get("COOLIFY_GITHUB_APP_UUID") or (ghs[0]["uuid"] if len(ghs) == 1 else None)
        if not gh:
            raise SystemExit("Set COOLIFY_GITHUB_APP_UUID in .env. Choices: " + ", ".join(f"{g['name']}={g['uuid']}" for g in ghs))
        st, r = call("POST", "/applications/private-github-app", {
            "project_uuid": project, "server_uuid": server, "environment_name": env.get("COOLIFY_ENVIRONMENT_NAME", "production"), "github_app_uuid": gh,
            "git_repository": REPO, "git_branch": BRANCH, "build_pack": "dockercompose", "ports_exposes": "8000", "base_directory": "/",
            "docker_compose_location": COMPOSE, "name": NAME, "docker_compose_domains": domains, "instant_deploy": False})
        print("  create:", st, "" if st < 300 else r)
        if st >= 300:
            raise SystemExit(1)
        uuid = r["uuid"]
    smtp = {k: env.get(k, "") for k in ("SPENDOS_SMTP_HOST", "SPENDOS_SMTP_PORT", "SPENDOS_SMTP_SECURITY", "SPENDOS_SMTP_USER", "SPENDOS_SMTP_PASSWORD", "SPENDOS_SMTP_FROM")}
    values = {**{k: v for k, v in smtp.items() if v}, "SPENDOS_API_URL": API, "SPENDOS_PUBLIC_URL": UI, "SPENDOS_CORS": UI}
    data = [{"key": k, "value": v, "is_preview": False, "is_buildtime": k == "SPENDOS_API_URL", "is_runtime": True} for k, v in values.items()]
    st, r = call("PATCH", f"/applications/{uuid}/envs/bulk", {"data": data})
    print("  environment variables:", st, "" if st < 300 else r)
    print("  resource uuid:", uuid)
    if not deploy:
        return
    st, r = call("POST", f"/deploy?uuid={uuid}&force=true")
    print("  deploy requested:", st, r if st >= 300 else "")
    dep = (r.get("deployments") or [{}])[0].get("deployment_uuid") if isinstance(r, dict) else None
    for _ in range(50):
        time.sleep(10)
        st, d = call("GET", f"/deployments/{dep}") if dep else (0, {})
        status = d.get("status") if isinstance(d, dict) else None
        print("  status:", status, flush=True)
        if status in ("finished", "failed", "cancelled", "error"):
            break
    st, a = call("GET", f"/applications/{uuid}")
    print("  application status:", a.get("status") if isinstance(a, dict) else a)


if __name__ == "__main__":
    main(deploy="--no-deploy" not in sys.argv)
