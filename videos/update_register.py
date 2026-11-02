"""Create/update the single canonical register docs/SPENDOS_SPRINT_VIDEO_REFERENCE.xlsx from the supplied template.
Existing sheets are kept; the SAMPLE row is replaced by real rows; a Roles & Access sheet is added.
Durations come from ffprobe; links are checked to exist on disk. Run: python -I update_register.py"""
import shutil
import subprocess
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent / "docs"
TEMPLATE = DOCS / "Aadi_SpendOS_Sprint_Video_Reference_Register (1).xlsx"
OUT = DOCS / "SPENDOS_SPRINT_VIDEO_REFERENCE.xlsx"
shutil.copy(TEMPLATE, OUT)  # rebuilt from the template on every run (idempotent)
wb = load_workbook(OUT)

PERSONAS = {
    "rahul.sharma": ("Owner (Personal)", "Rahul Sharma - Household (SAMPLE DATA)"),
    "sunita.sharma": ("Family Viewer (read-only)", "Rahul Sharma - Household (SAMPLE DATA)"),
    "arjun.mehta": ("Employee", "Aadi Technology (ILLUSTRATIVE DEMO)"),
    "sneha.iyer": ("Project Manager", "Aadi Technology (ILLUSTRATIVE DEMO)"),
    "rohit.patil": ("Project Manager (other projects)", "Aadi Technology (ILLUSTRATIVE DEMO)"),
    "sanjay.kulkarni": ("Finance Manager", "Aadi Technology (ILLUSTRATIVE DEMO)"),
    "anita.deshmukh": ("Organization Admin", "Aadi Technology (ILLUSTRATIVE DEMO)"),
    "vikram.joshi": ("Department Manager", "Aadi Technology (ILLUSTRATIVE DEMO)"),
    "platform.admin": ("Platform Admin", "(platform - no tenant data)"),
}
S1 = ("S1-MVP", "MVP build: personal and business editions, approvals, three pillars (PRD v1.1 M1-M8)", "2026-11-02")
S2 = ("S2-GAPS", "Gap closure: lockout, reminders and summaries, family allocation, data export and deletion, languages, performance and accessibility", "2026-11-02")
VIDEOS = [
    dict(sprint=S1, part="1 of 4", file="01-spendos-personal-edition", title="SpendOS - Personal edition: replace the household notebook",
         cap="Personal edition: sign-in with demo panel, dashboard, transactions search/detail, validated expense entry, duplicate detection, accounts and transfers, budgets, AI voice capture with mandatory confirmation and low-confidence handling, insights (fact/estimate/advisory), permission-aware questions, reports, read-only family viewer.",
         journeys="Sign in; read dashboard; search and open a transaction; add expense (validation then success); duplicate warning; transfer between accounts; budgets; AI capture and confirm; insights; ask a question; reports; family viewer denied add.",
         cov="Web (responsive)", ctx="Personal: Rahul Sharma household, Oct 2026", roles=["rahul.sharma", "sunita.sharma"]),
    dict(sprint=S1, part="2 of 4", file="02-spendos-business-edition", title="SpendOS - Business edition: expense, approval, reimbursement and budgets (Aadi Technology)",
         cap="Business edition: employee claim with project validation, policy-driven approval chain, wrong-project approver blocked, rejection reason required, finance verify and pay, reimbursements, budget vs actual, business dashboard, admin project budget, project reports, policies and audit, department-scoped manager, permission-aware AI, direct API 403/404 proof.",
         journeys="Employee submits travel expense; other PM cannot see it; right PM rejects (reason required) and approves; finance verifies and pays; budgets and dashboard; admin creates project budget; project report; policies and audit log; department manager scoped report; AI question allowed vs denied; direct API probes.",
         cov="Web (responsive)", ctx="Business: Aadi Technology illustrative demo, Oct-Nov 2026", roles=["arjun.mehta", "sneha.iyer", "rohit.patil", "sanjay.kulkarni", "anita.deshmukh", "vikram.joshi"]),
    dict(sprint=S1, part="3 of 4", file="03-spendos-growth-spend-and-entitlements", title="SpendOS - Marketing & sales spend, data import and tenant entitlements",
         cap="Pillar 2: campaign spend vs budget with reconciling totals, metrics only when data exists (unavailable otherwise), atomic CSV import with provenance and row errors, campaign tags on expenses. Platform: module catalogue with pillars, per-tenant entitlement override, dependency effect, server-side denial (403 ENTITLEMENT_DENIED), unentitled personal tenant.",
         journeys="Open Growth Spend; read unavailable vs estimated metrics; import bad file (rejected) then good file; tag an expense with campaign and channel; platform admin disables growth_spend for Aadi; finance sees it gone and API denies; override cleared; personal tenant denied.",
         cov="Web (responsive)", ctx="Business: Aadi Technology; Personal: Rahul (for denial)", roles=["sanjay.kulkarni", "platform.admin", "rahul.sharma"]),
    dict(sprint=S1, part="4 of 4", file="04-spendos-on-your-phone", title="SpendOS - the responsive web app on a phone-sized screen",
         cap="Responsive layout at 390x844 with touch emulation: single-column dashboard, drawer menu, quick expense entry. Native mobile app is NOT part of this sprint.",
         journeys="Sign in on phone viewport; scroll dashboard; open menu drawer; add expense; list.",
         cov="Web on phone viewport only (no native app)", ctx="Personal: Rahul Sharma household", roles=["rahul.sharma"]),
    dict(sprint=S2, part="1 of 1", file="05-spendos-sprint-2-gap-closure", title="SpendOS Sprint 2 - lockout, reminders, family allocation, privacy and languages",
         cap="Sign-in lockout after five failures; recurring payments with deduplicated reminders and monthly summary; family allocation of shared expenses (must reconcile) with contributions report; personal data download; account deletion with demo protection; Hindi/Marathi navigation (draft); measured performance (25,000 transactions) and automated accessibility scan results.",
         journeys="Lockout on a throwaway account; reminders and summary in notifications; add recurring payment; split a shared expense (mismatch refused, then saved); contributions report; download data; delete a throwaway account; switch language; business recurring payments.",
         cov="Web (responsive)", ctx="Personal: Rahul Sharma household; Business: Aadi Technology; throwaway accounts created and deleted on screen", roles=["rahul.sharma", "sanjay.kulkarni"]),
]


def duration(path: Path) -> str:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()
    s = int(float(out))
    return f"{s // 60}:{s % 60:02d}"


ws = wb["Sprint Video Register"]
if ws.max_row >= 2 and str(ws.cell(2, 3).value).startswith("SAMPLE"):
    ws.delete_rows(2, 1)
headers = [c.value for c in ws[1]]
common = dict(Product="SpendOS", **{"Release / Version": "v1.1.0 (MVP)"})
rows = []
for v in VIDEOS:
    mp4 = HERE / f"{v['file']}.mp4"
    assert mp4.exists(), mp4
    for u in v["roles"]:
        role, tenant = PERSONAS[u]
        sid, stitle, sdate = v["sprint"]
        rows.append({**common, "Sprint ID": sid, "Sprint Title": stitle, "Completion Date": sdate, "Video Part": v["part"], "Video Title": v["title"], "Video URL / Storage Path": f"ExpenseTracking/videos/{v['file']}.mp4 (captions: .srt/.vtt)",
                     "Duration": duration(mp4), "Delivered Capability Summary": v["cap"], "User Journeys Demonstrated": v["journeys"], "Platform Coverage (Web/Mobile/Both)": v["cov"],
                     "Environment Name": "Local demo (non-production), PostgreSQL 16 in Docker", "Environment URL": "http://localhost:8000", "Tenant / Organization Context": tenant,
                     "Role / Persona": role, "Demo Username": f"{u}@spendos.demo.test",
                     "Credential Location / Access Method": "docs/demo/DEMO_ACCESS.md (disposable demo-only password); sign-in page 'Show demo accounts' > Use",
                     "Credential Expiry / Rotation Note": "Demo-only. Change DEMO_PASSWORD in backend/app/seed.py and run `python -m app.seed --reset` after the review period.",
                     "Seed Data Notes": "Deterministic synthetic seed (python -m app.seed --reset); all records labelled sample/illustrative; Aadi figures are not real accounts.",
                     "Known Limitations": "No native mobile app; AI is a rules engine (no OCR/LLM provider); in-app notifications only; Redis/S3 not used; automated accessibility scan only (no manual audit); Hindi/Marathi are draft translations of menus and titles; videos recorded with browser date pinned to Oct/Nov 2026.",
                     "Test / Validation Status": "Backend 41/41 tests on PostgreSQL; frontend build OK; all demo logins verified in browser", "Reviewer": "Pending", "Review Date": "Pending",
                     "Documentation Status": "Awaiting review"})
for r in rows:
    ws.append([r.get(h, "") for h in headers])
for row in ws.iter_rows(min_row=2):
    for c in row:
        c.alignment = Alignment(wrap_text=True, vertical="top")
for col, w in zip("ABCDEFGHIJKLMNOPQRSTUVWXY", [10, 12, 11, 30, 12, 9, 34, 38, 9, 50, 50, 18, 26, 24, 28, 22, 34, 38, 38, 34, 38, 30, 10, 10, 16]):
    ws.column_dimensions[col].width = w
ws.freeze_panes = "A2"
ws.auto_filter.ref = ws.dimensions
ws.data_validations.dataValidation = []
dv = DataValidation(type="list", formula1='"Web,Mobile,Both,Web (responsive),Web on phone viewport only (no native app)"', allow_blank=True)
dv2 = DataValidation(type="list", formula1='"Pending,Awaiting review,Reviewed,Documentation complete"', allow_blank=False)
ws.add_data_validation(dv); ws.add_data_validation(dv2)
dv.add(f"L2:L{ws.max_row}"); dv2.add(f"Y2:Y{ws.max_row}")

# Sprint Summary
ss = wb["Sprint Summary"]
if ss.max_row >= 2 and str(ss.cell(2, 1).value).startswith("SAMPLE"):
    ss.delete_rows(2, 1)
ss.append(["S1-MVP", "MVP build (PRD v1.1 M1-M8)", "Implementation complete with gaps closed in S2 or listed in docs/SPRINT_REPORT.md", "Yes (tests on PostgreSQL; build OK)", "Yes (4 parts)",
           "Verified on disk; not yet reviewed by a person", "Yes - all personas signed in through the browser", "Yes", "No - pending Product Owner review",
           "Native mobile app, OCR/LLM provider, Redis/S3; reviewer sign-off", "Awaiting review"])
ss.append(["S2-GAPS", "Gap closure (lockout, reminders, family allocation, privacy, languages, performance, accessibility)", "Implementation complete", "Yes (41 backend tests on PostgreSQL; build OK; axe scan clean)", "Yes (1 part)",
           "Verified on disk; not yet reviewed by a person", "Yes - all personas signed in through the browser", "Yes", "No - pending Product Owner review",
           "Native mobile app, OCR/LLM provider, Redis/S3, live ad integrations, native-speaker review of translations, manual accessibility audit; reviewer sign-off", "Awaiting review"])
for row in ss.iter_rows(min_row=2):
    for c in row:
        c.alignment = Alignment(wrap_text=True, vertical="top")
for col, w in zip("ABCDEFGHIJK", [12, 30, 36, 30, 14, 26, 30, 14, 26, 50, 18]):
    ss.column_dimensions[col].width = w
ss.freeze_panes = "A2"

# Roles & Access (one persona per row, linked by Sprint ID)
if "Roles & Access" in wb.sheetnames:
    del wb["Roles & Access"]
ra = wb.create_sheet("Roles & Access")
ra.append(["Sprint ID", "Tenant / Organization", "Role / Persona", "Demo Username", "Access method", "Least-privilege scope", "Used in video part(s)"])
scope = {"rahul.sharma": "Full access to own household only", "sunita.sharma": "Read-only, shared items", "arjun.mehta": "Own expenses only", "sneha.iyer": "Approve for RITeSchool, Preschool ERP, Internship Program",
         "rohit.patil": "Approve for Multitenant CRM, AI Product Factory", "sanjay.kulkarni": "Whole organization: finance, growth spend", "anita.deshmukh": "Whole organization: administration",
         "vikram.joshi": "Software Development department only", "platform.admin": "Catalogue and entitlements, no tenant financial data"}
used = {}
for v in VIDEOS:
    for u in v["roles"]:
        used.setdefault(u, []).append(("V" + v["file"][:2]))
extra = ["neha.kapoor", "kiran.shah", "meera.nair", "divya.rao", "sameer.patil", "ravi.menon", "priya.sharma", "aarav.sharma"]
for u, parts in used.items():
    ra.append(["S1-MVP, S2-GAPS", PERSONAS[u][1], PERSONAS[u][0], f"{u}@spendos.demo.test", "docs/demo/DEMO_ACCESS.md", scope[u], ", ".join(parts)])
for u in extra:
    ra.append(["S1-MVP, S2-GAPS", "see DEMO_ACCESS.md", "additional persona", f"{u}@spendos.demo.test", "docs/demo/DEMO_ACCESS.md", "see DEMO_ACCESS.md", "browse only"])
for c in ra[1]:
    c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="3949AB")
for col, w in zip("ABCDEFG", [11, 36, 30, 40, 28, 52, 18]):
    ra.column_dimensions[col].width = w
ra.freeze_panes = "A2"; ra.auto_filter.ref = ra.dimensions

# Read Me additions
rm = wb["Read Me"]
existing = [str(r[0].value) for r in rm.iter_rows(min_row=1)]
for k, v in [("Where the videos are", "ExpenseTracking/videos/*.mp4 with .srt/.vtt captions. Open with any video player."), ("Demo app", "Run ExpenseTracking/start_demo.bat then open http://localhost:8000; logins in docs/demo/DEMO_ACCESS.md.")]:
    if k not in existing:
        rm.append([k, v])
wb.save(OUT)
print("saved", OUT, len(rows), "register rows")
