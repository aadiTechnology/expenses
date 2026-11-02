"""Sprint S2: lockout, reminders and summaries, recurring payments, family allocations and contributions, data export and account deletion."""
from datetime import date

from sqlalchemy import func, select

from app import models as m
from app.core import SessionLocal

API = "/api/v1"


def register(client, email, edition="personal"):
    r = client.post(f"{API}/auth/register", json={"name": "Temp Person", "email": email, "password": "abc12345", "edition": edition, "organization_name": "Temp Org"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_account_locks_after_five_failures_and_reset_unlocks(client):
    register(client, "lock.me@example.test")
    for _ in range(5):
        assert client.post(f"{API}/auth/login", json={"email": "lock.me@example.test", "password": "wrong-pass1"}).status_code == 401
    r = client.post(f"{API}/auth/login", json={"email": "lock.me@example.test", "password": "abc12345"})
    assert r.status_code == 429  # even the right password is refused while locked
    tok = client.post(f"{API}/auth/forgot", json={"email": "lock.me@example.test"}).json()["demo_reset_token"]
    assert client.post(f"{API}/auth/reset", json={"token": tok, "password": "newpass123"}).status_code == 200
    assert client.post(f"{API}/auth/login", json={"email": "lock.me@example.test", "password": "newpass123"}).status_code == 200


def test_successful_login_resets_failure_counter(client):
    register(client, "counter@example.test")
    for _ in range(4):
        client.post(f"{API}/auth/login", json={"email": "counter@example.test", "password": "nope-nope1"})
    assert client.post(f"{API}/auth/login", json={"email": "counter@example.test", "password": "abc12345"}).status_code == 200
    for _ in range(4):
        client.post(f"{API}/auth/login", json={"email": "counter@example.test", "password": "nope-nope1"})
    assert client.post(f"{API}/auth/login", json={"email": "counter@example.test", "password": "abc12345"}).status_code == 200


def test_recurring_reminders_are_generated_once(client, login):
    h = login("rahul.sharma")
    r1 = client.post(f"{API}/notifications/refresh", headers=h, json={"today": "2026-10-16"}).json()["created"]
    assert r1 >= 1
    assert client.post(f"{API}/notifications/refresh", headers=h, json={"today": "2026-10-16"}).json()["created"] == 0
    titles = [n["title"] for n in client.get(f"{API}/notifications", headers=h).json()["items"]]
    assert any("House rent" in t for t in titles) and not any("Internet bill" in t for t in titles)  # internet (day 11) already passed


def test_monthly_summary_matches_report_and_respects_preferences(client, login):
    h = login("sanjay.kulkarni")
    client.post(f"{API}/notifications/refresh", headers=h, json={"today": "2026-11-02"})
    items = client.get(f"{API}/notifications", headers=h).json()["items"]
    summ = [n for n in items if n["kind"] == "summary" and "2026-10" in n["title"]]
    assert len(summ) == 1 and "850000.00" in summ[0]["body"] and "500000.00" in summ[0]["body"]
    prefs = client.get(f"{API}/notifications", headers=h).json()["preferences"]
    client.put(f"{API}/notifications/preferences", headers=h, json={**prefs, "summary": False})
    assert not [n for n in client.get(f"{API}/notifications", headers=h).json()["items"] if n["kind"] == "summary"]
    client.put(f"{API}/notifications/preferences", headers=h, json=prefs)


def test_business_reminders_for_finance_only(client, login):
    n = client.post(f"{API}/notifications/refresh", headers=login("sanjay.kulkarni"), json={"today": "2026-10-03"}).json()["created"]
    assert n >= 2  # Azure (day 4) and GitHub (day 5)
    emp = login("arjun.mehta")
    assert not [x for x in client.get(f"{API}/notifications", headers=emp).json()["items"] if x["kind"] == "reminder"]
    assert client.post(f"{API}/recurring", headers=emp, json={"description": "x", "amount": "10", "day_of_month": 3}).status_code == 403


def test_recurring_crud_validation(client, login):
    h = login("rahul.sharma")
    assert client.post(f"{API}/recurring", headers=h, json={"description": "Gym", "amount": "1500", "day_of_month": 40}).status_code == 422
    rid = client.post(f"{API}/recurring", headers=h, json={"description": "Gym", "amount": "1500", "day_of_month": 9}).json()["id"]
    assert any(r["id"] == rid for r in client.get(f"{API}/recurring", headers=h).json())
    assert client.delete(f"{API}/recurring/{rid}", headers=h).status_code == 200


def test_family_allocation_must_reconcile_and_feeds_contributions(client, login):
    h = login("rahul.sharma")
    members = {x["name"]: x["id"] for x in client.get(f"{API}/members", headers=h).json()}
    cat = next(c["id"] for c in client.get(f"{API}/categories", headers=h).json() if c["name"] == "Household")
    base = {"date": "2026-10-29", "type": "expense", "amount": "1000", "category_id": cat, "account_id": "acc_p_cash", "shared": True, "description": "Shared pantry order", "allow_duplicate": True}
    bad = client.post(f"{API}/transactions", headers=h, json=base | {"splits": [{"member_id": members["Rahul Sharma"], "amount": "400"}, {"member_id": members["Priya Sharma"], "amount": "500"}]})
    assert bad.status_code == 422 and "must match" in bad.text
    ok = client.post(f"{API}/transactions", headers=h, json=base | {"splits": [{"member_id": members["Rahul Sharma"], "amount": "400"}, {"member_id": members["Priya Sharma"], "amount": "600"}]})
    assert ok.status_code == 200
    d = client.get(f"{API}/transactions/{ok.json()['id']}", headers=h).json()
    assert sorted(s["amount"] for s in d["splits"]) == ["400.00", "600.00"]
    rep = client.get(f"{API}/reports/contributions?period=2026-10", headers=h).json()
    rows = {r[0]: r for r in rep["rows"]}
    assert rows["Rahul Sharma"][1] >= 6500000  # salary recorded by Rahul
    with SessionLocal() as db:
        shared_net = db.scalar(select(func.coalesce(func.sum(m.Transaction.amount_minor), 0)).where(
            m.Transaction.tenant_id == "ten_personal_demo", m.Transaction.type == "expense", m.Transaction.shared.is_(True), m.Transaction.date >= date(2026, 10, 1), m.Transaction.date < date(2026, 11, 1)))
        credit = db.scalar(select(func.coalesce(func.sum(m.Transaction.amount_minor), 0)).where(
            m.Transaction.tenant_id == "ten_personal_demo", m.Transaction.type.in_(("refund", "reimbursement")), m.Transaction.shared.is_(True), m.Transaction.date >= date(2026, 10, 1), m.Transaction.date < date(2026, 11, 1)))
    assert sum(r[2] for r in rep["rows"]) == shared_net - credit  # allocations reconcile to the shared expenses
    client.delete(f"{API}/transactions/{ok.json()['id']}", headers=h)


def test_family_viewer_cannot_see_unshared_allocations(client, login):
    rep = client.get(f"{API}/reports/member?period=2026-10", headers=login("sunita.sharma")).json()
    assert rep["rows"] and all(isinstance(r[1], int) for r in rep["rows"])
    own = client.get(f"{API}/transactions?page_size=200", headers=login("sunita.sharma")).json()["items"]
    assert all(t["shared"] for t in own)


def test_export_contains_only_visible_data(client, login):
    ex = client.get(f"{API}/me/export", headers=login("arjun.mehta")).json()
    assert ex["profile"]["email"].startswith("arjun.mehta") and ex["transactions"]
    assert all(t["created_by"] == "mem_a_arjun" for t in ex["transactions"])


def test_account_deletion_rules(client, login):
    assert client.post(f"{API}/me/delete", headers=login("rahul.sharma"), json={"password": "SpendOS@Demo26"}).status_code == 409  # demo accounts are protected
    h = register(client, "delete.me@example.test")
    client.post(f"{API}/transactions", headers=h, json={"date": "2026-11-02", "type": "income", "amount": "100", "category_id": next(c["id"] for c in client.get(f"{API}/categories", headers=h).json() if c["name"] == "Salary"),
                                                       "account_id": client.get(f"{API}/accounts", headers=h).json()[0]["id"]})
    tenant_id = client.get(f"{API}/me", headers=h).json()["tenant"]["id"]
    assert client.post(f"{API}/me/delete", headers=h, json={"password": "wrong-pass1"}).status_code == 403
    assert client.post(f"{API}/me/delete", headers=h, json={"password": "abc12345"}).status_code == 200
    assert client.get(f"{API}/me", headers=h).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "delete.me@example.test", "password": "abc12345"}).status_code == 401
    with SessionLocal() as db:
        assert db.get(m.Tenant, tenant_id) is None
        assert db.scalar(select(func.count()).select_from(m.Transaction).where(m.Transaction.tenant_id == tenant_id)) == 0


def test_admin_with_team_must_hand_over_before_deleting(client, login):
    h = register(client, "boss@example.test", edition="business")
    r = client.post(f"{API}/members", headers=h, json={"name": "Helper", "email": "helper@example.test", "role": "employee"})
    assert r.status_code == 200
    assert client.post(f"{API}/me/delete", headers=h, json={"password": "abc12345"}).status_code == 409
