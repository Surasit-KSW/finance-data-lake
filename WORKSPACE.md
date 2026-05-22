# Workspace Organization Reference

`D:\_Work_Workspace\03_Data_Projects\` — current directory structure.

> Last updated: 2026-05-22 (reorganization complete)
> The 6 pinned directories at the top must never move.

---

## Pinned — Do NOT Move (hardcoded paths)

```
03_Data_Projects/
├── _Finance_Data_Lake/       PINNED — Vercel git remote + absolute path in data_paths.yaml
├── _Finance-Vault/           PINNED — Vault knowledge base
├── audit-reconcile/          PINNED — ../audit-reconcile referenced in data_paths.yaml
├── sap_cost_closing_app/     PINNED — ../sap_cost_closing_app referenced in cost_closing.py
├── main-dashboard/           PINNED — ../main-dashboard referenced in data_paths.yaml
└── fin-dashboard/            PINNED — ../fin-dashboard referenced in data_paths.yaml
```

---

## Current Structure

```
03_Data_Projects/
│
│   ── Pinned (must stay here) ──────────────────────────────────────────
├── _Finance_Data_Lake/        Central data hub + REST API (this project)
├── _Finance-Vault/            Knowledge base + AI memory
├── audit-reconcile/           Python audit/reconcile CLI
├── sap_cost_closing_app/      Streamlit SAP cost closing
├── main-dashboard/            Next.js central dashboard
├── fin-dashboard/             Next.js financial dashboard
│
│   ── Active Financial Projects ─────────────────────────────────────────
├── active/
│   ├── executive-financial-dashboard/
│   ├── amc-dashboard/
│   └── project-gi-dashboard/
│
│   ── AI / Automation Projects ──────────────────────────────────────────
├── ai/
│   ├── accounting-agent/       Monthly accounting automation (OCR→Payroll→E-filing)
│   │   └── docs/               accounting-agent-spec.md (moved from root)
│   ├── ai-marketing-team/
│   ├── content_planner/        AI content planner for Facebook/IG
│   ├── fb-agent-content/       Facebook content pipeline (LangGraph/Gemini)
│   ├── gi-simulation-app/      GI steel simulation (React/Vite)
│   └── ocr-accounting-project/ OCR for invoices/receipts
│
│   ── Tools and Personal Utilities ──────────────────────────────────────
├── tools/
│   ├── merge-pdf/
│   ├── payroll-to-sap/
│   ├── personal-task-assistant/
│   ├── pre-check-cost-center/
│   └── text-pdf-extractor/
│
│   ── Archived / Inactive Projects ──────────────────────────────────────
├── archive/
│   ├── ___JournalX/
│   ├── __Allgen_project_/
│   ├── _Agent_team_project/
│   ├── _ai-sales-bot/
│   ├── _Base_line_project/
│   ├── _bod-financial-dashboard/
│   ├── _content-automation/
│   ├── _Finance_Automation_Project/   merged into audit-reconcile
│   ├── _Finance_workspace/            merged into _Finance_Data_Lake/07_Workspace/
│   ├── _fintech-command-center/       superseded by Finance Data Lake
│   ├── _Project_Management/
│   ├── _web-app/
│   ├── _WebSite_Project/
│   ├── ar-aging/                      superseded by /api/v1/audit/ar-aging
│   ├── backup/
│   ├── personal_SAM/
│   └── sap-year-closing/
│
│   ── External Binaries and Assets ──────────────────────────────────────
└── vendor/
    ├── Fastwork_Images/
    ├── node/                   Node.js runtime — could not move (process lock)
    └── poppler-25.12.0/        PDF processing library
```

---

## Pending Cleanup (process lock — ลบหลัง restart/ปิด VS Code)

```
_web app/                       → ลบทิ้ง (copy อยู่ใน archive/_web-app/ แล้ว)
Executive Financial Dashboard/  → ลบทิ้ง (copy อยู่ใน active/executive-financial-dashboard/ แล้ว)
node/                           → ย้ายไป vendor/ (Node.js runtime — ติด process lock)
```

---

## Before Moving Any Directory

Run this to check if it's referenced anywhere in `_Finance_Data_Lake`:

```bash
grep -r "DIRNAME" D:/_Work_Workspace/03_Data_Projects/_Finance_Data_Lake --include="*.py" --include="*.yaml" --include="*.json" --include="*.env" --include="*.ts"
```

Also check if the target project has a git remote set (moving breaks remote tracking):

```bash
cd "D:/_Work_Workspace/03_Data_Projects/TARGET_DIR" && git remote -v
```

If it has a remote, push all branches before moving.
