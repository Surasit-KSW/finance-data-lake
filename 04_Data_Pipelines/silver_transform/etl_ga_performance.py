"""
ETL: GA Performance — Bronze GL+PRD → Silver Parquet
=====================================================
Reads GA GL files (monthly, Jan-Dec) from Bronze layer,
computes P&L per month using ALL-5xxx COGS methodology,
and writes Silver parquet files for API consumption.

Also reads GA PRD files to compute production metrics (yield, carryover orders).

Output:
  02_Silver_Cleaned/ga_performance_{year}.parquet  — P&L per month
  02_Silver_Cleaned/ga_production_{year}.parquet   — Production metrics per month

Usage:
  cd _Finance_Data_Lake
  python 04_Data_Pipelines/silver_transform/etl_ga_performance.py
  python 04_Data_Pipelines/silver_transform/etl_ga_performance.py --year 2026
"""
import sys
import argparse
from pathlib import Path

import pandas as pd

# ── Path setup ────────────────────────────────────────────────────────────────
LAKE_ROOT = Path(__file__).resolve().parents[2]
GL_DIR  = LAKE_ROOT / "01_Bronze_Raw/gl/ga/2026"
TB_DIR  = LAKE_ROOT / "01_Bronze_Raw/tb_snapshots/ga"
PRD_DIR = LAKE_ROOT / "01_Bronze_Raw/production_orders/ga/2200"
SILVER  = LAKE_ROOT / "02_Silver_Cleaned"

MONTH_LABELS = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
}


# ── GL Reader ─────────────────────────────────────────────────────────────────
def read_gl(year: str, month: str):
    """Read GA GL file for a given year/month. Returns (Series by GL_Account, text_map dict)."""
    path = GL_DIR / f"gl_{year}{month}.xlsx"
    if not path.exists():
        return None, {}
    df = pd.read_excel(path, header=0)
    df.columns = [
        "Ledger", "Company", "GL_Account", "GL_Text", "Doc_No", "Biz_Place",
        "Posting_Date", "Doc_Date", "Reference", "Header_Text", "Amount", "Currency",
        "Text", "Doc_Type", "Cost_Center", "CC_Text", "CC_Short", "Clearing_Doc",
        "Clearing_Date", "Assignment", "Quantity", "UOM", "PO_Doc", "Vendor", "Vendor_Name",
    ]
    df = df[df["GL_Account"].notna()].copy()
    df["GL_Account"] = df["GL_Account"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    by_acct = df.groupby("GL_Account")["Amount"].sum()
    text_map = df.drop_duplicates("GL_Account").set_index("GL_Account")["GL_Text"].to_dict()
    return by_acct, text_map


def g(gl, acct):
    return float(gl.get(str(acct), 0.0))


def sum_prefix(gl, prefix):
    mask = gl.index.str.startswith(prefix)
    return float(gl[mask].sum()) if mask.any() else 0.0


def sum_prefixes(gl, prefixes):
    return sum(sum_prefix(gl, p) for p in prefixes)


# ── P&L Builder ───────────────────────────────────────────────────────────────
def build_pnl(year: str, month: str) -> dict | None:
    gl, _ = read_gl(year, month)
    if gl is None:
        return None

    r = {"period": f"{year}-{month}"}

    # Revenue (411x — credit = negative stored; negate for display)
    r["rev_dom"] = g(gl, "4111010")   # credit, negative stored
    r["rev_aff"] = g(gl, "4111030")   # credit, negative stored
    r["rev_ret"] = g(gl, "4112010")   # debit, positive — REDUCES revenue
    all_rev = gl[gl.index.str.startswith("411")]
    r["net_rev_raw"]  = float(all_rev.sum())
    r["net_revenue"]  = -r["net_rev_raw"]

    # COGS — ALL 5xxx (correct: includes WIP offset credits + variances + overhead)
    all_5xxx = gl[gl.index.str.startswith("5")]
    r["net_cogs"] = float(all_5xxx.sum())

    # COGS sub-components (display only)
    r["cogs_main"]       = sum_prefix(gl, "5111")
    r["cogs_adj"]        = g(gl, "5119010")
    r["cogs_adj_ml"]     = g(gl, "5119020")
    r["cogs_completion"] = sum_prefix(gl, "5211")   # WIP offset credit
    r["cogs_var"]        = sum_prefixes(gl, ["5311","5321","5331","5341","5351","5391"])
    r["cogs_overhead"]   = sum_prefixes(gl, [
        "5411","5511","5512","5513","5611",
        "5711","5811","5812","5911","5912",
        "5991","5994","5996","5999",
    ])

    r["gross_profit"] = r["net_revenue"] - r["net_cogs"]
    r["gp_margin"]    = (r["gross_profit"] / r["net_revenue"] * 100) if r["net_revenue"] else 0.0

    # Other Income (4211/4212 — credit = negative → negate)
    all_oi = gl[gl.index.str.startswith("4211") | gl.index.str.startswith("4212")]
    r["total_other_income"] = -float(all_oi.sum())
    r["oi_svc"]    = -g(gl, "4211010")
    r["oi_scrap"]  = -g(gl, "4211020")
    r["oi_int"]    = -g(gl, "4211040")
    r["oi_penny"]  = -g(gl, "4211090")
    r["oi_other"]  = -g(gl, "4211990")

    # Selling — ALL 6xxx
    all_sell = gl[gl.index.str.startswith("6")]
    r["total_selling"] = float(all_sell.sum())
    r["sell_transport"]  = g(gl, "6111030")
    r["sell_commission"] = g(gl, "6111040")
    r["sell_sample"]     = g(gl, "6111080")
    r["sell_sal"]        = g(gl, "6211010")
    r["sell_ot"]         = g(gl, "6211020")
    r["sell_inc"]        = g(gl, "6211030")
    r["sell_bonus"]      = g(gl, "6211040")
    r["sell_hr"]         = sum(g(gl, a) for a in ["6212020","6212030","6212040","6212050","6212990"])
    r["sell_dep"]        = g(gl, "6511030") + g(gl, "6511040")
    r["sell_rm"]         = g(gl, "6411070") + g(gl, "6411990")
    r["sell_travel"]     = g(gl, "6911010")
    r["sell_mobile"]     = g(gl, "6911020")
    r["sell_ins"]        = g(gl, "6913010")
    r["sell_entert"]     = g(gl, "6915010")
    r["sell_inv_loss"]   = g(gl, "6999020")
    sell_named = sum(r[k] for k in [
        "sell_transport","sell_commission","sell_sample","sell_sal","sell_ot",
        "sell_inc","sell_bonus","sell_hr","sell_dep","sell_rm","sell_travel",
        "sell_mobile","sell_ins","sell_entert","sell_inv_loss",
    ])
    r["sell_others"] = r["total_selling"] - sell_named

    # Admin — ALL 7xxx
    all_admin = gl[gl.index.str.startswith("7")]
    r["total_admin"] = float(all_admin.sum())
    r["admin_idle_cost"]  = g(gl, "7917010")
    r["admin_dep_veh"]    = g(gl, "7511030")
    r["admin_dep_furn"]   = g(gl, "7511040")
    r["admin_dep_comp"]   = g(gl, "7511060")
    r["admin_dep_soft"]   = g(gl, "7511070")
    r["admin_total_dep"]  = sum(r[k] for k in ["admin_dep_veh","admin_dep_furn","admin_dep_comp","admin_dep_soft"])
    r["admin_ecl_prov"]   = g(gl, "7916280")   # Allowance for doubtful debts
    r["admin_tax_prov"]   = g(gl, "7916240")   # Income tax expenses
    r["admin_rental"]     = g(gl, "7913010")
    r["admin_ins"]        = g(gl, "7914010")
    r["admin_legal"]      = g(gl, "7916031")
    r["admin_bank"]       = g(gl, "7916080")
    r["admin_rm_soft"]    = g(gl, "7411050")
    r["admin_rm_veh"]     = g(gl, "7411070")
    admin_named = sum(r[k] for k in [
        "admin_idle_cost","admin_total_dep","admin_ecl_prov","admin_tax_prov",
        "admin_rental","admin_ins","admin_legal","admin_bank","admin_rm_soft","admin_rm_veh",
    ])
    r["admin_others"] = r["total_admin"] - admin_named

    # EBIT / NP
    r["ebit"]        = r["gross_profit"] + r["total_other_income"] - r["total_selling"] - r["total_admin"]
    r["ebit_margin"] = (r["ebit"] / r["net_revenue"] * 100) if r["net_revenue"] else 0.0
    all_fin          = gl[gl.index.str.startswith("8")]
    r["total_finance"] = float(all_fin.sum())
    r["fin_lease"]   = g(gl, "8111040")
    r["net_profit"]  = r["ebit"] - r["total_finance"]
    r["np_margin"]   = (r["net_profit"] / r["net_revenue"] * 100) if r["net_revenue"] else 0.0

    # Production cost breakdown (factory overhead — for cost section)
    r["cons_rm"]    = g(gl, "5411010")
    r["cons_semi"]  = g(gl, "5411020")
    r["cons_fg"]    = g(gl, "5411030")
    r["cons_oem"]   = g(gl, "5411050")
    r["total_cons"] = r["cons_rm"] + r["cons_semi"] + r["cons_fg"] + r["cons_oem"]
    r["lab_dir_sal"] = g(gl, "5511010")
    r["lab_dir_ot"]  = g(gl, "5511020")
    r["lab_dir_inc"] = g(gl, "5511030")
    r["lab_in_sal"]  = g(gl, "5512010")
    r["lab_in_ot"]   = g(gl, "5512020")
    r["lab_in_inc"]  = g(gl, "5512030")
    r["lab_ben"]     = sum(g(gl, a) for a in ["5513020","5513030","5513040","5513050","5513060"])
    r["total_labour"] = sum(r[k] for k in [
        "lab_dir_sal","lab_dir_ot","lab_dir_inc","lab_in_sal","lab_in_ot","lab_in_inc","lab_ben"
    ])
    r["elec"] = sum_prefix(gl, "5611")
    r["rm_mach"]  = g(gl, "5711010"); r["rm_equip"] = g(gl, "5711020")
    r["rm_elec"]  = g(gl, "5711030"); r["rm_soft"]  = g(gl, "5711070")
    r["rm_veh"]   = g(gl, "5711090"); r["rm_other"] = g(gl, "5711990")
    r["total_rm"] = sum(r[k] for k in ["rm_mach","rm_equip","rm_elec","rm_soft","rm_veh","rm_other"])
    r["dep_equip"] = g(gl, "5811040"); r["dep_veh"]  = g(gl, "5811050")
    r["dep_furn"]  = g(gl, "5811060"); r["dep_comp"] = g(gl, "5811080")
    r["total_dep"] = r["dep_equip"] + r["dep_veh"] + r["dep_furn"] + r["dep_comp"]
    r["mach_rental"] = g(gl, "5812010")
    r["tools"]       = g(gl, "5911010"); r["supplies"]  = g(gl, "5911020")
    r["packaging"]   = g(gl, "5912010")
    r["total_other_mfg"] = (r["mach_rental"] + r["tools"] + r["supplies"] + r["packaging"] +
                             sum_prefixes(gl, ["5991","5994","5996","5999"]))
    r["total_prod"] = (r["total_cons"] + r["total_labour"] + r["elec"] +
                       r["total_rm"] + r["total_dep"] + r["total_other_mfg"])

    # Variances (memo)
    r["var_prod_semi"] = g(gl, "5311010"); r["var_prod_fg"]  = g(gl, "5311020")
    r["var_prod_oem"]  = g(gl, "5311030"); r["var_purch"]    = g(gl, "5321010")
    r["var_xfer"]      = g(gl, "5341010"); r["var_ml"]       = g(gl, "5391010")
    r["var_adj_pc"]    = g(gl, "5391020")

    return r


# ── PRD Reader ────────────────────────────────────────────────────────────────
def read_prd(year: str, month: str) -> dict | None:
    path = PRD_DIR / f"prd_{year}{month}.xlsx"
    if not path.exists():
        return None
    df = pd.read_excel(path, header=0)
    # Normalize numeric columns
    for col in df.columns:
        if "QTY" in str(col) or "Amount" in str(col):
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Find relevant columns (tolerant of exact naming)
    gi_col  = next((c for c in df.columns if "GI QTY"  in str(c) and "Actual" in str(c)), None)
    gr_col  = next((c for c in df.columns if "GR QTY"  in str(c) and "Actual" in str(c)), None)
    sc_col  = next((c for c in df.columns if "Scrap"   in str(c) and "Actual" in str(c) and "QTY" in str(c)), None)

    if gi_col is None or gr_col is None:
        print(f"  [WARN] PRD {month}.{year}: cannot find GI/GR QTY columns. Skipping PRD metrics.")
        return {"period": f"{year}-{month}"}

    df[gi_col] = pd.to_numeric(df[gi_col], errors="coerce").fillna(0)
    df[gr_col] = pd.to_numeric(df[gr_col], errors="coerce").fillna(0)
    scrap_vals = df[sc_col] if sc_col else pd.Series([0]*len(df))

    matched   = df[(df[gi_col] > 0) & (df[gr_col] > 0)]
    carryover = df[(df[gr_col] > 0) & (df[gi_col] == 0)]

    gi_matched  = float(matched[gi_col].sum())
    gr_matched  = float(matched[gr_col].sum())
    sc_matched  = float(matched[sc_col].sum()) if sc_col else 0.0
    yield_pct   = (gr_matched / gi_matched * 100) if gi_matched > 0 else 0.0
    scrap_pct   = (sc_matched / gi_matched * 100) if gi_matched > 0 else 0.0

    return {
        "period":           f"{year}-{month}",
        "total_orders":     len(df),
        "matched_orders":   len(matched),
        "carryover_orders": len(carryover),
        "gi_qty":           float(df[gi_col].sum()),
        "gr_qty":           float(df[gr_col].sum()),
        "gi_matched":       gi_matched,
        "gr_matched":       gr_matched,
        "scrap_qty":        float(scrap_vals.sum()),
        "scrap_matched":    sc_matched,
        "carryover_gr_qty": float(carryover[gr_col].sum()),
        "yield_pct":        round(yield_pct, 2),
        "scrap_pct":        round(scrap_pct, 2),
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="ETL: GA Performance Bronze → Silver")
    parser.add_argument("--year", default="2026", help="Year to process (default: 2026)")
    args = parser.parse_args()
    year = args.year

    months = [f"{m:02d}" for m in range(1, 13)]

    pnl_rows = []
    prd_rows = []

    for month in months:
        label = f"{MONTH_LABELS[month]} {year}"
        gl_path = GL_DIR / f"gl_{year}{month}.xlsx"
        if not gl_path.exists():
            print(f"  [SKIP] {label} — GL file not found")
            continue

        print(f"  Processing {label}...")
        pnl = build_pnl(year, month)
        if pnl:
            pnl_rows.append(pnl)
            print(f"    P&L: Rev={pnl['net_revenue']:,.0f}  GP={pnl['gross_profit']:,.0f} ({pnl['gp_margin']:.1f}%)  NP={pnl['net_profit']:,.0f} ({pnl['np_margin']:.1f}%)")

        prd = read_prd(year, month)
        if prd and "total_orders" in prd:
            prd_rows.append(prd)
            print(f"    PRD: Orders={prd['total_orders']}  GI={prd['gi_qty']:,.0f}  GR={prd['gr_qty']:,.0f}  Yield={prd['yield_pct']:.1f}%  Carryover={prd['carryover_orders']}")

    if not pnl_rows:
        print(f"ERROR: No GL data found for year {year}. Check path: {GL_DIR}")
        sys.exit(1)

    SILVER.mkdir(exist_ok=True)

    # Write P&L parquet
    pnl_out = SILVER / f"ga_performance_{year}.parquet"
    pd.DataFrame(pnl_rows).to_parquet(pnl_out, index=False)
    print(f"\nSaved: {pnl_out}  ({len(pnl_rows)} months)")

    # Write PRD parquet
    if prd_rows:
        prd_out = SILVER / f"ga_production_{year}.parquet"
        pd.DataFrame(prd_rows).to_parquet(prd_out, index=False)
        print(f"Saved: {prd_out}  ({len(prd_rows)} months)")


if __name__ == "__main__":
    main()
