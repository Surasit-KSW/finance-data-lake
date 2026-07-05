"""
ETL: Treasury Positions
=======================
Source:  01_Bronze_Raw/treasury/control_lc_tr_*.xlsx
Target:  02_Silver_Cleaned/treasury_positions_2026.parquet

Extracts TR summary per bank, PN details, and FX rate.

Run: python 04_Data_Pipelines/silver_transform/etl_treasury_positions.py
"""
from pathlib import Path
from datetime import date
import pandas as pd

LAKE_ROOT = Path(__file__).resolve().parents[2]
BRONZE    = LAKE_ROOT / "01_Bronze_Raw" / "treasury"
SILVER    = LAKE_ROOT / "02_Silver_Cleaned"


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


def get_fx_rate(wb_path: Path) -> float:
    try:
        df = pd.read_excel(wb_path, sheet_name="3.Control TR ", header=None, nrows=5)
        for _, row in df.iterrows():
            for j, cell in enumerate(row):
                if str(cell).strip() in ('USD/THB ', 'USD/THB'):
                    rate = _safe_float(row.iloc[j + 1] if j + 1 < len(row) else None)
                    if rate > 0:
                        return rate
    except Exception as e:
        print(f"WARNING: Could not read FX rate: {e}")
    return 33.22


def etl_tr(wb_path: Path, as_of: date, fx_rate: float) -> pd.DataFrame:
    try:
        df = pd.read_excel(wb_path, sheet_name="3.Control TR ", header=None)
    except Exception as e:
        print(f"WARNING: Could not read Control TR sheet: {e}")
        return pd.DataFrame()

    rows = []
    header_idx = None
    for i, row in df.iterrows():
        if str(row.iloc[0]).strip() == 'BANK':
            header_idx = i
            break
    if header_idx is None:
        print("WARNING: Could not find BANK header row")
        return pd.DataFrame()

    rate_map = {}
    for i in range(header_idx + 1, min(header_idx + 10, len(df))):
        if len(df.columns) > 16:
            bank_cell = str(df.iloc[i, 15]).strip()
            rate_cell = df.iloc[i, 16]
            if bank_cell and bank_cell not in ('nan', 'None', ''):
                rate_map[bank_cell] = _safe_float(rate_cell)

    for i in range(header_idx + 1, min(header_idx + 10, len(df))):
        row = df.iloc[i]
        if pd.isna(row.iloc[0]):
            break
        bank = str(row.iloc[0]).strip()
        if not bank or bank in ('nan', 'None', '') or bank.startswith('TR'):
            continue

        tr_usd = _safe_float(row.iloc[1])
        tr_eur = _safe_float(row.iloc[2])
        tr_thb = _safe_float(row.iloc[3])
        rate   = rate_map.get(bank)

        if tr_usd > 0:
            rows.append({'date': as_of, 'bank': bank, 'product': 'TR', 'currency': 'USD',
                         'amount_orig': tr_usd, 'amount_thb': round(tr_usd * fx_rate, 2),
                         'fx_rate': fx_rate, 'interest_rate': rate,
                         'start_date': None, 'maturity_date': None,
                         'supplier': None, 'rm_type': None, 'lc_no': None})
        if tr_eur > 0:
            rows.append({'date': as_of, 'bank': bank, 'product': 'TR', 'currency': 'EUR',
                         'amount_orig': tr_eur, 'amount_thb': None,
                         'fx_rate': None, 'interest_rate': rate,
                         'start_date': None, 'maturity_date': None,
                         'supplier': None, 'rm_type': None, 'lc_no': None})
        if tr_thb > 0:
            rows.append({'date': as_of, 'bank': bank, 'product': 'TR', 'currency': 'THB',
                         'amount_orig': tr_thb, 'amount_thb': tr_thb,
                         'fx_rate': None, 'interest_rate': rate,
                         'start_date': None, 'maturity_date': None,
                         'supplier': None, 'rm_type': None, 'lc_no': None})
    return pd.DataFrame(rows)


def etl_pn(wb_path: Path, as_of: date) -> pd.DataFrame:
    try:
        df = pd.read_excel(wb_path, sheet_name="Control PN", header=None)
    except Exception as e:
        print(f"WARNING: Could not read Control PN sheet: {e}")
        return pd.DataFrame()

    rows = []
    for _, row in df.iterrows():
        try:
            int(float(str(row.iloc[0])))
        except (TypeError, ValueError):
            continue

        contract_no = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else None
        start_dt    = pd.to_datetime(row.iloc[4], errors='coerce')
        mat_dt      = pd.to_datetime(row.iloc[5], errors='coerce')
        rate        = _safe_float(row.iloc[6]) if pd.notna(row.iloc[6]) else None
        amount      = _safe_float(row.iloc[7])

        if amount <= 0:
            continue

        rows.append({'date': as_of, 'bank': 'SCB', 'product': 'PN', 'currency': 'THB',
                     'amount_orig': amount, 'amount_thb': amount,
                     'fx_rate': None, 'interest_rate': rate,
                     'start_date': start_dt.date() if not pd.isna(start_dt) else None,
                     'maturity_date': mat_dt.date() if not pd.isna(mat_dt) else None,
                     'supplier': None, 'rm_type': None, 'lc_no': contract_no})
    return pd.DataFrame(rows)


def run():
    wb_path = _latest("control_lc_tr")
    as_of   = date.today()
    fx      = get_fx_rate(wb_path)
    print(f"Source : {wb_path.name}")
    print(f"As-of  : {as_of}  |  USD/THB = {fx}")

    df_tr = etl_tr(wb_path, as_of, fx)
    df_pn = etl_pn(wb_path, as_of)
    df    = pd.concat([df_tr, df_pn], ignore_index=True)

    if df.empty:
        print("WARNING: No data extracted")
        return

    for col in ('start_date', 'maturity_date'):
        df[col] = pd.to_datetime(df[col], errors='coerce').dt.date

    SILVER.mkdir(exist_ok=True)
    out = SILVER / "treasury_positions_2026.parquet"
    df.to_parquet(out, index=False)
    print(f"Wrote {len(df)} rows -> {out}")
    print(df[['bank', 'product', 'currency', 'amount_thb', 'maturity_date']].to_string())


if __name__ == '__main__':
    run()
