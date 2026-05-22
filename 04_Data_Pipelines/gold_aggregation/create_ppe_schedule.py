"""
create_ppe_schedule.py — Gold Pipeline: PPE Roll-Forward Schedule

ผลลัพธ์: 03_Gold_DataMarts/gold_ppe.parquet
Schema:
  year, quarter, period_end, entity_type,
  asset_class, class_label_th, class_label_en, class_order,
  movement_type,   (cost | accum_dep | net_book_value)
  movement_label,  (Opening Balance / Additions / Disposals / Depreciation Charge / Closing Balance)
  amount, currency

Sources (priority order):
  1. master_ppe.parquet   — raw PPE register from SAP AR02 (etl_ppe.py จะสร้าง)
  2. GL fallback          — ถ้ายังไม่มี PPE register ดึงยอดสะสมจาก v_gl แทน (balance only)

รัน: python -m 04_Data_Pipelines.gold_aggregation.create_ppe_schedule --year 2025 --quarter Q1
"""
import os
import sys
import json
import argparse
import logging

import duckdb
import pandas as pd

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))

DUCK_DB     = os.path.join(PROJECT_ROOT, "finance_lake.duckdb")
GOLD_DIR    = os.path.join(PROJECT_ROOT, "03_Gold_DataMarts")
SILVER_DIR  = os.path.join(PROJECT_ROOT, "02_Silver_Cleaned")
CFG_DIR     = os.path.join(PROJECT_ROOT, "08_Config")

PPE_SILVER  = os.path.join(SILVER_DIR, "master_ppe.parquet")
OUT_FILE    = os.path.join(GOLD_DIR, "gold_ppe.parquet")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

QUARTER_MONTHS = {
    "Q1": (1, 3,  "03-31"),
    "Q2": (1, 6,  "06-30"),
    "Q3": (1, 9,  "09-30"),
    "Q4": (1, 12, "12-31"),
    "FY": (1, 12, "12-31"),
}

MOVEMENT_LABELS = {
    "opening":     { "order": 1, "label_th": "ยอดยกมาต้นงวด",         "label_en": "Opening Balance" },
    "addition":    { "order": 2, "label_th": "เพิ่มขึ้นระหว่างงวด",   "label_en": "Additions" },
    "disposal":    { "order": 3, "label_th": "ตัดจำหน่ายระหว่างงวด",  "label_en": "Disposals" },
    "dep_charge":  { "order": 4, "label_th": "ค่าเสื่อมราคาประจำงวด", "label_en": "Depreciation Charge" },
    "transfer":    { "order": 5, "label_th": "โอน/ปรับปรุง",           "label_en": "Transfers / Adjustments" },
    "closing":     { "order": 6, "label_th": "ยอดคงเหลือปลายงวด",     "label_en": "Closing Balance" },
}


def _build_from_gl(year: int, month_from: int, month_to: int,
                   ppe_map: dict, con) -> pd.DataFrame:
    """
    Fallback: ดึง balance สะสมจาก GL accounts ของ PPE/Accum Dep
    ไม่มี opening/additions/disposals breakdown — แค่ closing balance
    """
    log.warning("master_ppe.parquet not found — using GL balance fallback (closing balance only)")

    acct_map = ppe_map["account_map"]
    classes  = ppe_map["asset_classes"]

    # Cumulative balance up to period end
    df = con.execute("""
        SELECT
            CAST("G/L Account" AS VARCHAR) AS account,
            SUM(Net_Amount) AS balance
        FROM v_gl
        WHERE CAST(Year AS INTEGER) <= ?
          AND CAST(Month AS INTEGER) <= ?
        GROUP BY "G/L Account"
    """, [year, month_to]).fetchdf()

    df["account"] = df["account"].astype(str)

    records = []
    for _, row in df.iterrows():
        acct = row["account"]
        if acct not in acct_map:
            continue
        cfg = acct_map[acct]
        cls = cfg["class"]
        mov = cfg["movement"]  # cost or accum_dep
        cls_def = classes.get(cls, {})

        # PPE cost accounts: debit positive = positive balance = cost
        # Accum dep accounts: credit normal = negative in GL → flip for presentation
        amount = float(row["balance"])
        if mov == "accum_dep":
            amount = amount * -1  # present as positive deduction

        records.append({
            "asset_class":     cls,
            "class_label_th":  cls_def.get("label_th", cls),
            "class_label_en":  cls_def.get("label_en", cls),
            "class_order":     cls_def.get("order", 99),
            "movement_type":   mov,
            "movement":        "closing",
            "movement_order":  MOVEMENT_LABELS["closing"]["order"],
            "movement_label_th": MOVEMENT_LABELS["closing"]["label_th"],
            "movement_label_en": MOVEMENT_LABELS["closing"]["label_en"],
            "amount":          round(amount, 2),
        })

    return pd.DataFrame(records)


def _build_from_ppe_register(year: int, quarter: str,
                              month_from: int, month_to: int,
                              ppe_map: dict) -> pd.DataFrame:
    """
    Full roll-forward from master_ppe.parquet (SAP AR02 data).
    Expected Silver columns:
      asset_class, movement_type (OPENING/ACQUISITION/RETIREMENT/DEPRECIATION/TRANSFER/CLOSING),
      fiscal_year, period, amount_cost, amount_dep
    """
    df = pd.read_parquet(PPE_SILVER)
    classes = ppe_map["asset_classes"]

    # Filter year
    if "fiscal_year" in df.columns:
        df = df[df["fiscal_year"] == year]

    # Map movement types → standard keys
    movement_map = {
        "OPENING":      "opening",
        "ACQUISITION":  "addition",
        "RETIREMENT":   "disposal",
        "DEPRECIATION": "dep_charge",
        "TRANSFER":     "transfer",
        "CLOSING":      "closing",
    }

    records = []
    for _, row in df.iterrows():
        cls     = str(row.get("asset_class", "")).lower()
        raw_mov = str(row.get("movement_type", "")).upper()
        mov     = movement_map.get(raw_mov, raw_mov.lower())
        cls_def = classes.get(cls, {"label_th": cls, "label_en": cls, "order": 99})
        mov_def = MOVEMENT_LABELS.get(mov, {"order": 99, "label_th": mov, "label_en": mov})

        for col, m_type in [("amount_cost", "cost"), ("amount_dep", "accum_dep")]:
            if col not in df.columns:
                continue
            amount = float(row.get(col, 0.0) or 0.0)
            if amount == 0:
                continue
            records.append({
                "asset_class":       cls,
                "class_label_th":    cls_def.get("label_th", cls),
                "class_label_en":    cls_def.get("label_en", cls),
                "class_order":       cls_def.get("order", 99),
                "movement_type":     m_type,
                "movement":          mov,
                "movement_order":    mov_def.get("order", 99),
                "movement_label_th": mov_def.get("label_th", mov),
                "movement_label_en": mov_def.get("label_en", mov),
                "amount":            round(amount, 2),
            })

    return pd.DataFrame(records)


def run(year: int, quarter: str = "FY"):
    quarter = quarter.upper()
    if quarter not in QUARTER_MONTHS:
        raise ValueError(f"quarter must be one of {list(QUARTER_MONTHS.keys())}")

    month_from, month_to, end_suffix = QUARTER_MONTHS[quarter]
    period_end = f"{year}-{end_suffix}"

    log.info(f"PPE Schedule  year={year}  quarter={quarter}  period={period_end}")

    ppe_map = json.load(open(os.path.join(CFG_DIR, "mapping_ppe.json"), encoding="utf-8"))

    if os.path.exists(PPE_SILVER):
        log.info("Using master_ppe.parquet (full roll-forward)")
        detail = _build_from_ppe_register(year, quarter, month_from, month_to, ppe_map)
    else:
        con = duckdb.connect(DUCK_DB, read_only=True)
        try:
            detail = _build_from_gl(year, month_from, month_to, ppe_map, con)
        finally:
            con.close()

    # Aggregate by class + movement_type + movement
    agg = (
        detail.groupby([
            "asset_class", "class_label_th", "class_label_en", "class_order",
            "movement_type", "movement", "movement_order",
            "movement_label_th", "movement_label_en",
        ], as_index=False)
        .agg(amount=("amount", "sum"))
    )

    agg["year"]        = year
    agg["quarter"]     = quarter
    agg["period_end"]  = period_end
    agg["entity_type"] = "stat"
    agg["currency"]    = "THB"

    os.makedirs(GOLD_DIR, exist_ok=True)

    if os.path.exists(OUT_FILE):
        existing = pd.read_parquet(OUT_FILE)
        existing = existing[~(
            (existing["year"] == year) & (existing["quarter"] == quarter)
        )]
        final = pd.concat([existing, agg], ignore_index=True)
    else:
        final = agg

    final.to_parquet(OUT_FILE, index=False)
    log.info(f"Saved {len(agg)} rows → {OUT_FILE}")

    # Summary NBV
    cost_total = agg[agg["movement_type"] == "cost"]["amount"].sum()
    dep_total  = agg[agg["movement_type"] == "accum_dep"]["amount"].sum()
    log.info(f"  Total Cost:        {cost_total:>15,.0f}")
    log.info(f"  Accum Dep:         {dep_total:>15,.0f}")
    log.info(f"  Net Book Value:    {cost_total - dep_total:>15,.0f}")

    return agg


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build gold_ppe.parquet")
    parser.add_argument("--year",    type=int, required=True)
    parser.add_argument("--quarter", type=str, default="FY")
    args = parser.parse_args()
    run(args.year, args.quarter)
