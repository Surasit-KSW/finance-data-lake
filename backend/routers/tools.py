"""
tools.py — Data Tools status API
GET /api/v1/tools/status  → Bronze file inventory + Silver/Gold parquet status
"""
import os
import glob
from datetime import datetime
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BRONZE = os.path.join(PROJECT_ROOT, "01_Bronze_Raw")
SILVER = os.path.join(PROJECT_ROOT, "02_Silver_Cleaned")
GOLD   = os.path.join(PROJECT_ROOT, "03_Gold_DataMarts")


def _file_info(path: str) -> dict:
    if not os.path.exists(path):
        return {"exists": False}
    stat = os.stat(path)
    return {
        "exists": True,
        "size_kb": round(stat.st_size / 1024),
        "updated": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
    }


def _scan_bronze_months(pattern: str, months: list[str]) -> dict[str, bool]:
    """Check which months exist for a given glob pattern with {mm} placeholder."""
    result = {}
    for mm in months:
        expanded = pattern.replace("{mm}", mm)
        result[mm] = bool(glob.glob(os.path.join(BRONZE, expanded)))
    return result


@router.get("/status")
def get_tools_status():
    months_2026 = ["01", "02", "03", "04", "05"]

    # ── Bronze ───────────────────────────────────────────────────────────────
    bronze = {
        "sales_2026": _scan_bronze_months(
            "sales/amc/2026/vf05_2026{mm}.xlsx", months_2026),
        "production_2026": _scan_bronze_months(
            "warehouse_stock/amc/2026/mb52_1100_2026{mm}.xlsx", months_2026),
        "prd_1100": _scan_bronze_months(
            "production_orders/amc/1100/2026/prd_2026{mm}.xlsx", months_2026),
        "prd_1200": _scan_bronze_months(
            "production_orders/amc/1200/2026/prd_2026{mm}.xlsx", months_2026),
        "prd_1300": _scan_bronze_months(
            "production_orders/amc/1300/2026/prd_2026{mm}.xlsx", months_2026),
        "mb51_all": _scan_bronze_months(
            "material_docs/amc/all/2026/mb51_all_2026{mm}.xlsx", months_2026),
        "ksb1_1100": _scan_bronze_months(
            "cost_center/amc/1100/2026/ksb1_2026{mm}.xlsx", months_2026),
        "ksb1_1200": _scan_bronze_months(
            "cost_center/amc/1200/2026/ksb1_2026{mm}.xlsx", months_2026),
        "ksb1_1300": _scan_bronze_months(
            "cost_center/amc/1300/2026/ksb1_2026{mm}.xlsx", months_2026),
        "gl_2026": _scan_bronze_months(
            "gl/amc/2026/gl_2026{mm}.xlsx", months_2026),
        "amc_tb": _scan_bronze_months(
            "tb_snapshots/amc/2026/tb_2026{mm}.xlsx", months_2026),
    }

    # ── Silver ────────────────────────────────────────────────────────────────
    silver_files = [
        ("master_sales_2026",      "master_sales_2026.parquet"),
        ("master_sales_2025",      "master_sales_2025.parquet"),
        ("master_production_2026", "master_production_2026.parquet"),
        ("master_prd_2026",        "master_prd_2026.parquet"),
        ("master_mb51_2026",       "master_mb51_2026.parquet"),
        ("master_ar",              "master_ar.parquet"),
        ("master_gl_2026",         "Master_GL_26_26.parquet"),
    ]
    silver = {key: _file_info(os.path.join(SILVER, fname))
              for key, fname in silver_files}

    # ── Gold — Pipeline ───────────────────────────────────────────────────────
    gold_pipeline = {
        "gold_gp_by_plant":     _file_info(os.path.join(GOLD, "gold_gp_by_plant.parquet")),
        "gold_revenue_monthly": _file_info(os.path.join(GOLD, "gold_revenue_monthly.parquet")),
        "summary_gl":           _file_info(os.path.join(GOLD, "Summary_GL_26_26.parquet")),
    }

    # ── Gold — Period Close ───────────────────────────────────────────────────
    gold_close = {
        "gold_cashflow":      _file_info(os.path.join(GOLD, "gold_cashflow.parquet")),
        "gold_leadsheet":     _file_info(os.path.join(GOLD, "gold_leadsheet.parquet")),
        "gold_ppe":           _file_info(os.path.join(GOLD, "gold_ppe.parquet")),
        "gold_elimination":   _file_info(os.path.join(GOLD, "gold_elimination.parquet")),
        "gold_related_party": _file_info(os.path.join(GOLD, "gold_related_party.parquet")),
    }

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "months": months_2026,
        "bronze": bronze,
        "silver": silver,
        "gold_pipeline": gold_pipeline,
        "gold_close": gold_close,
    }
