"""
routers/treasury.py
===================
Treasury endpoints — /api/v1/treasury/...

Consumers: fintech-command-center (Finance > Treasury page)

Data sources (T1 — local only, never Neon):
  02_Silver_Cleaned/treasury_positions_2026.parquet
  02_Silver_Cleaned/treasury_banks_2026.parquet

Endpoints:
  GET /api/v1/treasury/all?asOf=YYYY-MM-DD
    Returns positions + banks + fx summary for Treasury page.
    Falls back gracefully if parquet files not yet created (returns usingMock=True).
"""
from pathlib import Path
from datetime import date
from fastapi import APIRouter, Query, HTTPException
import pandas as pd

router    = APIRouter(prefix="/api/v1/treasury", tags=["Treasury"])
LAKE_ROOT = Path(__file__).resolve().parents[2]
SILVER    = LAKE_ROOT / "02_Silver_Cleaned"

BANK_COLORS = {
    'TMB':   '#6366f1',
    'KBANK': '#10b981',
    'SCB':   '#3b82f6',
    'BBL':   '#f59e0b',
    'UOB':   '#8b5cf6',
    'BAY':   '#ec4899',
}


def _load_parquet(name: str) -> pd.DataFrame | None:
    """Load parquet, return None if missing (triggers usingMock fallback)."""
    path = SILVER / name
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    for col in ('date', 'start_date', 'maturity_date'):
        if col in df.columns:
            df[col] = df[col].astype(str).replace({'NaT': '', 'None': '', 'nan': ''})
    return df


def _latest_slice(df: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """Return rows for the latest available date <= as_of."""
    dates = pd.to_datetime(df['date'], errors='coerce').dt.date
    valid = dates[dates <= as_of]
    if valid.empty:
        return df.iloc[0:0]
    return df[dates == valid.max()].copy()


def _safe(val, default=None):
    if val is None:
        return default
    try:
        v = float(val)
        return default if (v != v) else v   # NaN check
    except (TypeError, ValueError):
        return default


def _days_until(d_str, today: date):
    if not d_str or str(d_str) in ('None', 'NaT', 'nan', ''):
        return None
    try:
        return (date.fromisoformat(str(d_str)) - today).days
    except ValueError:
        return None


@router.get("/all")
def treasury_all(asOf: str = Query(..., description="Snapshot date YYYY-MM-DD")):
    """
    Composite Treasury snapshot for the Treasury page.

    Returns positions (TR/PN) + bank balances + FX rate + summary KPIs.
    T1 data — served from local Silver parquet only, never from Neon.

    If parquet files are missing (ETL not yet run), returns usingMock=True
    so the frontend falls back to TREASURY_MOCK gracefully.
    """
    try:
        as_of_date = date.fromisoformat(asOf)
    except ValueError:
        raise HTTPException(status_code=400, detail="asOf must be YYYY-MM-DD")

    pos_df  = _load_parquet("treasury_positions_2026.parquet")
    bank_df = _load_parquet("treasury_banks_2026.parquet")

    if pos_df is None or bank_df is None:
        # ETL not yet run — signal frontend to use mock
        return {"usingMock": True}

    pos_df  = _latest_slice(pos_df,  as_of_date)
    bank_df = _latest_slice(bank_df, as_of_date)

    # ── Positions ─────────────────────────────────────────────────────────────
    positions = []
    for _, r in pos_df.iterrows():
        mat = r.get('maturity_date')
        mat_clean = str(mat) if mat and str(mat) not in ('None', 'NaT', 'nan', '') else None
        positions.append({
            'bank':          str(r.get('bank', '')),
            'product':       str(r.get('product', '')),
            'currency':      str(r.get('currency', 'THB')),
            'amount_orig':   _safe(r.get('amount_orig'), 0.0),
            'amount_thb':    _safe(r.get('amount_thb'), 0.0),
            'fx_rate':       _safe(r.get('fx_rate')),
            'start_date':    str(r.get('start_date')) if r.get('start_date') and str(r.get('start_date')) not in ('None', 'NaT', 'nan') else None,
            'maturity_date': mat_clean,
            'interest_rate': _safe(r.get('interest_rate')),
            'supplier':      r.get('supplier'),
            'rm_type':       r.get('rm_type'),
            'lc_no':         r.get('lc_no'),
        })

    # ── Banks ─────────────────────────────────────────────────────────────────
    banks = []
    for _, r in bank_df.iterrows():
        bname = str(r.get('bank', ''))
        banks.append({
            'bank':    bname,
            'balance': _safe(r.get('balance_thb'), 0.0),
            'color':   BANK_COLORS.get(bname, '#94a3b8'),
        })

    # ── Summary KPIs ──────────────────────────────────────────────────────────
    total_cash    = sum(b['balance'] for b in banks)
    usd_positions = [p for p in positions if p['currency'] == 'USD']
    total_usd     = sum(p['amount_orig'] for p in usd_positions)
    total_usd_thb = sum(p['amount_thb'] or 0 for p in usd_positions)

    maturity_pairs = [
        (_days_until(p['maturity_date'], as_of_date), p)
        for p in positions
        if _days_until(p['maturity_date'], as_of_date) is not None
        and _days_until(p['maturity_date'], as_of_date) >= 0
    ]
    maturity_pairs.sort(key=lambda x: x[0])

    next_days    = maturity_pairs[0][0] if maturity_pairs else None
    next_product = maturity_pairs[0][1]['product'] if maturity_pairs else None
    next_bank    = maturity_pairs[0][1]['bank']    if maturity_pairs else None

    usd_fx = next((p['fx_rate'] for p in usd_positions if p['fx_rate']), None)

    return {
        'asOf':      asOf,
        'positions': positions,
        'banks':     banks,
        'fx':        {'usd_thb': usd_fx, 'eur_thb': None},
        'summary': {
            'total_cash':            total_cash,
            'total_exposure_usd':    total_usd,
            'total_exposure_thb':    total_usd_thb,
            'days_to_next_maturity': next_days,
            'next_maturity_product': next_product,
            'next_maturity_bank':    next_bank,
        },
        # Backward compat (existing data_lake treasury endpoint provided these)
        'cash':      {'balance': total_cash, 'trend6m': []},
        'ar':        {'total': 0, 'overdue60': None, 'dso': None},
        'ap':        {'total': 0, 'due30d': None,    'dpo': None},
        'nwcRunway': {'netWorkingCapital': 0, 'monthlyBurnRate': 0, 'runwayMonths': None},
    }
