# Finance Data Lake — Data Catalog

อัพเดตล่าสุด: 2026-05-06
โครงสร้าง: Medallion Architecture (Bronze → Silver → Gold)

---

## Bronze Layer — `01_Bronze_Raw/` (Raw SAP Exports)

| Folder | ไฟล์ตัวอย่าง | Period | Source | หมายเหตุ |
|--------|------------|--------|--------|---------|
| `AR_Data/` | AR_2024.XLSX, AR_2025.XLSX | 2024–2025 | SAP FBL5N | Accounts Receivable open items |
| `AP_Data/` | *(ยังว่างอยู่)* | — | SAP FBL1N | รอข้อมูล Accounts Payable |
| `GL_Transactions/` | sap_fbl3n.XLSX | 2024–2025 | SAP FBL3N | General Ledger transactions |
| `Production/2023/` | 1100_2023_01.XLSX | 2023 | SAP MB52/MIGO | Plant 1100, 1200 (72 files) |
| `Production/2024/` | 1100_2024_01.XLSX | 2024 | SAP MB52/MIGO | Plant 1100, 1200 (72 files) |
| `Production/2025/` | 1100_2025_01.XLSX | 2025 | SAP MB52/MIGO | Plant 1100, 1200, **1300** (84 files) |
| `Sales_Reports/2023/` | sale_2023_01.XLSX | 2023 | SAP VF05/SD | Monthly sales billing (12 files) |
| `Sales_Reports/2024/` | sale_2024_01.XLSX | 2024 | SAP VF05/SD | Monthly sales billing (12 files) |
| `Sales_Reports/2025/` | sale_2025_01.XLSX | 2025 | SAP VF05/SD | Monthly sales billing (12 files) |
| `Fixed_Assets_PPE/` | *(ยังว่างอยู่)* | — | SAP AR03 | รอข้อมูล Fixed Assets |
| `Inventory_RollStock/` | *(ยังว่างอยู่)* | — | SAP MB52 | รอข้อมูล Inventory Roll-Forward |

---

## Silver Layer — `02_Silver_Cleaned/` (Cleaned Parquet)

### master_sales_YYYY.parquet (3 files: 2023, 2024, 2025)
**DuckDB view:** `v_sales`, `v_sales_2023`, `v_sales_2024`, `v_sales_2025`
**Source:** ETL → `04_Data_Pipelines/silver_transform/etl_sales.py`

| Column | Type | หมายเหตุ |
|--------|------|---------|
| Source_File | string | ชื่อไฟล์ต้นทาง (audit trail) |
| Year | int | ปี (เพิ่มโดย ETL) |
| Month | int | เดือน 1–12 (เพิ่มโดย ETL) |
| *columns จาก SAP SD* | varies | billing doc, material, qty, net value, customer |

---

### master_production_YYYY.parquet (3 files: 2023, 2024, 2025)
**DuckDB view:** `v_production`, `v_production_2023`, `v_production_2024`, `v_production_2025`
**Source:** ETL → `04_Data_Pipelines/silver_transform/etl_production.py`

| Column | Type | หมายเหตุ |
|--------|------|---------|
| Source_File | string | ชื่อไฟล์ต้นทาง (Plant_Year_Month) |
| *columns จาก SAP* | varies | plant, material group, qty_kg, cost allocation |

**Plants:** 1100, 1200 (2023–2025), 1300 (Jul 2025 เป็นต้นไป)

---

### Master_GL_24_25.parquet (~82 MB)
**DuckDB view:** `v_gl`
**Source:** ETL → `04_Data_Pipelines/silver_transform/etl_gl.py`

| Column | Type | หมายเหตุ |
|--------|------|---------|
| Source_File | string | ชื่อไฟล์ต้นทาง |
| *columns จาก SAP FBL3N* | varies | gl_account, posting_date, amount, doc_no, cost_center |

---

### master_ar.parquet *(สร้างโดย etl_ar.py)*
**DuckDB view:** `v_ar` *(จะมีหลังรัน init_duckdb.py)*
**Source:** ETL → `04_Data_Pipelines/silver_transform/etl_ar.py`

| Column | Type | หมายเหตุ |
|--------|------|---------|
| Source_File | string | ชื่อไฟล์ต้นทาง |
| *columns จาก SAP FBL5N* | varies | customer, invoice_date, due_date, open_amount, aging_bucket |

---

### อื่นๆ ใน Silver Layer

| ไฟล์ | คำอธิบาย |
|------|---------|
| `AR_Sales_Analytics_2023_2025.xlsx` | Multi-year AR & Sales analytics (สร้างโดย audit_ar_sales.py) |
| `Production_Summary_Plant_MatGroup.xlsx` | Production summary by plant & material group |
| `reconciled_tax_with_groups.xlsx` | AP tax reconciliation (3 sheets: All, Outstanding, Matched) |
| `archive/` | Timestamped Excel outputs เก่า (เก็บไว้ reference) |

---

## Gold Layer — `03_Gold_DataMarts/` (Business-Ready)

### Summary_GL_24_25.parquet
**DuckDB view:** `v_gl_summary`
**Source:** `04_Data_Pipelines/gold_aggregation/create_gold_summary.py`

| Column | Type | หมายเหตุ |
|--------|------|---------|
| GL_Group | string | หมวดหมู่บัญชี (เช่น ต้นทุน, รายได้) |
| G/L Account | string | รหัส GL account |
| GL_Name | string | ชื่อบัญชี |
| Period | int | เดือน 1–12 |
| Year | int | ปี |
| Net_Amount | float | ยอดสุทธิ |

**ใช้ใน:** `05_Dashboards/app_01_audit_analytics.py` (YoY Variance & Drill-Down)

---

### อื่นๆ ใน Gold Layer

| ไฟล์ | คำอธิบาย |
|------|---------|
| `Audit_Sales_Summary_23_24_25.xlsx` | Sales audit ปี 2023–2025 (สร้างโดย audit_sales_summary.py) |
| `Audit_Sales_Analysis_2025_v2.xlsx` | Product mix & customer frequency 2025 |
| `Audit_Sales_Analysis_2025.xlsx` | Sales analysis 2025 (เวอร์ชันก่อนหน้า) |

---

## DuckDB Views สรุป

รัน `python 04_Data_Pipelines/init_duckdb.py` เพื่อสร้าง/อัพเดตทุก view

| View | Source Parquet | หมายเหตุ |
|------|--------------|---------|
| `v_sales` | master_sales_*.parquet | ทุกปีรวมกัน |
| `v_sales_2023` | master_sales_2023.parquet | เฉพาะปี 2023 |
| `v_sales_2024` | master_sales_2024.parquet | เฉพาะปี 2024 |
| `v_sales_2025` | master_sales_2025.parquet | เฉพาะปี 2025 |
| `v_production` | master_production_*.parquet | ทุกปีรวมกัน |
| `v_production_2023` | master_production_2023.parquet | เฉพาะปี 2023 |
| `v_production_2024` | master_production_2024.parquet | เฉพาะปี 2024 |
| `v_production_2025` | master_production_2025.parquet | เฉพาะปี 2025 |
| `v_gl` | Master_GL_24_25.parquet | GL transactions 2024–2025 |
| `v_gl_summary` | Summary_GL_24_25.parquet | GL summary (Gold) |

---

## Script Directory — `06_Scripts/`

### audit/ — Ad-hoc analysis scripts
| Script | วัตถุประสงค์ |
|--------|------------|
| `audit_ar_sales.py` | AR & Sales by customer (DSO, growth rate) |
| `audit_ar_turnover.py` | AR turnover ratio analysis |
| `audit_analyze_AR.py` | AR aging & customer analysis |
| `audit_sales_yoy.py` | Sales YoY comparison (2024 vs 2025) |
| `audit_sales_summary.py` | Monthly sales pivot (related vs general) |
| `audit_production_yoy.py` | Production YoY (2023–2025) |
| `audit_revenue_drop.py` | Revenue anomaly detection |
| `audit_inventory_flow.py` | Inventory movement analysis |
| `audit_shipping_analysis.py` | Shipping cost analysis |
| `audit_shipping_zone_analysis.py` | Shipping by zone |
| `audit_gl_transport.py` | GL transport account audit |

### reporting/ — Report generation
| Script | วัตถุประสงค์ |
|--------|------------|
| `production_cost_report.py` | Production cost (DM, conversion, unit cost) → 4-sheet Excel |
| `reconcile_tax.py` | AP tax reconciliation (5-step matching) → 3-sheet Excel |
| `app_01_sales_analytics.py` | Sales analytics notebook (product mix, customer frequency) |
| `analytics.py` | Basic sales analytics pivot tables |
| `merge sale file.py` | Utility: merge multiple sales files |

### utils/ — Shared utilities
| Module | วัตถุประสงค์ |
|--------|------------|
| `excel_utils.py` | Excel formatting (header, currency, auto-fit, total row) |
| `parquet_utils.py` | Parquet I/O + DuckDB query helper |
| `date_utils.py` | Month names (TH/EN), fiscal periods, timestamps |

---

## Quick Start

```bash
# 1. ติดตั้ง dependencies
pip install -r requirements.txt

# 2. สร้าง DuckDB views
python 04_Data_Pipelines/init_duckdb.py

# 3. รัน full pipeline
python run_pipeline.py --all

# 4. เปิด dashboard
python run_pipeline.py --dashboard

# 5. รัน Silver ETL เฉพาะ domain
python run_pipeline.py --layer silver --domain sales --year 2025
```
