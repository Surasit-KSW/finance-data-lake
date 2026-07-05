"""
ETL: Treasury Bank Balances (Daily)
=====================================
Source:  01_Bronze_Raw/treasury/amc_cashflow_*.xlsx  (sheet: '1.Daily Balance ')
Target:  02_Silver_Cleaned/treasury_banks_2026.parquet

Run: python 04_Data_Pipelines/silver_transform/etl_treasury_banks.py
"""
from pathlib import Path
from datetime import date
import pandas as pd

LAKE_ROOT   = Path(__file__).resolve().parents[2]
BRONZE      = LAKE_ROOT / "01_Bronze_Raw" / "treasury"
SILVER      = LAKE_ROOT / "02_Silver_Cleaned"
KNOWN_BANKS = ['TMB', 'KBANK', 'SCB', 'BBL', 'UOB', 'BAY']


def _latest(prefix: str) -> Path:
    files = sorted(BRONZE.glob(f"{prefix}*.xlsx"))
    if not files:
        raise FileNotFoundError(f"No {prefix}*.xlsx in {BRONZE}")
    return files[-1]


def _safe_float(val, default: float = 0.0) -> float:
    try:
        v = float(val)
        return v if v == v else default
    except (TypeError, ValueError):
        return default


def run():
    wb_path = _latest("amc_cashflow")
    as_of   = date.today()
    print(f"Source : {wb_path.name}")
    print(f"As-of  : {as_of}")

    try:
        df_raw = pd.read_excel(wb_path, sheet_name="1.Daily Balance ", header=None)
    except Exception as e:
        raise RuntimeError(f"Could not read '1.Daily Balance ' sheet: {e}")

    # Find header row containing bank names
    header_idx = None
    bank_cols  = {}
    for i, row in df_raw.iterrows():
        vals = [str(v).strip() for v in row if pd.notna(v)]
        hits = [b for b in KNOWN_BANKS if b in vals]
        if len(hits) >= 3:
            header_idx = i
            for j, cell in enumerate(row):
                if str(cell).strip() in KNOWN_BANKS:
                    bank_cols[str(cell).strip()] = j
            break

    if header_idx is None or not bank_cols:
        raise RuntimeError("Could not locate bank header row in '1.Daily Balance '")

    print(f"Header row: {header_idx}, banks: {list(bank_cols.keys())}")

    # Find opening balance row (first row after header with positive numbers)
    opening_row = None
    for i in range(header_idx + 1, min(header_idx + 6, len(df_raw))):
        row = df_raw.iloc[i]
        if any(isinstance(row.iloc[col], (int, float)) and row.iloc[col] > 0
               for col in bank_cols.values()):
            opening_row = i
            break

    if opening_row is None:
        raise RuntimeError("Could not locate opening balance row")

    print(f"Opening balance row: {opening_row}")

    rows = []
    for bank, col in bank_cols.items():
        rows.append({'date': as_of, 'bank': bank,
                     'balance_thb': _safe_float(df_raw.iloc[opening_row, col])})

    # Fill missing banks with zero
    found = {r['bank'] for r in rows}
    for b in KNOWN_BANKS:
        if b not in found:
            rows.append({'date': as_of, 'bank': b, 'balance_thb': 0.0})
            print(f"  WARNING: {b} not in sheet, set to 0")

    df = pd.DataFrame(rows)

    # Idempotent append
    SILVER.mkdir(exist_ok=True)
    out = SILVER / "treasury_banks_2026.parquet"
    if out.exists():
        existing = pd.read_parquet(out)
        existing['date'] = pd.to_datetime(existing['date'], errors='coerce').dt.date
        existing = existing[existing['date'] != as_of]
        df = pd.concat([existing, df], ignore_index=True)

    df.to_parquet(out, index=False)
    today = df[df['date'].astype(str) == str(as_of)]
    print(f"Wrote {len(today)} bank rows for {as_of} -> {out}")
    print(today[['bank', 'balance_thb']].to_string(index=False))


if __name__ == '__main__':
    run()
