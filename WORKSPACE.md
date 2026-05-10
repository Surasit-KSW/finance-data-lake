# Workspace Organization Reference

`D:\_Work_Workspace\03_Data_Projects\` — target directory structure.

> This document defines the **target structure**. Actual file moves must be done manually
> and verified one directory at a time. The 5 pinned directories at the top must never move.

---

## Pinned — Do NOT Move (hardcoded paths)

```
03_Data_Projects/
├── _Finance_Data_Lake/       PINNED — Vercel git remote + absolute path in data_paths.yaml
├── audit-reconcile/          PINNED — ../audit-reconcile referenced in data_paths.yaml
├── sap_cost_closing_app/     PINNED — ../sap_cost_closing_app referenced in cost_closing.py
├── main-dashboard/           PINNED — ../main-dashboard referenced in data_paths.yaml
└── fin-dashboard/            PINNED — ../fin-dashboard referenced in data_paths.yaml
```

---

## Target Structure (after reorganization)

```
03_Data_Projects/
│
│   ── Pinned (must stay here) ──────────────────────────────────────────
├── _Finance_Data_Lake/        Central data hub (this project)
├── audit-reconcile/           Python audit/reconcile CLI
├── sap_cost_closing_app/      Streamlit SAP cost closing
├── main-dashboard/            Next.js central dashboard
├── fin-dashboard/             Next.js financial dashboard
│
│   ── Active Financial Projects ─────────────────────────────────────────
├── active/
│   ├── executive-financial-dashboard/   (from: "Executive Financial Dashboard")
│   ├── amc-dashboard/
│   └── project-gi-dashboard/            (from: Project_GI_Dashboard)
│
│   ── AI / Automation Projects ──────────────────────────────────────────
├── ai/
│   ├── fb-agent-content/           Facebook content pipeline (LangGraph/Gemini)
│   ├── ai-marketing-team/          Marketing agents
│   ├── ocr-accounting-project/     OCR for invoices/receipts
│   └── gi-simulation-app/          GI steel simulation (React/Vite)
│
│   ── Tools and Personal Utilities ──────────────────────────────────────
├── tools/
│   ├── personal-task-assistant/    (from: "Personal Task Assistant")
│   ├── payroll-to-sap/             (from: Project_Payroll_to_SAP)
│   ├── merge-pdf/                  (from: merge_pdf)
│   ├── text-pdf-extractor/         (from: "Text-based PDF Extractor")
│   └── pre-check-cost-center/      (from: "pre check cost center")
│
│   ── Archived / Inactive Projects ──────────────────────────────────────
├── archive/
│   ├── _fintech-command-center/    abandoned — superseded by Finance Data Lake
│   ├── _bod-financial-dashboard/   incomplete
│   ├── _content-automation/        incomplete
│   ├── _ai-sales-bot/              incomplete
│   ├── _Finance_Automation_Project/ merged into audit-reconcile
│   ├── ___JournalX/                abandoned
│   ├── __Allgen_project_/          abandoned
│   ├── _Base_line_project/         abandoned template
│   ├── _Agent_team_project/        abandoned
│   ├── _Project_Management/        abandoned
│   ├── _WebSite_Project/           abandoned
│   ├── _web_app/                   abandoned
│   ├── AR_Aging/                   (from: "AR Aging") — superseded by AR endpoint
│   ├── personal_SAM/               inactive
│   └── backup/                     redundant copy of _fintech-command-center
│
│   ── External Binaries and Assets ──────────────────────────────────────
└── vendor/
    ├── poppler-25.12.0/            PDF processing library
    ├── node/                       Node.js runtime
    └── Fastwork_Images/            Freelance project assets
```

---

## Safe Migration Order

### Phase 0 — Zero risk (do first)
Move to `archive/`:
- `___JournalX/`, `__Allgen_project_/`, `_Base_line_project/`, `_Agent_team_project/`, `_Project_Management/`, `_WebSite_Project/`, `backup/`

Move to `vendor/`:
- `poppler-25.12.0/`, `node/`, `Fastwork_Images/`

### Phase 1 — Archive incomplete projects
Move to `archive/`:
- `_fintech-command-center/`, `_bod-financial-dashboard/`, `_content-automation/`, `_ai-sales-bot/`, `_Finance_Automation_Project/`

Rename with spaces → kebab-case, then move to `archive/`:
- `"AR Aging"` → `ar-aging/`
- `"_web app"` → `_web-app/`

### Phase 2 — Group active AI projects
Move to `ai/`:
- `fb-agent-content/`, `ai-marketing-team/`, `ocr-accounting-project/`, `gi-simulation-app/`

### Phase 3 — Group active financial projects
Rename then move to `active/`:
- `"Executive Financial Dashboard"` → `executive-financial-dashboard/`
- `Project_GI_Dashboard/` → `project-gi-dashboard/`
- `amc-dashboard/`

### Phase 4 — Tools and utilities
Rename + move to `tools/`:
- `"Personal Task Assistant"` → `personal-task-assistant/`
- `"Text-based PDF Extractor"` → `text-pdf-extractor/`
- `"pre check cost center"` → `pre-check-cost-center/`
- `Project_Payroll_to_SAP/` → `payroll-to-sap/`
- `merge_pdf/` → `merge-pdf/`

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

---

## Stray Files to Clean Up

```
03_Data_Projects/fintech.db   ← orphan SQLite database — identify owner before deleting
```
