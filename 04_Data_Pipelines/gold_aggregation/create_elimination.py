"""
create_elimination.py — Gold Pipeline: Consolidation Elimination Entries

ผลลัพธ์: 03_Gold_DataMarts/gold_elimination.parquet
Schema:
  year, quarter, period_end,
  elim_type, elim_label_th, elim_label_en, elim_order,
  account, account_name,
  dr_amount, cr_amount, net_amount,
  note, currency

Sources:
  - gold_leadsheet.parquet (BS line totals for IC AR/AP)
  - v_gl (IC revenue/expense transactions)
  - Requires: subsidiary GL data (multi-entity) — returns parent-only IC for now

รัน: python -m 04_Data_Pipelines.gold_aggregation.create_elimination --year 2025 --quarter Q1
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

DUCK_DB   = os.path.join(PROJECT_ROOT, "finance_lake.duckdb")
GOLD_DIR  = os.path.join(PROJECT_ROOT, "03_Gold_DataMarts")
CFG_DIR   = os.path.join(PROJECT_ROOT, "config")

LEADSHEET_FILE = os.path.join(GOLD_DIR, "gold_leadsheet.parquet")
OUT_FILE       = os.path.join(GOLD_DIR, "gold_elimination.parquet")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

QUARTER_MONTHS = {
    "Q1": (1, 3,  "03-31"),
    "Q2": (1, 6,  "06-30"),
    "Q3": (1, 9,  "09-30"),
    "Q4": (1, 12, "12-31"),
    "FY": (1, 12, "12-31"),
}


def _get_account_balance(accounts: list, year: int, month_from: int, month_to: int,
                          cumulative: bool, con) -> pd.DataFrame:
    """Get balance for specific GL accounts."""
    if not accounts:
        return pd.DataFrame(columns=["account", "account_name", "balance"])

    placeholders = ",".join(["?" for _ in accounts])
    if cumulative:
        # Balance sheet: cumulative from beginning
        sql = f"""
            SELECT CAST("G/L Account" AS VARCHAR) AS account,
                   "G/L Account: Long Text"       AS account_name,
                   SUM(Net_Amount)                AS balance
            FROM v_gl
            WHERE CAST("G/L Account" AS VARCHAR) IN ({placeholders})
            GROUP BY "G/L Account", "G/L Account: Long Text"
        """
        params = accounts
    else:
        # P&L: period only
        sql = f"""
            SELECT CAST("G/L Account" AS VARCHAR) AS account,
                   "G/L Account: Long Text"       AS account_name,
                   SUM(Net_Amount)                AS balance
            FROM v_gl
            WHERE CAST(Year AS INTEGER) = ?
              AND CAST(Month AS INTEGER) BETWEEN ? AND ?
              AND CAST("G/L Account" AS VARCHAR) IN ({placeholders})
            GROUP BY "G/L Account", "G/L Account: Long Text"
        """
        params = [year, month_from, month_to] + accounts

    df = con.execute(sql, params).fetchdf()
    df["account"] = df["account"].astype(str)
    return df


def run(year: int, quarter: str = "FY"):
    quarter = quarter.upper()
    if quarter not in QUARTER_MONTHS:
        raise ValueError(f"quarter must be one of {list(QUARTER_MONTHS.keys())}")

    month_from, month_to, end_suffix = QUARTER_MONTHS[quarter]
    period_end = f"{year}-{end_suffix}"

    log.info(f"Elimination  year={year}  quarter={quarter}  period={period_end}")

    rp_map   = json.load(open(os.path.join(CFG_DIR, "mapping_related_party.json"), encoding="utf-8"))
    elim_def = rp_map["elimination_types"]
    ic_bal   = rp_map["ic_balance_accounts"]
    ic_txn   = rp_map["ic_transaction_accounts"]

    con = duckdb.connect(DUCK_DB, read_only=True)
    records = []

    try:
        # ── 1. IC AR / AP elimination ─────────────────────────────────────────
        elim = elim_def["ic_ar_ap"]
        ar_accounts = ic_bal["ar_affiliate"]["accounts"] + ic_bal["ar_related"]["accounts"]
        ap_accounts = ic_bal["ap_affiliate"]["accounts"] + ic_bal["ap_related"]["accounts"]

        ar_df = _get_account_balance(ar_accounts, year, month_from, month_to, True, con)
        ap_df = _get_account_balance(ap_accounts, year, month_from, month_to, True, con)

        for _, row in ar_df.iterrows():
            amt = float(row["balance"])
            if abs(amt) < 1:
                continue
            records.append({
                "elim_type":      "ic_ar_ap",
                "elim_label_th":  elim["label_th"],
                "elim_label_en":  elim["label_en"],
                "elim_order":     elim["order"],
                "account":        row["account"],
                "account_name":   row["account_name"],
                "dr_amount":      0.0,
                "cr_amount":      abs(amt),      # Credit AR (eliminate asset)
                "net_amount":     -abs(amt),
                "note":           "Eliminate IC Receivable",
                "data_source":    "parent_gl_only",
            })

        for _, row in ap_df.iterrows():
            amt = float(row["balance"])
            if abs(amt) < 1:
                continue
            records.append({
                "elim_type":      "ic_ar_ap",
                "elim_label_th":  elim["label_th"],
                "elim_label_en":  elim["label_en"],
                "elim_order":     elim["order"],
                "account":        row["account"],
                "account_name":   row["account_name"],
                "dr_amount":      abs(amt),       # Debit AP (eliminate liability)
                "cr_amount":      0.0,
                "net_amount":     abs(amt),
                "note":           "Eliminate IC Payable",
                "data_source":    "parent_gl_only",
            })

        # ── 2. IC Revenue / COGS elimination ─────────────────────────────────
        elim = elim_def["ic_revenue_cogs"]
        rev_accounts = (ic_txn["sales_affiliate"]["accounts"] +
                        ic_txn["sales_related"]["accounts"])
        rev_df = _get_account_balance(rev_accounts, year, month_from, month_to, False, con)

        for _, row in rev_df.iterrows():
            amt = float(row["balance"])
            if abs(amt) < 1:
                continue
            # SAP: revenue = credit (negative) → present as positive flip
            rev_presented = abs(amt)
            records.append({
                "elim_type":      "ic_revenue_cogs",
                "elim_label_th":  elim["label_th"],
                "elim_label_en":  elim["label_en"],
                "elim_order":     elim["order"],
                "account":        row["account"],
                "account_name":   row["account_name"],
                "dr_amount":      rev_presented,  # Debit revenue (eliminate)
                "cr_amount":      0.0,
                "net_amount":     -rev_presented,
                "note":           "Eliminate IC Revenue (COGS match required)",
                "data_source":    "parent_gl_only",
            })

        # ── 3. IC Dividend elimination ────────────────────────────────────────
        elim     = elim_def["ic_dividend"]
        div_accs = ic_txn["dividend_income"]["accounts"]
        div_pay  = ic_txn["dividend_payable"]["accounts"]

        div_inc_df = _get_account_balance(div_accs, year, month_from, month_to, False, con)
        div_pay_df = _get_account_balance(div_pay,  year, month_from, month_to, False, con)

        for _, row in div_inc_df.iterrows():
            amt = float(row["balance"])
            if abs(amt) < 1:
                continue
            records.append({
                "elim_type":      "ic_dividend",
                "elim_label_th":  elim["label_th"],
                "elim_label_en":  elim["label_en"],
                "elim_order":     elim["order"],
                "account":        row["account"],
                "account_name":   row["account_name"],
                "dr_amount":      abs(amt),
                "cr_amount":      0.0,
                "net_amount":     abs(amt),
                "note":           "Eliminate Dividend Income",
                "data_source":    "parent_gl_only",
            })

        for _, row in div_pay_df.iterrows():
            amt = float(row["balance"])
            if abs(amt) < 1:
                continue
            records.append({
                "elim_type":      "ic_dividend",
                "elim_label_th":  elim["label_th"],
                "elim_label_en":  elim["label_en"],
                "elim_order":     elim["order"],
                "account":        row["account"],
                "account_name":   row["account_name"],
                "dr_amount":      0.0,
                "cr_amount":      abs(amt),
                "net_amount":     -abs(amt),
                "note":           "Eliminate Dividend Payable",
                "data_source":    "parent_gl_only",
            })

        # ── 4. Investment vs Equity (placeholder — needs subsidiary data) ─────
        records.append({
            "elim_type":      "investment_equity",
            "elim_label_th":  elim_def["investment_equity"]["label_th"],
            "elim_label_en":  elim_def["investment_equity"]["label_en"],
            "elim_order":     elim_def["investment_equity"]["order"],
            "account":        "1211030",
            "account_name":   "Equity Investments",
            "dr_amount":      0.0,
            "cr_amount":      0.0,
            "net_amount":     0.0,
            "note":           "Requires subsidiary equity data — pending",
            "data_source":    "pending",
        })

    finally:
        con.close()

    df = pd.DataFrame(records)
    df["year"]       = year
    df["quarter"]    = quarter
    df["period_end"] = period_end
    df["currency"]   = "THB"

    os.makedirs(GOLD_DIR, exist_ok=True)

    if os.path.exists(OUT_FILE):
        existing = pd.read_parquet(OUT_FILE)
        existing = existing[~(
            (existing["year"] == year) & (existing["quarter"] == quarter)
        )]
        final = pd.concat([existing, df], ignore_index=True)
    else:
        final = df

    final.to_parquet(OUT_FILE, index=False)
    log.info(f"Saved {len(df)} elimination entries → {OUT_FILE}")

    for et in df["elim_type"].unique():
        sub = df[df["elim_type"] == et]
        log.info(f"  {et:25s}: {len(sub):3d} entries")

    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build gold_elimination.parquet")
    parser.add_argument("--year",    type=int, required=True)
    parser.add_argument("--quarter", type=str, default="FY")
    args = parser.parse_args()
    run(args.year, args.quarter)
