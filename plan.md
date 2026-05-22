# Finance Data Lake — Architecture Plan

> Created: 2026-05-22 | Updated: 2026-05-22
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

## สถานะปัจจุบัน (2026-05-22)

| สิ่งที่มีอยู่ | สถานะ | แผน |
|---|---|---|
| ETL Pipeline (`04_Data_Pipelines/`) | ✅ ถูกที่ | คงไว้ |
| REST API (`backend/`) | ✅ ถูกที่ | คงไว้ |
| DuckDB / PostgreSQL | ✅ ถูกที่ | คงไว้ |
| Streamlit Dashboard (`05_Dashboards/`) | ⚠️ ควรแยก | ย้ายออก — Phase 3 |
| Telegram Bot (`telegram_bot/`) | ❌ ไม่ควรอยู่ | ย้ายไป `ai/finance-bot` — Phase 3 |
| Google Sheets / Ops (`07_Workspace/`) | ❌ ไม่ควรอยู่ | ย้ายไป `ai/finance-ops` — Phase 3 |
| Ad-hoc scripts (`06_Scripts/`) | ⚠️ บางส่วน | เก็บเฉพาะที่ feed API |

---

## Target Architecture (Ecosystem)

```
03_Data_Projects/
│
│   ── Pinned API Data Center ────────────────────────────────────────────
├── _Finance_Data_Lake/     รับ SAP → แปลง → เก็บ → serve API เท่านั้น
│
│   ── Consumers (ดึงข้อมูลจาก API) ──────────────────────────────────────
├── audit-reconcile/
├── sap_cost_closing_app/
├── main-dashboard/
├── fin-dashboard/
│
│   ── AI / Automation (future consumers) ────────────────────────────────
├── ai/
│   ├── accounting-agent/   ✅ แยกออกมาแล้ว — monthly accounting automation
│   ├── finance-bot/        🔲 ยังไม่มี — Telegram bot (ย้ายจาก telegram_bot/)
│   └── finance-ops/        🔲 ยังไม่มี — Google Sheets ops (ย้ายจาก 07_Workspace/)
│
│   ── Active Financial Projects ─────────────────────────────────────────
├── active/
│   ├── executive-financial-dashboard/  ✅ ย้ายแล้ว
│   ├── amc-dashboard/                  ✅ ย้ายแล้ว
│   └── project-gi-dashboard/           ✅ ย้ายแล้ว
│
└── tools/ | archive/ | vendor/         ✅ จัดแล้ว
```

---

## ข้อมูลที่ยังขาด (ควรเพิ่มใน Data Lake)

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
| Data Catalog endpoint | รู้ว่ามีข้อมูลอะไร, fresh แค่ไหน |
| API Authentication (API Key) | consumer projects ต้องการ auth |
| Data freshness tracking | รู้ว่า data update ล่าสุดเมื่อไหร่ |

---

## Roadmap

### Phase 1 — Fix & Stabilize ✅ / 🔲
> แก้ของที่มีอยู่ให้ถูกต้องก่อน

- [x] Cleanup git — ลบ stale `config/` refs, แก้ `.gitignore` inline comments
- [x] แก้ `audit_data.py` — ตรวจแล้วพบว่า clean อยู่แล้ว (ไม่มี strftime, ไม่มี silent fallback)
- [x] เพิ่ม `v_ar` view ใน `init_duckdb.py` — AR endpoints ใช้ได้ใน DuckDB แล้ว
- [x] เพิ่ม auth guard ใน `/api/v1/financial/leadsheet/build` — ใช้ X-Api-Key header + `LEADSHEET_API_KEY` env
- [x] Update `TB_FILES` ใน `financial_tb.py` — ใช้ `_latest(dir, "AMC_TB_03.2026_v*.XLSX")` แทน hardcode `_v9`

### Phase 2 — Expand Data
> เพิ่มข้อมูลใหม่เข้า Data Lake

- [ ] เพิ่ม Inventory ETL (MB52 ครบทุก plant → Silver → API)
- [ ] เพิ่ม Budget vs Actual domain
- [ ] เพิ่ม AP/Vendor data (FBL1N)
- [ ] เพิ่ม Data Catalog endpoint (`/api/v1/catalog`)

### Phase 3 — Separate Concerns
> แยก project ที่ไม่ใช่ Data Layer ออก

- [ ] แยก `telegram_bot/` → `ai/finance-bot/` (consumer ของ API)
- [ ] แยก `07_Workspace/` → `ai/finance-ops/` (consumer ของ API)
- [ ] พิจารณาแยก `05_Dashboards/` → standalone project

### Pending Cleanup (process lock)
- [ ] ลบ `_web app/` ที่ root — copy อยู่ใน `archive/_web-app/` แล้ว
- [ ] ลบ `Executive Financial Dashboard/` ที่ root — copy อยู่ใน `active/` แล้ว
- [ ] ย้าย `node/` → `vendor/node/` — Node.js runtime ติด process lock

---

## กฎที่ห้ามทำใน Data Lake นี้

1. ห้าม push notification / send message จาก Data Lake โดยตรง
2. ห้าม render UI ใน backend layer
3. ห้าม hardcode business logic ที่เปลี่ยนบ่อย (rules ต้องมาจาก config)
4. ห้าม consumer project ดึงข้อมูลโดยตรงจาก Parquet — ต้องผ่าน API เท่านั้น
