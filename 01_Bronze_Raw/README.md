# 01_Bronze_Raw — SAP Raw Exports

> **Read-only layer** — ห้ามแก้ไขไฟล์ใน folder นี้  
> ทุก ETL script อ่าน Bronze แต่ไม่เคย write กลับ

---

## ข้อมูลคืออะไร

ไฟล์ทั้งหมดใน Bronze คือ SAP export โดยตรง ยังไม่ผ่านการ clean หรือ transform

---

## Subfolders & Naming Conventions

| Folder | SAP Source | Naming Pattern | Update |
|---|---|---|---|
| `GL_Transactions/` | FBL3N | `sap_fbl3n.XLSX` | Replace monthly (ไฟล์เดิม) |
| `Sales_Reports/{YYYY}/` | VF05 | `sale_{YYYY}_{MM}.XLSX` | Add monthly (12 ไฟล์/ปี) |
| `Production/{YYYY}/` | MB52/CO | `{PLANT}_{YYYY}_{MM}.XLSX` | Add monthly (24+ ไฟล์/ปี) |
| `AR_Data/` | FBL5N | `AR_{YYYY}.XLSX` | Add yearly |
| `AP_Data/` | FBL1N | `AP_{YYYY}.XLSX` | Add yearly |
| `Inventory_RollStock/NRV/` | ZFI_TB | `AMC_TB_{MM}.{YYYY}_v{N}.XLSX` | Add per period |
| `Templates/` | — | ชื่อตามที่ได้รับ | Add as needed |
| `monthend/` | KSB1/CO | `GA_{CCTR}_*.XLSX` | Add monthly |
| `Master/` | KS13 | `KS13_Master.XLSX` | Replace when updated |
| `PRD_GI/` | MB51 | ตาม plant convention | Add per period |
| `Fixed_Assets_PPE/` | AR01/S_ALR | `PPE_{YYYY}.XLSX` | Add yearly |
| `Deposit/` | Bank statement | `Deposit_{YYYY}_{MM}.XLSX` | Add monthly |

---

## กฎการใช้งาน

1. **ห้ามแก้ไขไฟล์** — ถ้า SAP export ผิด ให้ export ใหม่แล้ว replace
2. **ห้าม API อ่าน Bronze โดยตรง** — ต้องผ่าน ETL → Silver → DuckDB views ก่อน
3. **ETL scripts อ่าน Bronze เท่านั้น** (ไม่ write) — output ไปที่ `02_Silver_Cleaned/`
4. Bronze ไม่ commit ใน git (gitignored — ขนาดใหญ่, sensitive data)

---

## เมื่อมีไฟล์ใหม่จาก SAP

```bash
# Drop ไฟล์ใน folder ที่ถูกต้อง แล้วรัน ETL
python run_pipeline.py --layer silver
python run_pipeline.py --layer gold
python run_pipeline.py --init-db
```

---

## เชื่อมกับ Layer ถัดไป

```
01_Bronze_Raw/ (Excel)
      ↓ 04_Data_Pipelines/silver_transform/etl_*.py
02_Silver_Cleaned/ (Parquet)
      ↓ 04_Data_Pipelines/gold_aggregation/create_*.py
03_Gold_DataMarts/ (Parquet, aggregated)
      ↓ init_duckdb.py → DuckDB views
REST API
```
