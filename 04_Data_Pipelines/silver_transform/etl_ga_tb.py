"""
etl_ga_tb.py
============
ETL: GA Trial Balance (TB) Excel → Silver parquet

Input  : 01_Bronze_Raw/tb_snapshots/ga/{YYYY}/tb_{YYYYMM}.xlsx
Output : 02_Silver_Cleaned/ga_tb_{year}.parquet

Columns in output parquet:
  period         — YYYY-MM
  # Cash & Cash Equivalents
  cash_petty     — 1111010
  cash_bank_scb1 — 1112070
  cash_bank_bbl  — 1112090
  cash_bank_scb2 — 1112140
  cash_other     — remaining 111x accounts (outgoing, current)
  cash_total     — sum all 111x
  # Account Receivable Trade
  ar_domestic    — 1121010
  ar_affiliate   — 1121030
  ar_total       — 1121010 + 1121030
  # Inventory
  inv_rm         — 1131010
  inv_semi_fg    — 1131020
  inv_fg         — 1131030
  inv_other      — 1132xxx + 1133xxx (trading/consumable/spare/scrap/OEM)
  inv_provision  — 1139020 (negative, allowance for valuation)
  inv_total      — sum all 113x
  # Accounts Payable
  ap_affiliate   — 2121030 (absolute value, positive = liability)
  ap_domestic    — 2122010
  ap_employee    — 2122030
  ap_leasing     — 2122090
  ap_other       — remaining 2122xxx
  ap_total       — sum all 212x (absolute value)
  # Customer deposits & advances
  cust_deposit   — 2131010 + 2131020 + 2131030 (absolute value)
  # Accruals
  accrued_bonus  — 2141050
  accrued_other  — 2141010 + 2141040 + 2141070 + 2141080 + 2149910

Usage:
  python 04_Data_Pipelines/silver_transform/etl_ga_tb.py
  python 04_Data_Pipelines/silver_transform/etl_ga_tb.py --year 2026
"""
import argparse
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

LAKE_ROOT = Path(__file__).resolve().parents[2]
TB_DIR    = LAKE_ROOT / "01_Bronze_Raw" / "tb_snapshots" / "ga"
SILVER    = LAKE_ROOT / "02_Silver_Cleaned"

# Month → posting-period number mapping from filename
MONTHS = ["01","02","03","04","05","06","07","08","09","10","11","12"]


def _read_tb(path: Path) -> pd.DataFrame:
    """Read a single GA TB Excel file → DataFrame of account-level rows only."""
    df = pd.read_excel(path, header=0)
    df.columns = [
        "fs_item","text","account","balance","prior","abs_diff","pct_diff",
        "alt","biz","coa","co","country","cur","curtype","fy","func",
        "grpacct","grpcoa","hier","id","id2","newpg","pctnum","postperiod","summary",
    ]
    # Keep only rows with a numeric account number (leaf rows)
    df = df[df["account"].notna()].copy()
    df["account"] = df["account"].astype(float).astype(int).astype(str).str.strip()
    df["balance"] = pd.to_numeric(df["balance"], errors="coerce").fillna(0.0)
    return df[["account", "text", "balance"]].copy()


def _sum(df: pd.DataFrame, *prefixes) -> float:
    """Sum balances for all accounts whose numbers start with any of the given prefixes."""
    mask = df["account"].str.startswith(tuple(prefixes))
    return float(df.loc[mask, "balance"].sum())


def _get(df: pd.DataFrame, account: str) -> float:
    """Get balance for a specific account number (0.0 if not found)."""
    row = df[df["account"] == account]
    return float(row["balance"].values[0]) if not row.empty else 0.0


def _process_month(year: int, mm: str) -> dict | None:
    """Load one month's TB → return a dict of KPIs, or None if file missing."""
    # New filename pattern: tb_{YYYYMM}.xlsx in tb_snapshots/ga/{year}/
    year_dir = TB_DIR / str(year)
    path = year_dir / f"tb_{year}{mm}.xlsx"
    if not path.exists():
        path = year_dir / f"tb_{year}{mm}.XLSX"
    if not path.exists():
        return None

    df = _read_tb(path)
    period = f"{year}-{mm}"

    # ── Cash & Cash Equivalents (111x) ─────────────────────────────────────
    cash_petty  = _get(df, "1111010")
    cash_scb1   = _get(df, "1112070")
    cash_bbl    = _get(df, "1112090")
    cash_scb2   = _get(df, "1112140")
    cash_total  = _sum(df, "111")

    # Other = total minus the main 4
    cash_other  = cash_total - cash_petty - cash_scb1 - cash_bbl - cash_scb2

    # ── Account Receivable Trade (1121xxx) ──────────────────────────────────
    ar_domestic  = _get(df, "1121010")
    ar_affiliate = _get(df, "1121030")
    ar_total     = ar_domestic + ar_affiliate

    # ── Inventory (113x) ────────────────────────────────────────────────────
    inv_rm        = _get(df, "1131010")
    inv_semi_fg   = _get(df, "1131020")
    inv_fg        = _get(df, "1131030")
    inv_provision = _get(df, "1139020")   # negative (allowance)
    inv_other     = _sum(df, "1132", "1133")
    inv_total     = _sum(df, "113")

    # ── Account Payable (212x) — balances are negative (credits) ────────────
    ap_affiliate = abs(_get(df, "2121030"))
    ap_domestic  = abs(_get(df, "2122010"))
    ap_employee  = abs(_get(df, "2122030"))
    ap_leasing   = abs(_get(df, "2122090"))
    ap_other     = abs(_sum(df, "2122")) - ap_domestic - ap_employee - ap_leasing
    ap_total     = abs(_sum(df, "212"))

    # ── Customer Deposits (2131xxx) ─────────────────────────────────────────
    cust_deposit = abs(_sum(df, "2131"))

    # ── Accruals (2141xxx / 2149xxx) ────────────────────────────────────────
    accrued_bonus = abs(_get(df, "2141050"))
    accrued_other = abs(_sum(df, "2141", "2149")) - accrued_bonus

    # ── Working Capital quick calc ───────────────────────────────────────────
    current_assets      = cash_total + ar_total + inv_total
    current_liabilities = ap_total + cust_deposit + abs(_sum(df, "2141", "2149"))
    net_working_capital = current_assets - current_liabilities

    return {
        "period":              period,
        # Cash
        "cash_petty":          cash_petty,
        "cash_bank_scb1":      cash_scb1,
        "cash_bank_bbl":       cash_bbl,
        "cash_bank_scb2":      cash_scb2,
        "cash_other":          cash_other,
        "cash_total":          cash_total,
        # AR Trade
        "ar_domestic":         ar_domestic,
        "ar_affiliate":        ar_affiliate,
        "ar_total":            ar_total,
        # Inventory
        "inv_rm":              inv_rm,
        "inv_semi_fg":         inv_semi_fg,
        "inv_fg":              inv_fg,
        "inv_other":           inv_other,
        "inv_provision":       inv_provision,   # negative
        "inv_total":           inv_total,
        # AP
        "ap_affiliate":        ap_affiliate,
        "ap_domestic":         ap_domestic,
        "ap_employee":         ap_employee,
        "ap_leasing":          ap_leasing,
        "ap_other":            max(ap_other, 0.0),
        "ap_total":            ap_total,
        # Customer deposits
        "cust_deposit":        cust_deposit,
        # Accruals
        "accrued_bonus":       accrued_bonus,
        "accrued_other":       max(accrued_other, 0.0),
        # Working capital
        "net_working_capital": net_working_capital,
    }


def run(year: int = 2026) -> int:
    """Process all available months for a year → parquet. Returns row count."""
    rows = []
    for mm in MONTHS:
        rec = _process_month(year, mm)
        if rec:
            rows.append(rec)
            print(f"  OK {rec['period']}  cash={rec['cash_total']:>15,.2f}  AR={rec['ar_total']:>14,.2f}  inv={rec['inv_total']:>14,.2f}  AP={rec['ap_total']:>14,.2f}")

    if not rows:
        print(f"[etl_ga_tb] No TB files found for year {year} in {TB_DIR}")
        return 0

    df = pd.DataFrame(rows)
    out = SILVER / f"ga_tb_{year}.parquet"
    df.to_parquet(out, index=False)
    print(f"\n[etl_ga_tb] Saved {len(df)} rows -> {out.name}")
    return len(df)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GA TB ETL")
    parser.add_argument("--year", type=int, default=2026, help="Fiscal year")
    args = parser.parse_args()
    print(f"[etl_ga_tb] Processing GA Trial Balance for year {args.year}")
    run(args.year)
