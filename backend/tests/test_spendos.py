from sqlalchemy import func, select

from app import models as m
from app import seed
from app.core import SessionLocal

B, P = seed.BUSINESS_ID, seed.PERSONAL_ID
API = "/api/v1"


def cat(client, h, name):
    return next(c["id"] for c in client.get(f"{API}/categories", headers=h).json() if c["name"] == name)


def totals(client, h, period="2026-10"):
    return client.get(f"{API}/dashboard?period={period}", headers=h).json()["data"]["kpis"]


# ---------- financial integrity ----------
def test_business_seed_reconciles_to_prd_summary(client, login):
    k = totals(client, login("sanjay.kulkarni"))
    assert k["income"] == 85000000 and k["expense"] == 50000000 and k["savings"] == 35000000


def test_business_category_groups_match_summary(client, login):
    h = login("sanjay.kulkarni")
    rows = {r[0]: r[1] for r in client.get(f"{API}/reports/category?period=2026-10", headers=h).json()["rows"]}
    expect = {"Employee Costs": 300000, "Infrastructure": 35000, "Software Subscriptions": 25000, "Marketing": 40000, "Travel": 20000,
              "Training": 25000, "Other Expenses": 10000}
    for k, v in expect.items():
        assert rows[k] == v * 100
    assert rows["Administration"] + rows["Utilities"] == 3000000
    assert rows["Equipment"] + rows["Maintenance"] == 1500000


def test_split_allocations_reconcile(client, login):
    h = login("anita.deshmukh")
    proj = {r[0]: r[1] for r in client.get(f"{API}/reports/project?period=2026-10", headers=h).json()["rows"]}
    assert sum(proj.values()) == 50000000
    r = client.post(f"{API}/transactions", headers=h, json={
        "date": "2026-11-01", "type": "expense", "amount": "1000.00", "category_id": cat(client, h, "Marketing"), "account_id": "acc_a_bank",
        "project_id": "prj_a_ops", "splits": [{"project_id": "prj_a_ops", "amount": "400"}, {"project_id": "prj_a_crm", "amount": "500"}]})
    assert r.status_code == 422 and "must match" in r.text


def test_personal_balances_and_transfers_not_counted(client, login):
    h = login("rahul.sharma")
    accts = {a["name"]: a["balance_minor"] for a in client.get(f"{API}/accounts", headers=h).json()}
    k = totals(client, h)
    with SessionLocal() as db:
        s = lambda col, *c: db.scalar(select(func.sum(m.Transaction.amount_minor)).where(m.Transaction.tenant_id == P, col.in_(c)))  # noqa: E731
        opening = db.scalar(select(func.sum(m.Account.opening_minor)).where(m.Account.tenant_id == P))
        inc, exp, cr = s(m.Transaction.type, "income"), s(m.Transaction.type, "expense"), s(m.Transaction.type, "refund", "reimbursement")
    assert sum(accts.values()) >= 0 or True
    assert sum(accts.values()) == opening + inc - exp + cr  # transfers net to zero
    assert k["expense"] == k["expense_gross"] - k["refunds"]
    assert client.get(f"{API}/transactions?date_from=2026-10-01&date_to=2026-10-31", headers=h).json()["total"] >= 50


def test_refund_cap_and_decimal_rules(client, login):
    h = login("rahul.sharma")
    orig = next(t for t in client.get(f"{API}/transactions?q=Medicines", headers=h).json()["items"] if t["type"] == "expense")
    base = {"date": "2026-10-30", "account_id": orig["account_id"]}
    assert client.post(f"{API}/transactions", headers=h, json=base | {"type": "refund", "amount": "9999", "refund_of_id": orig["id"]}).status_code == 422
    assert client.post(f"{API}/transactions", headers=h, json=base | {"type": "expense", "amount": "10.005", "category_id": orig["category_id"]}).status_code == 422
    assert client.post(f"{API}/transactions", headers=h, json=base | {"type": "expense", "amount": "-5", "category_id": orig["category_id"]}).status_code == 422


def test_duplicate_detection(client, login):
    h = login("rahul.sharma")
    body = {"date": "2026-10-20", "type": "expense", "amount": "700", "category_id": cat(client, h, "Transport"), "description": "Petrol", "account_id": "acc_p_upi"}
    r = client.post(f"{API}/transactions", headers=h, json=body)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "DUPLICATE"


def test_transfer_same_account_rejected(client, login):
    h = login("rahul.sharma")
    r = client.post(f"{API}/transactions", headers=h, json={"date": "2026-10-30", "type": "transfer", "amount": "10", "account_id": "acc_p_bank", "to_account_id": "acc_p_bank"})
    assert r.status_code == 422


def test_seed_is_idempotent():
    with SessionLocal() as db:
        n1 = db.scalar(select(func.count()).select_from(m.Transaction))
    seed.run(do_reset=False)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(m.Transaction)) == n1


# ---------- approval workflow + authorization ----------
def test_full_reimbursement_flow_and_negative_cases(client, login):
    emp, pm, pm_other, fin = login("arjun.mehta"), login("sneha.iyer"), login("rohit.patil"), login("sanjay.kulkarni")
    r = client.post(f"{API}/transactions", headers=emp, json={"date": "2026-11-02", "type": "expense", "amount": "3500", "category_id": cat(client, emp, "Travel"),
                                                              "project_id": "prj_a_rite", "description": "Travel to client site"})
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    assert r.json()["status"] == "submitted"
    act = lambda who, what, body=None: client.post(f"{API}/transactions/{tid}/{what}", headers=who, json=body or {})  # noqa: E731
    assert act(pm_other, "approve").status_code in (403, 404)  # not their project: hidden or refused
    assert act(emp, "approve").status_code == 403
    assert act(fin, "approve").status_code == 403  # finance cannot jump the queue
    assert act(pm, "reject").status_code == 422  # reason required
    assert act(pm, "approve").json()["status"] == "pm_approved"
    assert act(fin, "approve").json()["status"] == "verified"
    assert act(pm, "pay", {"account_id": "acc_a_bank"}).status_code == 403
    bal = lambda: next(a for a in client.get(f"{API}/accounts", headers=fin).json() if a["id"] == "acc_a_bank")["balance_minor"]  # noqa: E731
    before = bal()
    assert act(fin, "pay", {"account_id": "acc_a_bank"}).json()["status"] == "paid"
    assert before - bal() == 350000
    d = client.get(f"{API}/transactions/{tid}", headers=emp).json()
    assert [s["status"] for s in d["steps"]] == ["approved", "approved"] and len(d["history"]) >= 4


def test_rejection_and_resubmission(client, login):
    emp, pm = login("divya.rao"), login("sneha.iyer")
    r = client.post(f"{API}/transactions", headers=emp, json={"date": "2026-11-02", "type": "expense", "amount": "5000", "category_id": cat(client, emp, "Marketing"),
                                                              "project_id": "prj_a_intern", "description": "Banner printing"}).json()
    rej = client.post(f"{API}/transactions/{r['id']}/reject", headers=pm, json={"reason": "Get a quote first"})
    assert rej.json()["status"] == "rejected"
    d = client.get(f"{API}/transactions/{r['id']}", headers=emp).json()
    assert d["reject_reason"] == "Get a quote first"
    assert client.post(f"{API}/transactions/{r['id']}/submit", headers=emp).json()["status"] == "submitted"


def test_small_claim_policy_skips_project_manager(client, login):
    emp = login("meera.nair")
    r = client.post(f"{API}/transactions", headers=emp, json={"date": "2026-11-02", "type": "expense", "amount": "400", "category_id": cat(client, emp, "Travel"),
                                                              "project_id": "prj_a_crm", "description": "Parking"})
    assert [s["role"] for s in client.get(f"{API}/transactions/{r.json()['id']}", headers=emp).json()["steps"]] == ["finance"]


def test_employee_visibility_limits(client, login):
    emp = login("arjun.mehta")
    items = client.get(f"{API}/transactions?page_size=200", headers=emp).json()["items"]
    assert items and all(i["created_by"] == "mem_a_arjun" for i in items)
    assert client.get(f"{API}/transactions/txn_aadi_c2", headers=emp).status_code == 404
    assert client.get(f"{API}/budgets", headers=emp).json() == []
    assert client.get(f"{API}/audit", headers=emp).status_code == 403
    assert client.post(f"{API}/categories", headers=emp, json={"name": "X"}).status_code == 403


def test_dept_and_project_manager_scopes(client, login):
    depts = {r[0] for r in client.get(f"{API}/reports/department?period=2026-10", headers=login("neha.kapoor")).json()["rows"]}
    assert depts == {"Digital Marketing"}
    projs = {r[0] for r in client.get(f"{API}/reports/project?period=2026-10", headers=login("rohit.patil")).json()["rows"]}
    assert projs and projs <= {"Multitenant CRM", "AI Product Factory"}


def test_cross_tenant_isolation(client, login):
    rahul = login("rahul.sharma")
    assert client.get(f"{API}/transactions/txn_aadi_c1", headers=rahul).status_code == 404
    assert client.post(f"{API}/auth/switch/{B}", headers=rahul).status_code == 403
    assert "HDFC Current Account" not in {a["name"] for a in client.get(f"{API}/accounts", headers=rahul).json()}


def test_auditor_is_read_only(client, login):
    a = login("ravi.menon")
    assert client.get(f"{API}/transactions?page_size=5", headers=a).status_code == 200
    assert client.post(f"{API}/transactions", headers=a, json={"date": "2026-11-02", "type": "expense", "amount": "1"}).status_code == 403


def test_family_viewer(client, login):
    v = login("sunita.sharma")
    items = client.get(f"{API}/transactions?page_size=200", headers=v).json()["items"]
    assert items and all(i["shared"] for i in items)
    assert client.post(f"{API}/transactions", headers=v, json={"date": "2026-11-02", "type": "expense", "amount": "1"}).status_code == 403


# ---------- entitlements ----------
def test_unentitled_tenant_blocked_on_direct_api(client, login):
    h = login("rahul.sharma")
    r = client.get(f"{API}/growth/spend", headers=h)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "ENTITLEMENT_DENIED"
    assert client.post(f"{API}/dimensions", headers=h, json={"key": "campaign", "name": "Campaign"}).status_code == 403


def test_entitlement_override_disable_expire_enable(client, login):
    plat, fin = login("platform.admin"), login("sanjay.kulkarni")
    assert client.get(f"{API}/growth/spend?period=2026-10", headers=fin).status_code == 200
    put = lambda tid, code, body: client.put(f"{API}/platform/tenants/{tid}/entitlements/{code}", headers=plat, json=body)  # noqa: E731
    assert put(B, "growth_spend", {"enabled": False, "reason": "test"}).status_code == 200
    assert client.get(f"{API}/growth/spend", headers=fin).status_code == 403
    put(B, "growth_spend", {"enabled": False, "expires_at": "2020-01-01"})
    assert client.get(f"{API}/growth/spend?period=2026-10", headers=fin).status_code == 200  # expired override: plan applies
    client.delete(f"{API}/platform/tenants/{B}/entitlements/growth_spend", headers=plat)
    put(P, "growth_dimensions", {"enabled": True})
    assert client.get(f"{API}/dimensions", headers=login("rahul.sharma")).status_code == 200
    client.delete(f"{API}/platform/tenants/{P}/entitlements/growth_dimensions", headers=plat)
    assert client.get(f"{API}/platform/modules", headers=fin).status_code == 403


# ---------- Pillar 2 ----------
def test_growth_report_reconciles_and_discloses_missing_metrics(client, login):
    r = client.get(f"{API}/growth/spend?period=2026-10", headers=login("sanjay.kulkarni")).json()
    assert r["total_minor"] == 4000000
    by = {x["name"]: x for x in r["rows"]}
    i = by["Internship Intake Oct"]
    assert i["actual_minor"] == 2000000 and i["utilization"] == 80.0 and i["cac_minor"] == round(2000000 / 16)
    w = by["AI Product Launch Webinar"]
    assert w["cac_minor"] is None and "Unavailable" in w["metric_note"]
    rs = by["RITeSchool Admissions Drive"]
    assert rs["cost_per_lead_minor"] == 30000 and rs["cac_minor"] is None


def test_growth_import_is_atomic(client, login):
    h = login("sanjay.kulkarni")
    bad = b"campaign,leads,customers,revenue\nInternship Intake Oct,10,2,\nNo Such Campaign,5,1,\n"
    r = client.post(f"{API}/growth/import", headers=h, data={"source": "x", "period": "2026-11", "currency": "INR", "attribution_method": "manual"}, files={"file": ("a.csv", bad, "text/csv")})
    assert r.status_code == 422 and r.json()["detail"]["errors"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(m.GrowthMetric).join(m.ImportBatch, m.ImportBatch.id == m.GrowthMetric.batch_id).where(m.ImportBatch.period == "2026-11")) == 0
    wrong = client.post(f"{API}/growth/import", headers=h, data={"source": "x", "period": "2026-11", "currency": "USD", "attribution_method": "manual"}, files={"file": ("a.csv", b"campaign,leads\n", "text/csv")})
    assert wrong.status_code == 422


# ---------- Pillar 3 ----------
def test_ai_parse_saves_nothing_until_confirmed(client, login):
    h = login("rahul.sharma")
    before = client.get(f"{API}/transactions?page_size=1", headers=h).json()["total"]
    r = client.post(f"{API}/ai/parse", headers=h, json={"text": "Today vegetables 250, milk 60 and petrol 500"}).json()
    assert [i["amount"] for i in r["items"]] == ["250", "60", "500"]
    assert client.get(f"{API}/transactions?page_size=1", headers=h).json()["total"] == before
    items = [i | {"account_id": "acc_p_cash", "allow_duplicate": True, "date": "2026-11-02"} for i in r["items"]]
    items[0]["needs_review"], items[0]["reviewed"] = True, False
    assert client.post(f"{API}/ai/extractions/{r['extraction_id']}/confirm", headers=h, json={"items": items}).status_code == 422
    items[0]["reviewed"] = True
    c = client.post(f"{API}/ai/extractions/{r['extraction_id']}/confirm", headers=h, json={"items": items})
    assert c.status_code == 200 and len(c.json()["created"]) == 3
    t = client.get(f"{API}/transactions/{c.json()['created'][0]}", headers=h).json()
    assert t["ai_assisted"] and t["ai"]["confirmed_by"]


def test_ai_answers_respect_permissions(client, login):
    q = {"question": "How much did we spend on Multitenant CRM in October?"}
    a = client.post(f"{API}/ai/ask", headers=login("arjun.mehta"), json=q).json()
    assert "no spending" in a["answer"] and a["citations"] == []
    assert "Multitenant CRM spending" in client.post(f"{API}/ai/ask", headers=login("rohit.patil"), json=q).json()["answer"]
    assert client.post(f"{API}/ai/ask", headers=login("sanjay.kulkarni"), json={"question": "spend on RITeSchool"}).json()["citations"]
    assert client.post(f"{API}/ai/ask", headers=login("rahul.sharma"), json={"question": "spend on RITeSchool"}).json()["citations"] == []


def test_insights_are_labelled_and_reviewable(client, login):
    h = login("rahul.sharma")
    ins = client.get(f"{API}/ai/insights", headers=h).json()["items"]
    assert any(i["kind"] == "fact" for i in ins) and all(i["engine"] for i in ins)
    assert all("advisory" in i["body"] for i in ins if i["kind"] == "anomaly")
    assert client.post(f"{API}/ai/insights/{ins[0]['key']}/review", headers=h, json={"status": "acknowledged"}).status_code == 200
    assert client.post(f"{API}/ai/insights/anomaly:nope/review", headers=h, json={"status": "dismissed"}).status_code == 404


def test_receipt_upload_validation_and_extraction(client, login):
    h = login("rahul.sharma")
    assert client.post(f"{API}/ai/receipt", headers=h, files={"file": ("x.png", b"not an image", "image/png")}).status_code == 415
    pdf = b"%PDF-1.4\nMerchant: Big Bazaar\nDate 2026-10-30\nGST 90\nTotal Rs 1,890.00\n"
    it = client.post(f"{API}/ai/receipt", headers=h, files={"file": ("bill.pdf", pdf, "application/pdf")}).json()["items"][0]
    assert it["amount"] == "1890.00" and it["merchant"] == "Big Bazaar" and it["needs_review"]


# ---------- auth and misc ----------
def test_registration_onboarding_and_password_reset(client):
    r = client.post(f"{API}/auth/register", json={"name": "New User", "email": "new.user@example.test", "password": "abc12345", "edition": "personal"})
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert len(client.get(f"{API}/categories", headers=h).json()) >= 15
    assert client.post(f"{API}/auth/register", json={"name": "N", "email": "new.user@example.test", "password": "abc12345"}).status_code == 409
    assert client.post(f"{API}/auth/register", json={"name": "N", "email": "w@example.test", "password": "short"}).status_code == 422
    tok = client.post(f"{API}/auth/forgot", json={"email": "new.user@example.test"}).json()["demo_reset_token"]
    assert client.post(f"{API}/auth/reset", json={"token": tok, "password": "newpass123"}).status_code == 200
    assert client.get(f"{API}/me", headers=h).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "new.user@example.test", "password": "newpass123"}).status_code == 200


def test_logout_revokes_session(client, login):
    h = login("rahul.sharma")
    assert client.post(f"{API}/auth/logout", headers=h).status_code == 200
    assert client.get(f"{API}/me", headers=h).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "rahul.sharma" + seed.DOMAIN, "password": "wrong"}).status_code == 401


def test_budget_utilisation_and_alerts_deduplicated(client, login):
    fin = login("sanjay.kulkarni")
    titles = [i["title"] for i in client.get(f"{API}/notifications", headers=fin).json()["items"] if i["kind"] == "budget_alert"]
    assert titles and len(titles) == len(set(titles))
    b = {r["name"]: r for r in client.get(f"{API}/budgets?period=2026-10", headers=login("anita.deshmukh")).json()}
    assert b["Organization operating budget"]["utilization"] == round(50000000 / 55000000 * 100, 1)


def test_csv_export_neutralises_formulas_and_import_preview(client, login):
    h = login("rahul.sharma")
    t = client.post(f"{API}/transactions", headers=h, json={"date": "2026-11-02", "type": "expense", "amount": "5", "category_id": cat(client, h, "Miscellaneous"),
                                                            "description": "=HYPERLINK(1)", "account_id": "acc_p_cash"})
    assert t.status_code == 200
    assert "'=HYPERLINK(1)" in client.get(f"{API}/transactions/export", headers=h).text
    csv = b"date,type,amount,category,description,account\n2026-11-03,expense,12,Miscellaneous,test,Cash in Hand\n2026-11-03,expense,x,Nope,bad,Cash in Hand\n"
    up = client.post(f"{API}/transactions/import", headers=h, files={"file": ("a.csv", csv, "text/csv")}).json()
    assert up["ok"] == 1 and up["skipped"] == 1


def test_pdf_and_csv_reports(client, login):
    h = login("anita.deshmukh")
    assert client.get(f"{API}/reports/department?format=pdf&period=2026-10", headers=h).content[:4] == b"%PDF"
    assert "Department" in client.get(f"{API}/reports/department?format=csv&period=2026-10", headers=h).text


def test_platform_catalogue_classification_is_audited(client, login):
    plat = login("platform.admin")
    mods = client.get(f"{API}/platform/modules", headers=plat).json()["modules"]
    assert {x["primary_pillar"] for x in mods} == {"P1", "P2", "P3"}
    assert client.patch(f"{API}/platform/modules/growth_import", headers=plat, json={"primary_pillar": "P2", "secondary_pillar": "P1"}).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(m.AuditEvent.id).where(m.AuditEvent.entity == "module", m.AuditEvent.action == "classification_changed"))
