# Data Update SOP — Finance Data Lake
> อัพเดทไฟล์นี้ทุกครั้งที่เชื่อมโมดูลใหม่

---

## สถานะปัจจุบัน (2026-06-01)

| โมดูล | Data Source | สถานะ | หมายเหตุ |
|---|---|---|---|
| Financial Performance | v_gl_summary → Neon | ✅ LIVE | 2026 Jan–May |
| Liquidity & Health | v_gl_summary → Neon | ✅ LIVE | 2026 Jan–May |
| Working Capital | v_gl_summary → Neon | ✅ LIVE | 2026 Jan–May |
| Cash Flow | v_gl_summary → Neon | ✅ LIVE | 2026 Jan–May |
| Budget vs Actual | — | ⏳ DEMO | ยังไม่มี budget data |
| FP&A Planning | — | ⏳ MOCK | local only |
| A/F Radar | — | ⏳ MOCK | local only |
| Treasury | — | ⏳ MOCK | local only |
| Monitor Overview | — | ⏳ DEMO | รอ Sales data |
| Cost Ledger | v_gl → Neon | ⏳ DEMO | รอ verify cost center filter |
| P&L Summary | — | ⏳ DEMO | รอ Sales data |

---

## รอบเดือน — GL Update (ทำทุกต้นเดือน วันที่ 1–5)

### Step 1 — Export จาก SAP FBL3N
- T-code: **FBL3N** (All items, open + cleared)
- ครอบคลุมทุกปีที่ต้องการ (2024, 2025, 2026)
- Export เป็น Excel → บันทึกที่:
  ```
  _Finance_Data_Lake/01_Bronze_Raw/GL_Transactions/2026/gl_2026_MM.XLSX
  ```
  (แต่ละเดือนแยกไฟล์ตาม MM)

### Step 2 — รัน Pipeline
```bash
cd D:\_Work_Workspace\03_Data_Projects\_Finance_Data_Lake

# Silver ETL — แปลง Excel → Parquet
python run_pipeline.py --layer silver --domain gl

# Gold ETL — สร้าง GL Summary
python run_pipeline.py --layer gold

# (optional) Refresh DuckDB local
python run_pipeline.py --init-db
```

ตรวจ output:
- `02_Silver_Cleaned/Master_GL_26_26.parquet` — ควรมี row count เพิ่มขึ้น
- `03_Gold_DataMarts/Summary_GL_26_26.parquet` — ควรมี row count เพิ่มขึ้น

### Step 3 — Upload ขึ้น Neon PostgreSQL
```bash
python -X utf8 upload_to_neon.py --domain all
```

ใช้เวลา ~5–10 นาที (583K+ rows)  
ตรวจ: ดู log ว่า `✅ v_gl uploaded` และ `✅ v_gl_summary uploaded`

### Step 4 — Verify Dashboard
เปิด `https://fintech-command-center.vercel.app/finance/performance`  
เลือก period เดือนล่าสุด → ต้องแสดง **LIVE** badge (ไม่ใช่ DEMO)

---

## โมดูลถัดไปที่จะเชื่อม (ลำดับความสำคัญ)

### 1. Cost Ledger (`/monitor/ledger`) — พร้อมแล้ว รอ verify
- Backend endpoint มีอยู่แล้ว (`GET /api/v1/monitor/cost-ledger`)
- v_gl อยู่บน Neon แล้ว
- **งาน:** ตรวจสอบว่า Cost Center prefix 1300/1100/1200 ใน v_gl ตรงกับข้อมูลจริง
- ทดสอบ: `curl "https://finance-data-lake.onrender.com/api/v1/monitor/cost-ledger?plant=1300&year=2026&quarter=1"`

### 2. Monitor Overview (`/monitor/overview`) — ต้องการ Sales data
- ต้องการ `v_sales` สำหรับ GP margin
- **งาน:** Export VF05 → `01_Bronze_Raw/Sales_Reports/2026/sale_2026_MM.XLSX` แล้วรัน:
  ```bash
  python run_pipeline.py --layer silver --domain sales --year 2026
  ```

### 3. P&L Summary (`/monitor/pnl-summary`) — ต้องการ Sales data
- Backend endpoint มีอยู่แล้ว (`GET /api/v1/monitor/pnl`)
- Frontend เชื่อม API แล้ว (wired ใน session นี้)
- ยังแสดง DEMO เพราะ v_sales ยังไม่มี 2026

### 4. Budget vs Actual — ต้องการ Budget file
- รับ Budget file จาก Finance team ก่อน
- Format: ปี / เดือน / GL_Group / budget_amount

---

## ไฟล์สำคัญ

| ไฟล์ | หน้าที่ |
|---|---|
| `upload_to_neon.py` | Upload Silver/Gold → Neon (รันหลัง pipeline) |
| `04_Data_Pipelines/silver_transform/etl_gl.py` | Bronze Excel → Silver Parquet |
| `04_Data_Pipelines/gold_aggregation/create_gold_summary.py` | Silver → Gold Summary |
| `backend/routers/dashboard.py` | Finance Performance / Liquidity / WC / Cash Flow |
| `backend/routers/monitor.py` | Monitor Overview / Cost Ledger / P&L |

---

## Connection String

```
Neon PostgreSQL (ap-southeast-1):
ep-morning-glade-aoeucyd9-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb

Render API:
https://finance-data-lake.onrender.com

Vercel Frontend:
https://fintech-command-center.vercel.app
```
