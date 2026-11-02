"""Deployment features: invite-only onboarding, SMTP email (invitations and reset links), token expiry, production start-up rules."""
import os
import re
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from app import mail
from app import models as m
from app.core import SessionLocal

API = "/api/v1"
BACKEND = Path(__file__).resolve().parent.parent


def token_from(link_or_text: str) -> str:
    return re.search(r"token=([\w-]+)", link_or_text).group(1)


def test_registration_can_be_switched_off(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.ALLOW_REGISTRATION", False)
    assert client.get(f"{API}/auth/config").json()["registration"] is False
    r = client.post(f"{API}/auth/register", json={"name": "X", "email": "closed@example.test", "password": "abc12345", "edition": "personal"})
    assert r.status_code == 403 and "invit" in r.text.lower()


def test_platform_admin_onboards_an_organization_without_mail(client, login):
    plat = login("platform.admin")
    r = client.post(f"{API}/platform/organizations", headers=plat, json={"name": "Invited Co", "edition": "business", "template": "it_company", "admin_name": "New Admin", "admin_email": "new.admin@example.test"})
    assert r.status_code == 200 and r.json()["invite_link"] and not r.json()["invite_emailed"]
    tok = token_from(r.json()["invite_link"])
    # the invited person chooses a password, then signs in as the organization administrator
    assert client.post(f"{API}/auth/reset", json={"token": tok, "password": "chosen-pass-1"}).status_code == 200
    s = client.post(f"{API}/auth/login", json={"email": "new.admin@example.test", "password": "chosen-pass-1"}).json()
    me = client.get(f"{API}/me", headers={"Authorization": f"Bearer {s['token']}"}).json()
    assert me["role"] == "org_admin" and me["tenant"]["name"] == "Invited Co"
    assert client.post(f"{API}/auth/reset", json={"token": tok, "password": "another-pass-1"}).status_code == 400  # a link works once


def test_only_platform_admin_can_create_organizations(client, login):
    r = client.post(f"{API}/platform/organizations", headers=login("anita.deshmukh"), json={"name": "Nope", "edition": "business", "admin_name": "A", "admin_email": "a@example.test"})
    assert r.status_code == 403


def test_invitation_and_reset_emails_are_sent_when_smtp_is_configured(client, login, monkeypatch):
    sent = []
    monkeypatch.setattr(mail, "configured", lambda: True)
    monkeypatch.setattr(mail, "send", lambda to, subject, text: sent.append((to, subject, text)) or True)
    monkeypatch.setenv("SPENDOS_PUBLIC_URL", "https://expenses.aaditechnology.com")
    r = client.post(f"{API}/members", headers=login("anita.deshmukh"), json={"name": "Mail Person", "email": "mail.person@example.test", "role": "employee"})
    assert r.status_code == 200 and r.json()["invite_emailed"] and r.json()["temporary_password"] is None
    to, subject, text = sent[-1]
    assert to == "mail.person@example.test" and "invited" in subject and "https://expenses.aaditechnology.com/reset?token=" in text
    assert client.post(f"{API}/auth/login", json={"email": "mail.person@example.test", "password": "anything-1"}).status_code == 401  # nobody knows a password yet
    assert client.post(f"{API}/auth/reset", json={"token": token_from(text), "password": "my-own-pass-1"}).status_code == 200
    assert client.post(f"{API}/auth/login", json={"email": "mail.person@example.test", "password": "my-own-pass-1"}).status_code == 200
    # forgot password: one email for a real address, none for an unknown one, identical answers
    n = len(sent)
    a = client.post(f"{API}/auth/forgot", json={"email": "mail.person@example.test"}).json()["message"]
    b = client.post(f"{API}/auth/forgot", json={"email": "nobody.here@example.test"}).json()["message"]
    assert a == b and len(sent) == n + 1 and "Reset your" in sent[-1][1]


def test_expired_links_are_refused(client):
    with SessionLocal() as db:
        u = db.query(m.User).filter(m.User.email == "rahul.sharma@spendos.demo.test").one()
        db.add(m.PasswordReset(token="expired-token-test", user_id=u.id, expires_at=m.now() - timedelta(minutes=1)))
        db.commit()
    r = client.post(f"{API}/auth/reset", json={"token": "expired-token-test", "password": "abc12345x"})
    assert r.status_code == 400 and "expired" in r.text


def test_smtp_client_uses_starttls_and_login(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None): calls.append(("connect", host, port))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, context=None): calls.append(("starttls",))
        def login(self, u, p): calls.append(("login", u))
        def send_message(self, msg): calls.append(("send", msg["To"], msg["Subject"]))

    for k, v in {"SPENDOS_SMTP_HOST": "smtp.example.test", "SPENDOS_SMTP_PORT": "587", "SPENDOS_SMTP_USER": "mailer", "SPENDOS_SMTP_PASSWORD": "secret", "SPENDOS_SMTP_FROM": "SpendOS <no-reply@example.test>"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    assert mail.send("to@example.test", "Hello", "Body") is True
    assert [c[0] for c in calls] == ["connect", "starttls", "login", "send"] and calls[1:2] == [("starttls",)]
    # a failing mail server never raises into the request
    monkeypatch.setattr("smtplib.SMTP", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    assert mail.send("to@example.test", "Hello", "Body") is False


def test_production_refuses_to_start_without_a_real_secret():
    env = {**os.environ, "SPENDOS_ENV": "production", "SPENDOS_DB": "postgresql+psycopg://x:y@localhost:1/z", "SPENDOS_SECRET": "short"}
    p = subprocess.run([sys.executable, "-c", "import app.core"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert p.returncode != 0 and "SPENDOS_SECRET" in p.stderr
    env["SPENDOS_SECRET"] = "x" * 40
    assert subprocess.run([sys.executable, "-c", "import app.core"], cwd=BACKEND, env=env, capture_output=True, text=True).returncode == 0


def test_demo_login_list_is_hidden_in_production(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.ENV", "production")
    assert client.get(f"{API}/demo/accounts").status_code == 404
    assert "demo_reset_token" not in client.post(f"{API}/auth/forgot", json={"email": "rahul.sharma@spendos.demo.test"}).json()
