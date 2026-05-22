"""
create_related_party.py — Gold Pipeline: Related Party Transactions & Balances

ผลลัพธ์: 03_Gold_DataMarts/gold_related_party.parquet
Schema:
  year, quarter, period_end,
  category_key, category_label_th, category_label_en,
  account, account_name,
  amount, currency,
  data_type (transaction | balance)

รัน: python -m 04_Data_Pipelines.gold_aggregation.create_related_party --year 2025 --quarter Q1
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
CFG_DIR   = os.path.join(PROJECT_ROOT, "08_Config")

OUT_FILE  = os.path.join(GOLD_DIR, "gold_related_party.parquet")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

QUARTER_MONTHS = {
    "Q1": (1, 3,  "03-31"),
    "Q2": (1, 6,  "06-30"),
    "Q3": (1, 9,  "09-30"),
    "Q4": (1, 12, "12-31"),
    "FY": (1, 12, "12-31"),
}

# Balance sheet categories (cumulative) vs P&L categories (period)
BALANCE_CATEGORIES = {"ar_from_related", "ap_to_related", "shareholder_loan"}


def run(year: int, quarter: str = "FY"):
    quarter = quarter.upper()
    if quarter not in QUARTER_MONTHS:
        raise ValueError(f"quarter must be one of {list(QUARTER_MONTHS.keys())}")

    month_from, month_to, end_suffix = QUARTER_MONTHS[quarter]
    period_end = f"{year}-{end_suffix}"

    log.info(f"Related Party  year={year}  quarter={quarter}  period={period_end}")

    rp_map = json.load(open(os.path.join(CFG_DIR, "mapping_related_party.json"), encoding="utf-8"))
    categories = rp_map["related_party_disclosure"]["categories"]

    con = duckdb.connect(DUCK_DB, read_only=True)
    records = []

    try:
        for cat in categories:
            key        = cat["key"]
            accounts   = cat["accounts"]
            label_th   = cat["label_th"]
            label_en   = cat["label_en"]
            is_balance = key in BALANCE_CATEGORIES

            if not accounts:
                continue

            placeholders = ",".join(["?" for _ in accounts])

            if is_balance:
                # Cumulative balance (BS)
                sql = f"""
                    SELECT CAST("G/L Account" AS VARCHAR) AS account,
                           "G/L Account: Long Text"       AS account_name,
                           SUM(Net_Amount)                AS amount
                    FROM v_gl
                    WHERE CAST("G/L Account" AS VARCHAR) IN ({placeholders})
                    GROUP BY "G/L Account", "G/L Account: Long Text"
                """
                params = accounts
                data_type = "balance"
            else:
                # Period transactions (P&L / IC transactions)
                sql = f"""
                    SELECT CAST("G/L Account" AS VARCHAR) AS account,
                           "G/L Account: Long Text"       AS account_name,
                           SUM(Net_Amount)                AS amount
                    FROM v_gl
                    WHERE CAST(Year AS INTEGER) = ?
                      AND CAST(Month AS INTEGER) BETWEEN ? AND ?
                      AND CAST("G/L Account" AS VARCHAR) IN ({placeholders})
                    GROUP BY "G/L Account", "G/L Account: Long Text"
                """
                params = [year, month_from, month_to] + accounts
                data_type = "transaction"

            df = con.execute(sql, params).fetchdf()
            df["account"] = df["account"].astype(str)

            for _, row in df.iterrows():
                raw_amount = float(row["amount"])
                if abs(raw_amount) < 1:
                    continue

                # Flip sign for revenue/balance presentation
                # Revenue accounts: SAP credit = negative → flip to positive
                # AR balance: debit = positive (keep)
                # AP balance: credit = negative → flip to positive
                if key in ("sales_to_related", "dividend_received"):
                    presented = abs(raw_amount)
                elif key in ("ap_to_related",):
                    presented = abs(raw_amount)
                else:
                    presented = raw_amount

                records.append({
                    "year":             year,
                    "quarter":          quarter,
                    "period_end":       period_end,
                    "category_key":     key,
                    "category_label_th": label_th,
                    "category_label_en": label_en,
                    "account":          row["account"],
                    "account_name":     row["account_name"],
                    "amount_raw":       raw_amount,
                    "amount":           round(presented, 2),
                    "data_type":        data_type,
                    "currency":         "THB",
                })

    finally:
        con.close()

    df = pd.DataFrame(records) if records else pd.DataFrame(columns=[
        "year","quarter","period_end","category_key","category_label_th",
        "category_label_en","account","account_name","amount_raw","amount",
        "data_type","currency",
    ])

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
    log.info(f"Saved {len(df)} related-party entries → {OUT_FILE}")

    for cat in df["category_key"].unique() if len(df) > 0 else []:
        sub = df[df["category_key"] == cat]["amount"].sum()
        log.info(f"  {cat:30s}: {sub:>15,.0f}")

    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build gold_related_party.parquet")
    parser.add_argument("--year",    type=int, required=True)
    parser.add_argument("--quarter", type=str, default="FY")
    args = parser.parse_args()
    run(args.year, args.quarter)
