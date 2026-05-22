"""
create_cashflow.py — Gold Pipeline: Cash Flow Statement (Indirect Method)

ผลลัพธ์: 03_Gold_DataMarts/gold_cashflow.parquet
Schema:
  year, quarter, period_end, entity_type,
  section, section_label_th, section_label_en, section_order,
  line_key, line_label_th, line_label_en, line_order,
  amount, currency

Logic:
  1. สร้าง leadsheet ก่อน (หรืออ่านจาก gold_leadsheet.parquet ถ้ามีแล้ว)
  2. คำนวณ Net Income จาก P&L
  3. บวกกลับ non-cash items (depreciation, amortisation, employee benefits)
  4. คำนวณ Working Capital changes (BS current period vs prior period)
  5. Investing / Financing จาก GL movements

รัน: python -m 04_Data_Pipelines.gold_aggregation.create_cashflow --year 2025 --quarter Q1
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

LEADSHEET_FILE = os.path.join(GOLD_DIR, "gold_leadsheet.parquet")
OUT_FILE       = os.path.join(GOLD_DIR, "gold_cashflow.parquet")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

QUARTER_MONTHS = {
    "Q1": (1, 3,  "03-31"),
    "Q2": (1, 6,  "06-30"),
    "Q3": (1, 9,  "09-30"),
    "Q4": (1, 12, "12-31"),
    "FY": (1, 12, "12-31"),
}


def _load_bs_lines(year: int, quarter: str) -> pd.DataFrame:
    """Load BS line totals from gold_leadsheet for a given period."""
    if not os.path.exists(LEADSHEET_FILE):
        raise FileNotFoundError(
            f"gold_leadsheet.parquet not found. Run create_leadsheet.py --year {year} first."
        )
    df = pd.read_parquet(LEADSHEET_FILE)
    df = df[(df["year"] == year) & (df["quarter"] == quarter) & (df["statement"] == "BS")]
    return df.set_index("line_key")["amount_presented"].to_dict()


def _load_pl_total(year: int, quarter: str) -> float:
    """Net Income = Revenue + Other Inc - COGS - Selling - Admin - Finance."""
    if not os.path.exists(LEADSHEET_FILE):
        raise FileNotFoundError(
            f"gold_leadsheet.parquet not found. Run create_leadsheet.py --year {year} first."
        )
    df = pd.read_parquet(LEADSHEET_FILE)
    df = df[(df["year"] == year) & (df["quarter"] == quarter) & (df["statement"] == "PL")]
    total = df["amount_presented"].sum()
    return float(total)


def _get_gl_amount(accounts: list, prefixes: list,
                   year: int, month_from: int, month_to: int, con) -> float:
    """Sum Net_Amount for given accounts and/or prefixes from v_gl."""
    clauses = []
    params  = [year, month_from, month_to]
    if accounts:
        placeholders = ",".join(["?" for _ in accounts])
        clauses.append(f'CAST("G/L Account" AS VARCHAR) IN ({placeholders})')
        params.extend(accounts)
    if prefixes:
        for p in prefixes:
            clauses.append(f'CAST("G/L Account" AS VARCHAR) LIKE ?')
            params.append(f"{p}%")

    if not clauses:
        return 0.0

    where = " OR ".join(clauses)
    sql   = f"""
        SELECT COALESCE(SUM(Net_Amount), 0) AS total
        FROM v_gl
        WHERE CAST(Year AS INTEGER) = ?
          AND CAST(Month AS INTEGER) BETWEEN ? AND ?
          AND ({where})
    """
    result = con.execute(sql, params).fetchone()
    return float(result[0]) if result else 0.0


def run(year: int, quarter: str = "FY"):
    quarter = quarter.upper()
    if quarter not in QUARTER_MONTHS:
        raise ValueError(f"quarter must be one of {list(QUARTER_MONTHS.keys())}")

    month_from, month_to, end_suffix = QUARTER_MONTHS[quarter]
    period_end = f"{year}-{end_suffix}"

    log.info(f"Cash Flow  year={year}  quarter={quarter}  period={period_end}")

    cf_map = json.load(open(os.path.join(CFG_DIR, "mapping_cashflow.json"), encoding="utf-8"))
    lines  = cf_map["lines"]
    gl_acc = cf_map.get("gl_accounts", {})
    wc_map = cf_map.get("bs_working_capital", {})

    # ── 1. Load base data ──────────────────────────────────────────────────────
    bs_current  = _load_bs_lines(year, quarter)
    # Prior period = prior quarter / prior year FY
    prior_quarter = quarter
    prior_year    = year - 1
    try:
        bs_prior = _load_bs_lines(prior_year, "FY")
    except Exception:
        log.warning("No prior year BS found — working capital changes will be zero")
        bs_prior = {}

    net_income = _load_pl_total(year, quarter)
    log.info(f"  Net Income: {net_income:,.0f}")

    con = duckdb.connect(DUCK_DB, read_only=True)

    records = []
    structure = cf_map["structure"]

    def _add(line_key: str, amount: float):
        if line_key not in lines:
            return
        ld      = lines[line_key]
        section = ld["section"]
        sd      = structure.get(section, {})
        records.append({
            "year":             year,
            "quarter":          quarter,
            "period_end":       period_end,
            "entity_type":      "stat",
            "section":          section,
            "section_label_th": sd.get("label_th", section),
            "section_label_en": sd.get("label_en", section),
            "section_order":    sd.get("order", 99),
            "line_key":         line_key,
            "line_label_th":    ld.get("label_th", line_key),
            "line_label_en":    ld.get("label_en", line_key),
            "line_order":       ld.get("order", 999),
            "amount":           round(amount, 2),
            "currency":         "THB",
        })

    try:
        # ── 2. Net Income ──────────────────────────────────────────────────────
        _add("net_income", net_income)

        # ── 3. Non-cash adjustments (from GL) ─────────────────────────────────
        for key, cfg in gl_acc.items():
            if key not in lines:
                continue
            accts    = cfg.get("accounts", [])
            prefixes = cfg.get("prefixes", [])
            raw      = _get_gl_amount(accts, prefixes, year, month_from, month_to, con)
            # Depreciation/Amortisation: stored as positive debit → add back as positive
            # Gain on disposal: stored as negative (credit) → flip sign (presented as deduction)
            if key in ("less_gain_disposal",):
                amount = raw * -1   # negate: gain is negative in GL → present as deduction
            elif key in ("add_unrealized_fx",):
                amount = raw * -1   # unrealized FX gain (credit=neg) → flip
            else:
                amount = raw
            _add(key, amount)

        # ── 4. Working Capital changes (BS current - BS prior) ─────────────────
        for wc_key, wc_cfg in wc_map.items():
            if wc_key not in lines:
                continue
            bs_keys = wc_cfg.get("bs_lines", [])
            cur_total  = sum(bs_current.get(k, 0.0) for k in bs_keys)
            prior_total= sum(bs_prior.get(k, 0.0)   for k in bs_keys)
            change     = cur_total - prior_total

            section_type = lines[wc_key].get("section")
            # Assets: increase = cash outflow (negative for CF), decrease = inflow (positive)
            # Liabilities: increase = cash inflow (positive for CF), decrease = outflow
            if any(k in ("trade_ar","other_ar","allowance_ar","inventory","prepaid","accrued_income","other_ca","tax_asset_current") for k in bs_keys):
                amount = -change  # asset increase = cash out
            else:
                amount = change   # liability increase = cash in

            _add(wc_key, amount)

        # ── 5. Investing Activities ────────────────────────────────────────────
        for key in ("ppe_purchase", "auc_additions", "investment_change"):
            if key not in gl_acc:
                continue
            cfg    = gl_acc[key]
            accts  = cfg.get("accounts", [])
            prfxs  = cfg.get("prefixes", [])
            raw    = _get_gl_amount(accts, prfxs, year, month_from, month_to, con)
            # PPE/AUC: debit additions = positive in GL = cash outflow
            amount = -raw if raw > 0 else raw
            _add(key, amount)

        # Add proceeds from disposal (positive — captured via gain account proxy)
        _add("ppe_disposal", 0.0)   # placeholder: requires PPE register data

        # ── 6. Financing Activities ────────────────────────────────────────────
        for key in ("st_loan_proceeds", "st_loan_repayment", "lease_payment", "dividend_paid"):
            if key not in gl_acc:
                if key in ("st_loan_proceeds", "st_loan_repayment"):
                    # Derive from BS change in short-term borrowings
                    chg = (bs_current.get("st_borrowing", 0.0) -
                           bs_prior.get("st_borrowing", 0.0))
                    if chg >= 0:
                        _add("st_loan_proceeds", chg)
                    else:
                        _add("st_loan_repayment", chg)
                continue
            cfg    = gl_acc[key]
            accts  = cfg.get("accounts", [])
            prfxs  = cfg.get("prefixes", [])
            raw    = _get_gl_amount(accts, prfxs, year, month_from, month_to, con)
            # Lease / Dividend paid: credit entries = negative in GL → negate to show as outflow
            _add(key, raw)

    finally:
        con.close()

    df = pd.DataFrame(records).sort_values(["section_order", "line_order"])

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
    log.info(f"Saved {len(df)} CF lines → {OUT_FILE}")

    # Summary
    for sec in ["operating", "investing", "financing"]:
        sub = df[df["section"] == sec]["amount"].sum()
        log.info(f"  {sec:12s}: {sub:>15,.0f}")
    net_change = df["amount"].sum()
    log.info(f"  Net cash change: {net_change:>12,.0f}")

    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build gold_cashflow.parquet")
    parser.add_argument("--year",    type=int, required=True)
    parser.add_argument("--quarter", type=str, default="FY")
    args = parser.parse_args()
    run(args.year, args.quarter)
