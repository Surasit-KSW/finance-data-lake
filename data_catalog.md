# Finance Data Lake — Data Catalog

อัพเดตล่าสุด: 2026-05-31
โครงสร้าง: Medallion Architecture (Bronze → Silver → Gold)

---

## Bronze Layer — `01_Bronze_Raw/` (Raw SAP Exports)

> Read-only — ห้ามแก้ไข ห้าม API อ่านโดยตรง

| Folder | ไฟล์ตัวอย่าง | Period | Source | หมายเหตุ |
|--------|------------|--------|--------|---------|
| `GL_Transactions/` | `sap_fbl3n.XLSX` | 2024–2025 | SAP FBL3N | Replace in-place ทุกเดือน |
| `Sales_Reports/{YYYY}/` | `sale_2025_01.XLSX` | 2023–2025 | SAP VF05/SD | 12 ไฟล์/ปี — add monthly |
| `Production/{YYYY}/` | `1100_2025_01.XLSX` | 2023–2025 | SAP MB52/CO | 24–28 ไฟล์/ปี (plants 1100, 1200, 1300) |
| `AR_Data/` | `AR_2024.XLSX`, `AR_2025.XLSX` | 2024–2025 | SAP FBL5N | Accounts Receivable open items |
| `AP_Data/` | *(ยังว่างอยู่)* | — | SAP FBL1N | รอข้อมูล Accounts Payable |
| `Inventory_RollStock/NRV/` | `AMC_TB_03.2026_v9.XLSX` | 2025–2026 | ZFI_TB | Trial Balance — หลาย version/period |
| `Templates/` | `AMC_Q12026_Leadsheet STAT to client_.xlsx` | — | — | Leadsheet templates + Excel forms |
| `Leadsheet/` | — | — | — | Leadsheet working files |
| `monthend/` | `GA_2200_*.XLSX` | — | SAP KSB1/CO | Month-end CO analysis files |
| `PRD_GI/` | — | — | SAP MB51 | Production GI data (shared กับ 07_Workspace) |
| `Master/` | `KS13_Master.XLSX` | — | SAP KS13 | Cost center master data |
| `Fixed_Assets_PPE/` | *(ยังว่างอยู่)* | — | SAP AR03 | รอข้อมูล Fixed Assets |
| `Deposit/` | — | — | Bank | Bank deposit data |

---

## Silver Layer — `02_Silver_Cleaned/` (Cleaned Parquet)

> Output ของ ETL scripts — ไม่ commit ใน git (regenerate ได้จาก Bronze)

### master_sales_1000.parquet (per-company file, company AMC = 1000)
**DuckDB view:** `v_sales`
**ETL:** `04_Data_Pipelines/silver_transform/etl_sales.py`

| Column | Type | หมายเหตุ |
|--------|------|---------|
| Source_File | string | ชื่อไฟล์ต้นทาง (audit trail) |
| Year | int | ปี (เพิ่มโดย ETL) |
| Month | int | เดือน 1–12 (เพิ่มโดย ETL) |
| *columns จาก SAP VF05* | varies | billing doc, material, qty, net value, customer |

---

### master_production_1000.parquet (per-company file, company AMC = 1000)
**DuckDB view:** `v_production`
**ETL:** `04_Data_Pipelines/silver_transform/etl_production.py`

| Column | Type | หมายเหตุ |
|--------|------|---------|
| Source_File | string | ชื่อไฟล์ต้นทาง (Plant_Year_Month) |
| Year | int | ปี |
| Month | int | เดือน |
| Plant | string | 1100, 1200, 1300 |
| *columns จาก SAP MB52/CO* | varies | material group, qty_kg, cost allocation |

**Plants:** 1100 + 1200 (2023–2025), 1300 (2025)

---

### master_gl_1000.parquet (per-company file, company AMC = 1000)
**DuckDB view:** `v_gl`
**ETL:** `04_Data_Pipelines/silver_transform/etl_gl.py`

| Column | Type | หมายเหตุ |
|--------|------|---------|
| Source_File | string | ชื่อไฟล์ต้นทาง |
| *columns จาก SAP FBL3N* | varies | gl_account, posting_date, amount, doc_no, cost_center |

---

### master_ar_1000.parquet ⚠️ ยังไม่มีไฟล์
**DuckDB view:** `v_ar` *(สร้างได้เมื่อรัน etl_ar.py)*
**ETL:** `04_Data_Pipelines/silver_transform/etl_ar.py`
**Status:** ต้องรัน `python orchestrator.py --layer silver --domain ar` ก่อน

| Column | Type | หมายเหตุ |
|--------|------|---------|
| Source_File | string | ชื่อไฟล์ต้นทาง |
| *columns จาก SAP FBL5N* | varies | customer, invoice_date, due_date, open_amount, aging_bucket |

---

### master_mb51_2025.parquet, master_mb51_2026.parquet
**DuckDB view:** `v_mb51` (wildcard `master_mb51_*.parquet`)
**ETL:** standalone ETL (MB51 material cost orders)

| Column | Type | หมายเหตุ |
|--------|------|---------|
| Source_File | string | ชื่อไฟล์ต้นทาง |
| Year | int | ปี |
| *columns จาก SAP MB51* | varies | material, movement type, quantity, cost |

---

### master_prd_2026.parquet
**DuckDB view:** `v_prd` (wildcard `master_prd_*.parquet`)
**ETL:** standalone ETL (production daily log)

| Column | Type | หมายเหตุ |
|--------|------|---------|
| Source_File | string | ชื่อไฟล์ต้นทาง |
| Year | int | ปี |
| *columns จาก PRD GI* | varies | plant, material, quantity, date |

---

### ไฟล์อื่นๆ ใน Silver Layer (output จาก 06_Scripts)

| ไฟล์ | คำอธิบาย | สร้างโดย |
|------|---------|---------|
| `AR_Sales_Analytics_2023_2025.xlsx` | AR & Sales analytics หลายปี (DSO, growth) | `audit_ar_sales.py` |
| `Production_Summary_Plant_MatGroup.xlsx` | Production summary by plant & material group | `audit_production_yoy.py` |
| `reconciled_tax_with_groups.xlsx` | AP tax reconciliation (3 sheets: All/Outstanding/Matched) | `reconcile_tax.py` |
| `archive/` | Timestamped Excel outputs เก่า (เก็บไว้ reference) | — |

---

## Gold Layer — `03_Gold_DataMarts/` (Business-Ready)

> Output ของ aggregation scripts — ไม่ commit ใน git

### Summary_GL_24_25.parquet
**DuckDB view:** `v_gl_summary`
**ETL:** `04_Data_Pipelines/gold_aggregation/create_gold_summary.py`

| Column | Type | หมายเหตุ |
|--------|------|---------|
| GL_Group | string | หมวดหมู่บัญชี (ต้นทุน, รายได้, ฯลฯ) |
| G/L Account | string | รหัส GL account |
| GL_Name | string | ชื่อบัญชี |
| Period | int | เดือน 1–12 |
| Year | int | ปี |
| Net_Amount | float | ยอดสุทธิ |

---

### gold_leadsheet.parquet
**ETL:** `04_Data_Pipelines/gold_aggregation/create_leadsheet.py`
**รัน:** `python -m 04_Data_Pipelines.gold_aggregation.create_leadsheet --year 2025 --quarter Q1`

| Column | Type | หมายเหตุ |
|--------|------|---------|
| year, quarter, period_end | int/str/date | ช่วงเวลา |
| entity_type | string | `stat` = งบเดี่ยว, `conso` = งบรวม |
| section, section_label_th/en, section_order | string/int | หมวด BS/PL |
| line_key, line_label_th/en, line_order | string/int | บรรทัด |
| gl_account, account_name | string | รหัส + ชื่อ GL |
| amount_raw | float | ยอดก่อนปรับ |
| amount_presented | float | ยอดหลังปรับ (นำเสนอในงบ) |
| currency | string | THB |

---

### gold_cashflow.parquet
**ETL:** `04_Data_Pipelines/gold_aggregation/create_cashflow.py`
**Dependency:** ต้องรัน `create_leadsheet.py` ก่อน
**รัน:** `python -m 04_Data_Pipelines.gold_aggregation.create_cashflow --year 2025 --quarter Q1`

| Column | Type | หมายเหตุ |
|--------|------|---------|
| year, quarter, period_end | int/str/date | ช่วงเวลา |
| entity_type | string | stat / conso |
| section, section_label_th/en, section_order | string/int | Operating / Investing / Financing |
| line_key, line_label_th/en, line_order | string/int | รายการ |
| amount | float | ยอด THB |
| currency | string | THB |

**Logic:** Indirect method — Net Income → บวกกลับ non-cash → Working Capital changes → Investing/Financing

---

### gold_ppe.parquet
**ETL:** `04_Data_Pipelines/gold_aggregation/create_ppe_schedule.py`
**รัน:** `python -m 04_Data_Pipelines.gold_aggregation.create_ppe_schedule --year 2025 --quarter Q1`

| Column | Type | หมายเหตุ |
|--------|------|---------|
| year, quarter, period_end | int/str/date | ช่วงเวลา |
| entity_type | string | stat / conso |
| asset_class, class_label_th/en, class_order | string/int | ประเภทสินทรัพย์ |
| movement_type | string | cost / accum_dep / net_book_value |
| movement_label | string | Opening / Additions / Disposals / Depreciation / Closing |
| amount | float | ยอด THB |
| currency | string | THB |

**Note:** ถ้ายังไม่มี `master_ppe.parquet` (ETL จาก SAP AR02) จะ fallback อ่านจาก `v_gl` แทน

---

### gold_elimination.parquet
**ETL:** `04_Data_Pipelines/gold_aggregation/create_elimination.py`
**Dependency:** ต้องรัน `create_leadsheet.py` ก่อน
**รัน:** `python -m 04_Data_Pipelines.gold_aggregation.create_elimination --year 2025 --quarter Q1`

| Column | Type | หมายเหตุ |
|--------|------|---------|
| year, quarter, period_end | int/str/date | ช่วงเวลา |
| elim_type, elim_label_th/en, elim_order | string/int | ประเภท elimination |
| account, account_name | string | รหัส + ชื่อ GL |
| dr_amount, cr_amount, net_amount | float | ยอด Dr/Cr/สุทธิ |
| note | string | หมายเหตุ |
| currency | string | THB |

**Note:** ปัจจุบัน parent-only IC — รอข้อมูล subsidiary GL เพื่อทำ full consolidation

---

### gold_related_party.parquet
**ETL:** `04_Data_Pipelines/gold_aggregation/create_related_party.py`
**รัน:** `python -m 04_Data_Pipelines.gold_aggregation.create_related_party --year 2025 --quarter Q1`

| Column | Type | หมายเหตุ |
|--------|------|---------|
| year, quarter, period_end | int/str/date | ช่วงเวลา |
| category_key, category_label_th/en | string | หมวดหมู่ related party |
| account, account_name | string | รหัส + ชื่อ GL |
| amount | float | ยอด THB |
| currency | string | THB |
| data_type | string | `transaction` หรือ `balance` |

---

### ไฟล์อื่นๆ ใน Gold Layer (Excel outputs)

| ไฟล์ | คำอธิบาย | สร้างโดย |
|------|---------|---------|
| `Leadsheet_YE2025_STAT.xlsx` | Year-end 2025 leadsheet (งบเดี่ยว) | `06_Scripts/leadsheet/build_q1_2026_leadsheet.py` |
| `Audit_Sales_Summary_23_24_25.xlsx` | Sales audit ปี 2023–2025 | `audit_sales_summary.py` |
| `Audit_Sales_Analysis_2025_v2.xlsx` | Product mix & customer frequency 2025 | `app_01_sales_analytics.py` |
| `Audit_Sales_Analysis_2025.xlsx` | Sales analysis 2025 (เวอร์ชันก่อนหน้า) | — |
| `v_gl_summary.parquet` | Alias ของ Summary_GL_24_25 (legacy) | — |

---

## DuckDB Views (`finance_lake.duckdb`)

รัน `python run_pipeline.py --init-db` หรือ `python 04_Data_Pipelines/init_duckdb.py` เพื่อสร้าง/อัพเดต

| View | Source Parquet | หมายเหตุ |
|------|--------------|---------|
| `v_gl` | `02_Silver_Cleaned/master_gl_1000.parquet` | GL transactions (company 1000) |
| `v_gl_summary` | `03_Gold_DataMarts/Summary_GL_24_25.parquet` | GL summary aggregated (Gold) |
| `v_sales` | `02_Silver_Cleaned/master_sales_1000.parquet` | Sales (company 1000) |
| `v_production` | `02_Silver_Cleaned/master_production_1000.parquet` | Production (company 1000) |
| `v_ar` | `02_Silver_Cleaned/master_ar_1000.parquet` | ⚠️ ข้าม — ไฟล์ยังไม่มี |
| `v_mb51` | `02_Silver_Cleaned/master_mb51_*.parquet` | MB51 material cost orders (standalone ETL) |
| `v_prd` | `02_Silver_Cleaned/master_prd_*.parquet` | Production daily log (standalone ETL) |
| `gold_leadsheet` | `03_Gold_DataMarts/gold_leadsheet.parquet` | Audit leadsheet P&L+BS |
| `gold_cashflow` | `03_Gold_DataMarts/gold_cashflow.parquet` | Cash flow (indirect method) |
| `gold_ppe` | `03_Gold_DataMarts/gold_ppe.parquet` | PPE roll-forward schedule |
| `gold_elimination` | `03_Gold_DataMarts/gold_elimination.parquet` | Consolidation elimination entries |
| `gold_related_party` | `03_Gold_DataMarts/gold_related_party.parquet` | Related party transactions |

---

## Script Directory

### `04_Data_Pipelines/silver_transform/` — Bronze → Silver ETL

| Script | Source | Output |
|--------|--------|--------|
| `etl_gl.py` | `01_Bronze_Raw/GL_Transactions/*.XLSX` | `master_gl_1000.parquet` |
| `etl_sales.py --year YYYY` | `01_Bronze_Raw/Sales_Reports/YYYY/*.XLSX` | `master_sales_1000.parquet` |
| `etl_production.py --year YYYY` | `01_Bronze_Raw/Production/YYYY/*.XLSX` | `master_production_1000.parquet` |
| `etl_ar.py` | `01_Bronze_Raw/AR_Data/*.XLSX` | `master_ar_1000.parquet` *(ยังไม่รัน)* |

### `04_Data_Pipelines/gold_aggregation/` — Silver → Gold

| Script | Dependency | Output |
|--------|-----------|--------|
| `create_gold_summary.py` | `v_gl` | `Summary_GL_24_25.parquet` |
| `create_leadsheet.py` | TB Excel files + GL mapping | `gold_leadsheet.parquet` |
| `create_cashflow.py` | `gold_leadsheet.parquet` | `gold_cashflow.parquet` |
| `create_ppe_schedule.py` | `v_gl` (หรือ `master_ppe.parquet`) | `gold_ppe.parquet` |
| `create_elimination.py` | `gold_leadsheet.parquet` + `v_gl` | `gold_elimination.parquet` |
| `create_related_party.py` | `v_gl` + GL mapping | `gold_related_party.parquet` |

---

### `06_Scripts/audit/` — Ad-hoc Analysis

| Script | วัตถุประสงค์ |
|--------|------------|
| `audit_ar_sales.py` | AR & Sales by customer (DSO, growth rate) |
| `audit_ar_turnover.py` | AR turnover ratio analysis |
| `audit_analyze_AR.py` | AR aging & customer deep-dive |
| `audit_sales_yoy.py` | Sales YoY comparison |
| `audit_sales_summary.py` | Monthly sales pivot (related vs general) |
| `audit_production_yoy.py` | Production YoY (2023–2025) |
| `audit_revenue_drop.py` | Revenue anomaly detection |
| `audit_inventory_flow.py` | Inventory movement analysis |
| `audit_shipping_analysis.py` | Shipping cost analysis |
| `audit_shipping_zone_analysis.py` | Shipping by zone |
| `audit_gl_transport.py` | GL transport account audit |
| `credit_note_analysis.py` | Credit note analysis |
| `map_clearing_data.py` | Clearing document mapping |

### `06_Scripts/reporting/` — Report Generation

| Script | วัตถุประสงค์ |
|--------|------------|
| `production_cost_report.py` | Production cost (DM, conversion, unit cost) → 4-sheet Excel |
| `reconcile_tax.py` | AP tax reconciliation (5-step matching) → 3-sheet Excel |
| `nrv_price_methodology_2026_q1.py` | NRV price methodology Q1 2026 |
| `nrv_rm_calc_explained_2026_q1.py` | NRV RM calculation explained Q1 2026 |
| `nrv_rm_pipe_analysis_2026_q1.py` | NRV RM pipe analysis Q1 2026 |
| `nrv_sku_analysis.py` | NRV SKU analysis |
| `production_cost_nrv_reference.py` | Production cost NRV reference |
| `production_variance_allocation_2026_q1.py` | Production variance allocation Q1 2026 |
| `app_01_sales_analytics.py` | Sales analytics (product mix, customer frequency) |
| `analytics.py` | Basic sales analytics pivot tables |
| `merge_sales_file.py` | Utility: merge multiple sales files |

### `06_Scripts/leadsheet/` — Quarterly Leadsheet Builder

| Script | วัตถุประสงค์ |
|--------|------------|
| `build_q1_2026_leadsheet.py` | สร้าง Q1 2026 leadsheet + schedules |
| `extract_tb_data.py` | Extract Trial Balance data จาก Excel |
| `update_formulas.py` | Update Excel formulas ใน leadsheet |

### `06_Scripts/utils/` — Shared Utilities

| Module | วัตถุประสงค์ |
|--------|------------|
| `lake_client.py` | HTTP client สำหรับ consumer projects ที่เรียก API |
| `lake_config.py` | อ่าน `08_Config/data_paths.yaml` → path objects |
| `excel_utils.py` | Excel formatting (header, currency, auto-fit, total row) |
| `parquet_utils.py` | Parquet I/O + DuckDB query helper |
| `date_utils.py` | Month names (TH/EN), fiscal periods, timestamps |

---

## Quick Reference

```bash
# Full pipeline refresh (Silver + Gold GL Summary + DuckDB)
python orchestrator.py --all
# (run_pipeline.py --all also works — forwards to orchestrator automatically)

# Full pipeline + all Gold Parquets
python orchestrator.py --all --include-gold

# ETL ทีละ domain
python orchestrator.py --layer silver --domain gl
python orchestrator.py --layer silver --domain sales --year 2025
python orchestrator.py --layer silver --domain production --year 2025
python orchestrator.py --layer silver --domain ar

# Gold aggregation (GL Summary only)
python orchestrator.py --layer gold

# DuckDB views เท่านั้น
python orchestrator.py --init-db

# Gold Parquets (รันแยก — หรือใช้ --include-gold ข้างบน)
python -m 04_Data_Pipelines.gold_aggregation.create_leadsheet --year 2025 --quarter Q1
python -m 04_Data_Pipelines.gold_aggregation.create_cashflow --year 2025 --quarter Q1
python -m 04_Data_Pipelines.gold_aggregation.create_ppe_schedule --year 2025 --quarter Q1
python -m 04_Data_Pipelines.gold_aggregation.create_elimination --year 2025 --quarter Q1
python -m 04_Data_Pipelines.gold_aggregation.create_related_party --year 2025 --quarter Q1

# เปิด API
uvicorn backend.main:app --reload --port 8000
```

---

## Known Issues / TODO

| Issue | Priority |
|---|---|
| `master_ar_1000.parquet` ยังไม่ได้รัน ETL — `v_ar` ใน DuckDB จะ skip | Medium |
| `cost_closing.py` อ่าน CSV จาก `sap_cost_closing_app/` โดยตรง (ยังไม่มี ETL) | Low |
| `master_ppe.parquet` ยังไม่มี (etl_ppe.py ยังไม่ได้สร้าง) — gold_ppe ใช้ GL fallback | Medium |
