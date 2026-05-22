"""
mb51_cost_breakdown.py
======================
MB51 Cost Breakdown by Material Type — Plant 1300 / 1100 / 1200
รวม MB51 + MARA เพื่อแยกต้นทุนเป็น Raw Material / Semi-Finished / Scrap / Supplies / Spare Parts

Input files (01_Raw/PRD_GI/):
  - MB51_all plant_03.2026.XLSX   (61,838 rows — Mvt 261/201/531)
  - MB51_ingot_03.2026.XLSX       (1,366 rows — Ingot Mvt 101/301/311/312)
  - MARA_03.2026.XLSX             (50,272 rows — Material Master)

Output (02_Working/):
  - mb51_cost_breakdown_YYYYMMDD_HHMMSS.xlsx
    Tab: Summary    — Total by Plant × Cost Category × Month
    Tab: Detail_1300 / Detail_1100 / Detail_1200 — Row-level with category
    Tab: Unclassified — materials ไม่พบใน MARA

Prepared by: Claude Code | 2026-05-19
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent.parent.parent  # _Finance_Data_Lake/
RAW  = BASE / "01_Bronze_Raw" / "PRD_GI"
OUT  = Path(__file__).resolve().parent.parent / "02_Working"
OUT.mkdir(parents=True, exist_ok=True)

MB51_ALL    = RAW / "MB51_all plant_03.2026.XLSX"
MB51_INGOT  = RAW / "MB51_ingot_03.2026.XLSX"
MARA_FILE   = RAW / "MARA_03.2026.XLSX"

# ── Constants ─────────────────────────────────────────────────────────────────
# Movement types to include
INCLUDE_MVT = {"261", "201", "531"}

# Material type → Cost Category
MATTYPE_TO_CATEGORY = {
    "ZRMA": "Raw Material",
    "ZSMA": "Semi-Finished",
    "ZSCP": "Scrap/By-product",
    "ZSUP": "Supplies",
    "ZSPA": "Spare Parts",
    "ZFGA": "Finished Goods",
    "ZFGC": "Finished Goods Component",
    "ZRMC": "Raw Material Component",
    "ZSMC": "Semi-Finished Component",
    "ZEQT": "Equipment",
    "ZNOS": "Non-stock",
    "ZNOV": "Non-valuated",
    "ZSER": "Service",
    "ZTRA": "Trading Material",
}

# Sign convention: debit = negative (cost), credit = positive (recovery)
# Mvt 531 = by-product receipt → amount in MB51 is positive (credit to production cost)
# Mvt 261 = GI to order → negative
# Mvt 201 = GI to CC   → negative


def load_mara() -> pd.DataFrame:
    """Load MARA — return slim DataFrame with Material, Material type, Material Group, Description."""
    print("Loading MARA...")
    df = pd.read_excel(MARA_FILE, dtype=str, usecols=["Material", "Material type", "Material Group", "Material description"])
    df.columns = ["material", "mat_type", "mat_group", "mat_desc"]
    df["material"] = df["material"].str.strip()
    print(f"  MARA: {len(df):,} rows")
    return df


def load_mb51_all(mara: pd.DataFrame) -> pd.DataFrame:
    """Load MB51 all-plant and join with MARA for classification."""
    print("Loading MB51 all plant...")
    df = pd.read_excel(MB51_ALL, dtype=str)
    print(f"  Raw rows: {len(df):,} | Columns: {list(df.columns[:10])}")

    # Normalise column names (SAP export may have different capitalisation)
    df.columns = [c.strip() for c in df.columns]

    # Identify key columns — try common SAP MB51 column names
    col_map = _detect_mb51_columns(df)
    print(f"  Column mapping: {col_map}")

    df = df.rename(columns=col_map)

    # Filter movement types
    df["mvt"] = df["mvt"].str.strip()
    df = df[df["mvt"].isin(INCLUDE_MVT)].copy()
    print(f"  After Mvt filter ({', '.join(INCLUDE_MVT)}): {len(df):,} rows")

    # Numeric amount
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0).round(2)

    # Parse posting date → month
    df["posting_date"] = pd.to_datetime(df["posting_date"], dayfirst=True, errors="coerce")
    df["month"] = df["posting_date"].dt.to_period("M").astype(str)

    # Material — strip leading zeros issue: SAP sometimes pads to 18 chars
    df["material"] = df["material"].str.strip().str.lstrip("0")

    # Join MARA
    df = df.merge(mara, on="material", how="left")
    df["cost_category"] = df["mat_type"].map(MATTYPE_TO_CATEGORY).fillna("Unknown")

    return df


def load_mb51_ingot(mara: pd.DataFrame) -> pd.DataFrame:
    """Load MB51 ingot file — same join logic."""
    print("Loading MB51 ingot...")
    df = pd.read_excel(MB51_INGOT, dtype=str)
    print(f"  Raw rows: {len(df):,}")
    df.columns = [c.strip() for c in df.columns]

    col_map = _detect_mb51_columns(df)
    df = df.rename(columns=col_map)

    df["mvt"] = df["mvt"].str.strip()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0).round(2)
    df["posting_date"] = pd.to_datetime(df["posting_date"], dayfirst=True, errors="coerce")
    df["month"] = df["posting_date"].dt.to_period("M").astype(str)
    df["material"] = df["material"].str.strip().str.lstrip("0")

    df = df.merge(mara, on="material", how="left")
    df["cost_category"] = df["mat_type"].map(MATTYPE_TO_CATEGORY).fillna("Unknown")
    return df


def _detect_mb51_columns(df: pd.DataFrame) -> dict:
    """Map actual column names → standardised names."""
    cols = {c.lower(): c for c in df.columns}
    mapping = {}

    for src, targets in [
        ("material",      ["material", "material number", "matnr"]),
        ("mvt",           ["movement type", "mvt", "movement", "bwart"]),
        ("amount",        ["amt.in loc.cur.", "amount in lc", "amount", "total val.in lc", "value in lc", "wrbtr", "dmbtr"]),
        ("qty",           ["qty in unit of entry", "qty in puom", "quantity", "qty", "menge"]),
        ("unit",          ["unit of entry", "parallel uom", "unit", "uom", "meins"]),
        ("plant",         ["plant", "werks"]),
        ("posting_date",  ["posting date", "posting_date", "budat"]),
        ("order",         ["order", "order number", "aufnr"]),
        ("cost_center",   ["cost center", "cost ctr", "kostl"]),
        ("sloc",          ["storage location", "sloc", "lgort"]),
        ("mat_doc",       ["material document", "mat. doc.", "mblnr"]),
        ("batch",         ["batch", "charge"]),
        ("description",   ["material description", "maktx", "short text"]),
    ]:
        for t in targets:
            if t in cols:
                mapping[cols[t]] = src
                break

    return mapping


def build_summary(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Pivot: Plant × Cost Category × Month — Amount sum."""
    grp = df.groupby(["plant", "cost_category", "mvt", "month"])["amount"].sum().round(2).reset_index()
    grp.insert(0, "source", label)
    return grp


def write_output(df_all: pd.DataFrame, df_ingot: pd.DataFrame, mara: pd.DataFrame):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUT / f"mb51_cost_breakdown_{ts}.xlsx"

    print(f"\nWriting output to {out_path}...")

    # Summary pivot
    summary_all   = build_summary(df_all[df_all["mvt"].isin(INCLUDE_MVT)], "MB51_all")
    summary_ingot = build_summary(df_ingot, "MB51_ingot")
    summary = pd.concat([summary_all, summary_ingot], ignore_index=True)

    # Wide pivot: rows=plant+cost_category, cols=month
    pivot = summary.groupby(["plant", "cost_category", "mvt"])["amount"].sum().unstack("mvt").round(2)
    pivot = pivot.reset_index()

    # Unclassified materials
    unclass = df_all[df_all["cost_category"] == "Unknown"][["material", "mat_type", "plant", "mvt", "amount"]].drop_duplicates("material")
    unclass_ingot = df_ingot[df_ingot["cost_category"] == "Unknown"][["material", "mat_type", "plant", "mvt", "amount"]].drop_duplicates("material")
    unclassified = pd.concat([unclass, unclass_ingot])

    # Plant detail tabs
    detail = {}
    for plant in ["1300", "1100", "1200"]:
        sub = df_all[df_all["plant"].astype(str).str.strip() == plant]
        if len(sub):
            keep_cols = ["month", "plant", "material", "description", "mat_type", "mat_group",
                         "cost_category", "mvt", "amount"]
            for c in ["qty", "unit", "order", "cost_center", "sloc"]:
                if c in sub.columns:
                    keep_cols.append(c)
            detail[f"Detail_{plant}"] = sub[[c for c in keep_cols if c in sub.columns]].copy()

    # Month × Category summary (readable)
    monthly = (
        df_all.groupby(["plant", "month", "cost_category"])["amount"]
        .sum().round(2).reset_index()
        .pivot_table(index=["plant", "cost_category"], columns="month", values="amount", aggfunc="sum")
        .round(2)
        .reset_index()
    )

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        # Sheet 1: Monthly summary (readable)
        monthly.to_excel(writer, sheet_name="Summary_Monthly", index=False)
        # Sheet 2: Raw pivot by mvt
        pivot.to_excel(writer, sheet_name="Summary_by_Mvt", index=False)
        # Sheet 3: Plant detail
        for tab, df_tab in detail.items():
            df_tab.to_excel(writer, sheet_name=tab, index=False)
        # Sheet 4: Ingot detail
        df_ingot.to_excel(writer, sheet_name="Ingot", index=False)
        # Sheet 5: Unclassified
        unclassified.to_excel(writer, sheet_name="Unclassified", index=False)
        # Sheet 6: Full detail
        df_all.to_excel(writer, sheet_name="Full_Detail", index=False)

    print(f"  Done. Rows: all={len(df_all):,}, ingot={len(df_ingot):,}")
    print(f"  Unclassified materials: {len(unclassified):,}")
    return out_path


def print_breakdown(df_all: pd.DataFrame):
    """Print console summary for quick review."""
    print("\n" + "=" * 70)
    print("MB51 COST BREAKDOWN SUMMARY — Q1 2026 (all plants)")
    print("=" * 70)

    for plant in sorted(df_all["plant"].dropna().astype(str).str.strip().unique()):
        sub = df_all[df_all["plant"].astype(str).str.strip() == plant]
        total = sub["amount"].sum()
        print(f"\nPlant {plant}  (total = {total:>15,.2f} THB)")
        print(f"  {'Mvt':<5} {'Category':<25} {'Amount':>15}")
        print(f"  {'-'*5} {'-'*25} {'-'*15}")
        breakdown = sub.groupby(["mvt", "cost_category"])["amount"].sum().sort_index()
        for (mvt, cat), amt in breakdown.items():
            print(f"  {mvt:<5} {cat:<25} {amt:>15,.2f}")


def main():
    print(f"MB51 Cost Breakdown | {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("-" * 60)

    mara    = load_mara()
    df_all  = load_mb51_all(mara)
    df_ingot = load_mb51_ingot(mara)

    print_breakdown(df_all)

    out_path = write_output(df_all, df_ingot, mara)
    print(f"\nOutput saved: {out_path}")
    print("\nPrepared by: Claude Code")


if __name__ == "__main__":
    main()
