# Finance Data Lake — Architecture Plan

> Created: 2026-05-22
> Goal: ทำให้ Finance Data Lake เป็น API Data Center จริงๆ ไม่ใช่แค่ script dump

---

## หลักการ — Data Lake ทำแค่ 3 อย่าง

```
1. รับข้อมูลดิบ (Ingest)     → 01_Bronze_Raw/
2. แปลงและเก็บ (Transform)   → 02_Silver → 03_Gold → DuckDB/PostgreSQL
3. เปิด API ให้ดึง (Serve)   → backend/ REST API
```

**ไม่ใช่หน้าที่ของ Data Lake:**
- แสดง UI
- ส่ง message / notification
- ทำ automation งาน finance ops

---

## ปัญหาตอนนี้ — "ทำทุกอย่างในที่เดียว"

| สิ่งที่มีตอนนี้ | สถานะ | ควรทำ |
|---|---|---|
| ETL Pipeline (`04_Data_Pipelines/`) | ✅ ถูกที่ | คงไว้ |
| REST API (`backend/`) | ✅ ถูกที่ | คงไว้ |
| DuckDB / PostgreSQL | ✅ ถูกที่ | คงไว้ |
| Streamlit Dashboard (`05_Dashboards/`) | ⚠️ ควรแยก | ย้ายไป project แยกระยะยาว |
| Telegram Bot (`telegram_bot/`) | ❌ ไม่ควรอยู่ | ย้ายไป `_Finance-Bot` |
| Google Sheets / Ops (`07_Workspace/`) | ❌ ไม่ควรอยู่ | ย้ายไป `_Finance-Ops` |
| Ad-hoc scripts (`06_Scripts/`) | ⚠️ บางส่วน | เก็บเฉพาะ audit/reporting ที่ feed API |

---

## Target Architecture

```
_Finance_Data_Lake (API Data Center)
│   → รับ SAP data → แปลง → เก็บ → serve API เท่านั้น
│
├── _Finance-Bot           (Telegram Bot — consumer ของ API)
├── _Finance-Ops           (Google Sheets, month-end, reconcile — consumer ของ API)
└── Consumers:
    ├── main-dashboard
    ├── fin-dashboard
    ├── audit-reconcile
    └── sap_cost_closing_app
```

---

## ข้อมูลที่ยังขาด (ควรเพิ่ม)

| Domain | SAP Source | Priority |
|---|---|---|
| Inventory / Stock | MB52 ครบทุก plant | High |
| Budget vs Actual | — | High |
| Fixed Assets | สินทรัพย์ถาวร | Medium |
| Vendor / AP data | FBL1N | Medium |
| Cost Center hierarchy | — | Low |

---

## Infrastructure ที่ยังขาด

| สิ่งที่ขาด | ทำไมสำคัญ |
|---|---|
| Data Catalog | รู้ว่ามีข้อมูลอะไร, fresh แค่ไหน |
| API Authentication (API Key) | consumer projects ต้องการ auth |
| Data freshness tracking | รู้ว่า data update ล่าสุดเมื่อไหร่ |
| API versioning ที่ชัดเจน | v1 → v2 migration path |

---

## Roadmap

### Phase 1 — Fix & Stabilize (Short term)
> แก้ของที่มีอยู่ให้ถูกต้องก่อน

- [ ] แก้ `audit_data.py` — ลบ `strftime()` เปลี่ยนเป็น `EXTRACT()` + ลบ silent fallback
- [ ] เพิ่ม `v_ar` view ใน `init_duckdb.py`
- [ ] เพิ่ม auth guard ใน `/api/v1/financial/leadsheet/build`
- [ ] Update `TB_FILES` ใน `financial_tb.py` ให้ใช้ glob แทน versioned filename

### Phase 2 — Expand Data (Medium term)
> เพิ่มข้อมูลใหม่เข้า Data Lake

- [ ] เพิ่ม Inventory ETL (MB52 ครบทุก plant → Silver → API)
- [ ] เพิ่ม Budget vs Actual domain
- [ ] เพิ่ม AP/Vendor data (FBL1N)
- [ ] เพิ่ม Data freshness endpoint (`/api/v1/catalog`)

### Phase 3 — Separate Concerns (Long term)
> แยก project ที่ไม่ใช่ Data Layer ออก

- [ ] แยก `telegram_bot/` → `_Finance-Bot` project (consumer ของ API)
- [ ] แยก `07_Workspace/` → `_Finance-Ops` project (consumer ของ API)
- [ ] พิจารณาแยก `05_Dashboards/` → standalone project

---

## กฎที่ห้ามทำใน Data Lake นี้

1. ห้าม push notification / send message จาก Data Lake โดยตรง
2. ห้าม render UI ใน backend layer
3. ห้าม hardcode business logic ที่เปลี่ยนบ่อย (rules ต้องมาจาก config)
4. ห้าม consumer project หนึ่งดึงข้อมูลโดยตรงจาก Parquet — ต้องผ่าน API เท่านั้น
