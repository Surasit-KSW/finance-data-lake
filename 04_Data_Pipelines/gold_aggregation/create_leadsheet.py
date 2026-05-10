"""
create_leadsheet.py — Gold Pipeline: Trial Balance → Leadsheet (งบเดี่ยว / งบรวม)

ผลลัพธ์: 03_Gold_DataMarts/gold_leadsheet.parquet
Schema:
  year, quarter, period_end, entity_type (stat|conso),
  section, section_label_th, section_label_en, section_order,
  line_key, line_label_th, line_label_en, line_order,
  gl_account, account_name,
  amount_raw, amount_presented, currency

รัน: python -m 04_Data_Pipelines.gold_aggregation.create_leadsheet --year 2025 --quarter Q1
"""
import os
import sys
import json
import argparse
import logging
from datetime import date

import duckdb
import pandas as pd

# ── paths ──────────────────────────────────────────────────────────────────────
_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))

DUCK_DB   = os.path.join(PROJECT_ROOT, "finance_lake.duckdb")
GOLD_DIR  = os.path.join(PROJECT_ROOT, "03_Gold_DataMarts")
CFG_DIR   = os.path.join(PROJECT_ROOT, "config")

OUT_FILE  = os.path.join(GOLD_DIR, "gold_leadsheet.parquet")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ── helpers ────────────────────────────────────────────────────────────────────
def _load_mapping():
    bs_map = json.load(open(os.path.join(CFG_DIR, "mapping_bs.json"), encoding="utf-8"))
    pl_map = json.load(open(os.path.join(CFG_DIR, "mapping_pl.json"), encoding="utf-8"))
    return bs_map, pl_map


def _resolve_line(account_str: str, mapping: dict) -> str | None:
    """Return line_key for a given GL account string.
    New format uses account_map (exact match). Falls back to prefix_map for legacy configs.
    """
    # 1. Exact account map (new format from template)
    acct_map = mapping.get("account_map", {})
    if account_str in acct_map:
        return acct_map[account_str]
    # 2. Legacy prefix_map fallback
    prefix_map = mapping.get("prefix_map", {})
    if prefix_map:
        p4 = account_str[:4]
        if p4 in prefix_map:
            return prefix_map[p4]
        p2 = account_str[:2]
        if p2 in prefix_map:
            return prefix_map[p2]
    return None


def _build_account_df(year: int, month_from: int, month_to: int, con) -> pd.DataFrame:
    """Return GL balances by account split into BS (cumulative) and PL (period only).

    BS accounts (1xxx, 2xxx, 3xxx): sum ALL transactions up to period end
    PL accounts (4xxx-9xxx):        sum only transactions in the period (YTD)
    """
    # BS — cumulative balance up to period end (all years ≤ year, capped at month_to for current year)
    bs_df = con.execute("""
        SELECT
            CAST("G/L Account" AS VARCHAR)   AS account,
            "G/L Account: Long Text"         AS account_name,
            SUM(Net_Amount)                   AS amount_raw
        FROM v_gl
        WHERE LEFT(CAST("G/L Account" AS VARCHAR), 1) IN ('1', '2', '3')
          AND (
              CAST(Year AS INTEGER) < ?
              OR (CAST(Year AS INTEGER) = ? AND CAST(Month AS INTEGER) <= ?)
          )
        GROUP BY "G/L Account", "G/L Account: Long Text"
        ORDER BY "G/L Account"
    """, [year, year, month_to]).fetchdf()

    # PL — period movements only (YTD: month_from to month_to of the year)
    pl_df = con.execute("""
        SELECT
            CAST("G/L Account" AS VARCHAR)   AS account,
            "G/L Account: Long Text"         AS account_name,
            SUM(Net_Amount)                   AS amount_raw
        FROM v_gl
        WHERE LEFT(CAST("G/L Account" AS VARCHAR), 1) NOT IN ('1', '2', '3')
          AND CAST(Year AS INTEGER) = ?
          AND CAST(Month AS INTEGER) BETWEEN ? AND ?
        GROUP BY "G/L Account", "G/L Account: Long Text"
        ORDER BY "G/L Account"
    """, [year, month_from, month_to]).fetchdf()

    df = pd.concat([bs_df, pl_df], ignore_index=True)
    df["account"] = df["account"].astype(str)
    return df


def _map_to_lines(df: pd.DataFrame, bs_map: dict, pl_map: dict,
                  year: int, quarter: str, period_end: str) -> pd.DataFrame:
    """Assign each GL account to its FS line and compute presented amount."""
    records = []

    for _, row in df.iterrows():
        acct    = row["account"]
        raw_amt = float(row["amount_raw"])

        # Try BS first, then PL
        for mapping, stmt_type in [(bs_map, "BS"), (pl_map, "PL")]:
            line_key = _resolve_line(acct, mapping)
            if line_key is None:
                continue

            lines = mapping["lines"]
            if line_key not in lines:
                continue

            line_def  = lines[line_key]
            structure = mapping["structure"]
            section   = line_def["section"]
            sec_def   = structure.get(section, {})

            # Sign adjustment
            if stmt_type == "BS":
                sign     = line_def.get("sign", 1)
                amt_pres = raw_amt * sign
            else:
                flip     = line_def.get("flip_sign", False)
                amt_pres = raw_amt * (-1 if flip else 1)

            records.append({
                "year":             year,
                "quarter":          quarter,
                "period_end":       period_end,
                "entity_type":      "stat",
                "statement":        stmt_type,
                "section":          section,
                "section_label_th": sec_def.get("label_th", section),
                "section_label_en": sec_def.get("label_en", section),
                "section_order":    sec_def.get("order", 99),
                "line_key":         line_key,
                "line_label_th":    line_def.get("label_th", line_key),
                "line_label_en":    line_def.get("label_en", line_key),
                "line_order":       line_def.get("order", 999),
                "gl_account":       acct,
                "account_name":     row["account_name"],
                "amount_raw":       raw_amt,
                "amount_presented": amt_pres,
                "currency":         "THB",
            })
            break  # account mapped — stop trying

    result = pd.DataFrame(records)
    return result


def _summarise_to_lines(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate to line-item level (sum across GL accounts)."""
    return (
        df.groupby([
            "year", "quarter", "period_end", "entity_type", "statement",
            "section", "section_label_th", "section_label_en", "section_order",
            "line_key", "line_label_th", "line_label_en", "line_order",
            "currency",
        ], as_index=False)
        .agg(amount_presented=("amount_presented", "sum"))
        .sort_values(["statement", "section_order", "line_order"])
    )


# ── quarter helpers ────────────────────────────────────────────────────────────
QUARTER_MONTHS = {
    "Q1": (1, 3,  "03-31"),
    "Q2": (1, 6,  "06-30"),
    "Q3": (1, 9,  "09-30"),
    "Q4": (1, 12, "12-31"),
    "FY": (1, 12, "12-31"),
}


# ── main ───────────────────────────────────────────────────────────────────────
def run(year: int, quarter: str = "FY"):
    quarter = quarter.upper()
    if quarter not in QUARTER_MONTHS:
        raise ValueError(f"quarter must be one of {list(QUARTER_MONTHS.keys())}")

    month_from, month_to, end_suffix = QUARTER_MONTHS[quarter]
    period_end = f"{year}-{end_suffix}"

    log.info(f"Leadsheet  year={year}  quarter={quarter}  period={period_end}")

    bs_map, pl_map = _load_mapping()

    con = duckdb.connect(DUCK_DB, read_only=True)
    try:
        acct_df = _build_account_df(year, month_from, month_to, con)
        log.info(f"GL accounts loaded: {len(acct_df)} unique accounts")
    finally:
        con.close()

    detail_df = _map_to_lines(acct_df, bs_map, pl_map, year, quarter, period_end)
    unmapped  = acct_df[~acct_df["account"].isin(detail_df["gl_account"])]["account"].tolist()
    if unmapped:
        log.warning(f"Unmapped accounts ({len(unmapped)}): {unmapped[:20]}")

    summary_df = _summarise_to_lines(detail_df)

    os.makedirs(GOLD_DIR, exist_ok=True)

    # Append or replace for this year/quarter
    if os.path.exists(OUT_FILE):
        existing = pd.read_parquet(OUT_FILE)
        existing = existing[~(
            (existing["year"] == year) & (existing["quarter"] == quarter)
        )]
        final = pd.concat([existing, summary_df], ignore_index=True)
    else:
        final = summary_df

    final.to_parquet(OUT_FILE, index=False)
    log.info(f"Saved {len(summary_df)} line-items → {OUT_FILE}")

    # Quick summary print
    for stmt in ["BS", "PL"]:
        sub = summary_df[summary_df["statement"] == stmt]
        log.info(f"  {stmt}: {len(sub)} lines  total={sub['amount_presented'].sum():,.0f}")

    return summary_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build gold_leadsheet.parquet")
    parser.add_argument("--year",    type=int, required=True)
    parser.add_argument("--quarter", type=str, default="FY",
                        help="Q1 | Q2 | Q3 | Q4 | FY  (default: FY = full year cumulative)")
    args = parser.parse_args()
    run(args.year, args.quarter)
