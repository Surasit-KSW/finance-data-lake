"""
reports.py — /api/reports/* endpoints
เสิร์ฟข้อมูล Leadsheet / Cash Flow / PPE / Elimination / Related Party
จาก Gold DataMarts parquet files
"""
import os
import sys

import pandas as pd
from fastapi import APIRouter, Query, HTTPException

router = APIRouter(prefix="/api/reports", tags=["Financial Reports"])

# ── paths ──────────────────────────────────────────────────────────────────────
_HERE        = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))
GOLD_DIR     = os.path.join(PROJECT_ROOT, "03_Gold_DataMarts")

VALID_QUARTERS = {"Q1", "Q2", "Q3", "Q4", "FY"}


def _load(filename: str) -> pd.DataFrame:
    path = os.path.join(GOLD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail=f"{filename} not found. Run the pipeline first: "
                   f"python -m 04_Data_Pipelines.gold_aggregation.{filename.replace('gold_','create_').replace('.parquet','')}",
        )
    return pd.read_parquet(path)


def _filter(df: pd.DataFrame, year: int, quarter: str,
            entity_type: str | None = None) -> pd.DataFrame:
    mask = (df["year"] == year) & (df["quarter"] == quarter.upper())
    if entity_type:
        mask &= df["entity_type"] == entity_type
    result = df[mask]
    if result.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No data for year={year} quarter={quarter}. Run the pipeline.",
        )
    return result


# ── Leadsheet ─────────────────────────────────────────────────────────────────
@router.get("/leadsheet")
def get_leadsheet(
    year:        int = Query(..., description="ปีงบการเงิน เช่น 2025"),
    quarter:     str = Query("FY", description="Q1 | Q2 | Q3 | Q4 | FY"),
    entity_type: str = Query("stat", description="stat | conso"),
    statement:   str = Query("BS",  description="BS | PL | all"),
):
    """
    Trial Balance จัดกลุ่มตาม FS line items พร้อมทั้ง BS และ PL
    ใช้สำหรับกรอกข้อมูลใน Leadsheet worksheet
    """
    if quarter.upper() not in VALID_QUARTERS:
        raise HTTPException(400, f"quarter must be one of {VALID_QUARTERS}")

    df   = _load("gold_leadsheet.parquet")
    data = _filter(df, year, quarter, entity_type)

    if statement.upper() != "ALL":
        data = data[data["statement"] == statement.upper()]
        if data.empty:
            raise HTTPException(404, f"No {statement} data found")

    # Build structured response grouped by section → lines
    result = {}
    for stmt in data["statement"].unique():
        s_data = data[data["statement"] == stmt]
        sections = {}
        for _, row in s_data.sort_values(["section_order", "line_order"]).iterrows():
            sec = row["section"]
            if sec not in sections:
                sections[sec] = {
                    "section":          sec,
                    "section_label_th": row["section_label_th"],
                    "section_label_en": row["section_label_en"],
                    "order":            int(row["section_order"]),
                    "lines":            [],
                    "subtotal":         0.0,
                }
            sections[sec]["lines"].append({
                "line_key":       row["line_key"],
                "label_th":       row["line_label_th"],
                "label_en":       row["line_label_en"],
                "order":          int(row["line_order"]),
                "amount":         round(float(row["amount_presented"]), 2),
            })
            sections[sec]["subtotal"] = round(
                sections[sec]["subtotal"] + float(row["amount_presented"]), 2
            )
        result[stmt] = sorted(sections.values(), key=lambda x: x["order"])

    return {
        "status":      "ok",
        "year":        year,
        "quarter":     quarter.upper(),
        "entity_type": entity_type,
        "period_end":  data["period_end"].iloc[0] if len(data) > 0 else None,
        "data":        result,
    }


@router.get("/leadsheet/flat")
def get_leadsheet_flat(
    year:        int = Query(...),
    quarter:     str = Query("FY"),
    entity_type: str = Query("stat"),
):
    """
    Flat list ของทุก line item — ง่ายสำหรับ Google Sheets writer ที่ต้องการ array เรียบ
    """
    if quarter.upper() not in VALID_QUARTERS:
        raise HTTPException(400, f"quarter must be one of {VALID_QUARTERS}")

    df   = _load("gold_leadsheet.parquet")
    data = _filter(df, year, quarter, entity_type)

    rows = data.sort_values(["statement","section_order","line_order"]).to_dict(orient="records")
    return {
        "status":      "ok",
        "year":        year,
        "quarter":     quarter.upper(),
        "entity_type": entity_type,
        "count":       len(rows),
        "data":        rows,
    }


# ── Cash Flow ─────────────────────────────────────────────────────────────────
@router.get("/cashflow")
def get_cashflow(
    year:        int = Query(...),
    quarter:     str = Query("FY"),
    entity_type: str = Query("stat"),
):
    """
    Cash Flow Statement (Indirect Method) พร้อม subtotals ต่อ section
    """
    if quarter.upper() not in VALID_QUARTERS:
        raise HTTPException(400, f"quarter must be one of {VALID_QUARTERS}")

    df   = _load("gold_cashflow.parquet")
    data = _filter(df, year, quarter, entity_type)

    sections = {}
    for _, row in data.sort_values(["section_order", "line_order"]).iterrows():
        sec = row["section"]
        if sec not in sections:
            sections[sec] = {
                "section":          sec,
                "section_label_th": row["section_label_th"],
                "section_label_en": row["section_label_en"],
                "order":            int(row["section_order"]),
                "lines":            [],
                "net_cash":         0.0,
            }
        sections[sec]["lines"].append({
            "line_key":  row["line_key"],
            "label_th":  row["line_label_th"],
            "label_en":  row["line_label_en"],
            "order":     int(row["line_order"]),
            "amount":    round(float(row["amount"]), 2),
        })
        sections[sec]["net_cash"] = round(
            sections[sec]["net_cash"] + float(row["amount"]), 2
        )

    sorted_sections = sorted(sections.values(), key=lambda x: x["order"])
    net_change      = sum(s["net_cash"] for s in sorted_sections)

    return {
        "status":      "ok",
        "year":        year,
        "quarter":     quarter.upper(),
        "entity_type": entity_type,
        "period_end":  data["period_end"].iloc[0],
        "net_cash_change": round(net_change, 2),
        "data":        sorted_sections,
    }


# ── PPE Schedule ──────────────────────────────────────────────────────────────
@router.get("/ppe")
def get_ppe(
    year:        int = Query(...),
    quarter:     str = Query("FY"),
    entity_type: str = Query("stat"),
):
    """
    PPE Roll-Forward Table จัดกลุ่มตาม asset class
    """
    if quarter.upper() not in VALID_QUARTERS:
        raise HTTPException(400, f"quarter must be one of {VALID_QUARTERS}")

    df   = _load("gold_ppe.parquet")
    data = _filter(df, year, quarter, entity_type)

    # Build pivot: asset_class × movement × movement_type
    classes = {}
    for _, row in data.sort_values(["class_order","movement_type","movement_order"]).iterrows():
        cls = row["asset_class"]
        if cls not in classes:
            classes[cls] = {
                "asset_class":    cls,
                "label_th":       row["class_label_th"],
                "label_en":       row["class_label_en"],
                "order":          int(row["class_order"]),
                "cost":           {},
                "accum_dep":      {},
                "net_book_value": 0.0,
            }
        m_type = row["movement_type"]
        mov    = row["movement"]
        amt    = round(float(row["amount"]), 2)
        if m_type in ("cost", "accum_dep"):
            classes[cls][m_type][mov] = amt

    # Compute NBV for each class
    for cls_data in classes.values():
        cost_close = cls_data["cost"].get("closing", 0.0)
        dep_close  = cls_data["accum_dep"].get("closing", 0.0)
        cls_data["net_book_value"] = round(cost_close - dep_close, 2)

    sorted_classes = sorted(classes.values(), key=lambda x: x["order"])
    total_cost_close = sum(c["cost"].get("closing", 0.0) for c in sorted_classes)
    total_dep_close  = sum(c["accum_dep"].get("closing", 0.0) for c in sorted_classes)

    return {
        "status":           "ok",
        "year":             year,
        "quarter":          quarter.upper(),
        "entity_type":      entity_type,
        "period_end":       data["period_end"].iloc[0],
        "total_cost":       round(total_cost_close, 2),
        "total_accum_dep":  round(total_dep_close, 2),
        "total_nbv":        round(total_cost_close - total_dep_close, 2),
        "data":             sorted_classes,
    }


# ── Elimination ───────────────────────────────────────────────────────────────
@router.get("/elimination")
def get_elimination(
    year:    int = Query(...),
    quarter: str = Query("FY"),
):
    """
    Consolidation Elimination Entries จัดกลุ่มตาม elimination type
    """
    if quarter.upper() not in VALID_QUARTERS:
        raise HTTPException(400, f"quarter must be one of {VALID_QUARTERS}")

    df   = _load("gold_elimination.parquet")
    data = _filter(df, year, quarter)

    groups = {}
    for _, row in data.sort_values(["elim_order"]).iterrows():
        et = row["elim_type"]
        if et not in groups:
            groups[et] = {
                "elim_type":     et,
                "label_th":      row["elim_label_th"],
                "label_en":      row["elim_label_en"],
                "order":         int(row["elim_order"]),
                "entries":       [],
                "total_dr":      0.0,
                "total_cr":      0.0,
            }
        groups[et]["entries"].append({
            "account":      row["account"],
            "account_name": row["account_name"],
            "dr_amount":    round(float(row["dr_amount"]), 2),
            "cr_amount":    round(float(row["cr_amount"]), 2),
            "net_amount":   round(float(row["net_amount"]), 2),
            "note":         row.get("note", ""),
            "data_source":  row.get("data_source", ""),
        })
        groups[et]["total_dr"] = round(groups[et]["total_dr"] + float(row["dr_amount"]), 2)
        groups[et]["total_cr"] = round(groups[et]["total_cr"] + float(row["cr_amount"]), 2)

    return {
        "status":   "ok",
        "year":     year,
        "quarter":  quarter.upper(),
        "period_end": data["period_end"].iloc[0],
        "_note":    "parent_gl_only: ยังใช้ข้อมูลบริษัทแม่เท่านั้น เพิ่ม Subsidiary GL เพื่อ full consolidation",
        "data":     sorted(groups.values(), key=lambda x: x["order"]),
    }


# ── Related Party ─────────────────────────────────────────────────────────────
@router.get("/related-party")
def get_related_party(
    year:    int = Query(...),
    quarter: str = Query("FY"),
):
    """
    Related Party Transactions & Balances แยกตาม category
    """
    if quarter.upper() not in VALID_QUARTERS:
        raise HTTPException(400, f"quarter must be one of {VALID_QUARTERS}")

    df   = _load("gold_related_party.parquet")
    data = _filter(df, year, quarter)

    categories = {}
    for _, row in data.iterrows():
        key = row["category_key"]
        if key not in categories:
            categories[key] = {
                "category_key":    key,
                "label_th":        row["category_label_th"],
                "label_en":        row["category_label_en"],
                "data_type":       row["data_type"],
                "accounts":        [],
                "total":           0.0,
            }
        categories[key]["accounts"].append({
            "account":      row["account"],
            "account_name": row["account_name"],
            "amount":       round(float(row["amount"]), 2),
        })
        categories[key]["total"] = round(
            categories[key]["total"] + float(row["amount"]), 2
        )

    return {
        "status":     "ok",
        "year":       year,
        "quarter":    quarter.upper(),
        "period_end": data["period_end"].iloc[0],
        "data":       list(categories.values()),
    }


# ── Run all pipelines ─────────────────────────────────────────────────────────
@router.post("/build")
def build_reports(
    year:    int = Query(...),
    quarter: str = Query("FY"),
):
    """
    Trigger ทุก Gold pipeline สำหรับ year/quarter ที่กำหนด
    (รัน leadsheet → cashflow → ppe → elimination → related_party ตามลำดับ)
    """
    import threading
    import importlib.util

    def _import(name):
        spec = importlib.util.spec_from_file_location(
            name,
            os.path.join(PROJECT_ROOT, "04_Data_Pipelines", "gold_aggregation", f"{name}.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    create_leadsheet    = _import("create_leadsheet")
    create_cashflow     = _import("create_cashflow")
    create_ppe_schedule = _import("create_ppe_schedule")
    create_elimination  = _import("create_elimination")
    create_related_party= _import("create_related_party")

    results = {}

    def _run():
        try:
            create_leadsheet.run(year, quarter)
            results["leadsheet"] = "ok"
        except Exception as e:
            results["leadsheet"] = str(e)
        try:
            create_cashflow.run(year, quarter)
            results["cashflow"] = "ok"
        except Exception as e:
            results["cashflow"] = str(e)
        try:
            create_ppe_schedule.run(year, quarter)
            results["ppe"] = "ok"
        except Exception as e:
            results["ppe"] = str(e)
        try:
            create_elimination.run(year, quarter)
            results["elimination"] = "ok"
        except Exception as e:
            results["elimination"] = str(e)
        try:
            create_related_party.run(year, quarter)
            results["related_party"] = "ok"
        except Exception as e:
            results["related_party"] = str(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=120)

    return {
        "status":  "completed",
        "year":    year,
        "quarter": quarter.upper(),
        "results": results,
    }
