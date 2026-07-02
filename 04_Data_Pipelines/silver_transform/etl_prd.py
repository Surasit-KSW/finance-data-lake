"""
etl_prd.py — Bronze production_orders → Silver: Production Order Detail

อ่านไฟล์ prd_{YYYYMM}.xlsx จาก 01_Bronze_Raw/production_orders/amc/{plant}/{year}/
Output: 02_Silver_Cleaned/master_prd_{year}.parquet

โครงสร้างผลลัพธ์ per production order:
  Year, Month, Plant, Process, Work Center, Order, Combined Order
  gi_qty_kg, gi_amount   → DM consumed (Actual GI)
  gr_qty_kg, gr_amount   → FG output   (Actual GR)
  scrap_qty_kg, scrap_amount
  dm_amount              → = gi_amount  (alias)
  cc_direct_amount       → D101 + D102
  cc_indirect_amount     → I101 ... I111
  cc_amount              → cc_direct + cc_indirect
  total_cost             → dm_amount + cc_amount

Process mapping (Work Center → Process):
  slit : SL02, SL03, SL09, SL06, SL10, SL11
  form : PL*, FF*, CC*
  cr_pk: CR01+PK01  (Plant 1300 — Pickling & Cold Roll → CRC)
  galv : GL01       (Plant 1300 — Galvanizing → GIC)
  pack : CP01
  rework: RW01

รัน: python 04_Data_Pipelines/silver_transform/etl_prd.py
     python 04_Data_Pipelines/silver_transform/etl_prd.py --year 2026
"""
import os, sys, re, glob, argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
BRONZE       = os.path.join(PROJECT_ROOT, '01_Bronze_Raw', 'production_orders', 'amc')
SILVER       = os.path.join(PROJECT_ROOT, '02_Silver_Cleaned')

# ─── Process mapping ─────────────────────────────────────────────────────────
def _map_process(wc: str) -> str:
    """Map Work Center code → process label."""
    wc = str(wc).strip().upper()
    if any(wc.startswith(s) for s in ('SL',)):
        return 'slit'
    if any(wc.startswith(s) for s in ('PL', 'FF', 'CC')):
        return 'form'
    if 'CR' in wc or 'PK' in wc:
        return 'cr_pk'
    if wc.startswith('GL'):
        return 'galv'
    if wc.startswith('CP'):
        return 'pack'
    if wc.startswith('RW'):
        return 'rework'
    return 'other'

# ─── Amount cleaner ───────────────────────────────────────────────────────────
def _to_float(series: pd.Series) -> pd.Series:
    """Convert SAP amount strings (with comma + trailing minus) to float."""
    s = series.astype(str).str.strip()
    s = s.str.replace(',', '', regex=False)
    # trailing minus: "1234-" → -1234
    mask = s.str.endswith('-')
    s = s.str.rstrip('-')
    result = pd.to_numeric(s, errors='coerce').fillna(0)
    result = result.where(~mask, -result)
    return result

# ─── Parse one file ───────────────────────────────────────────────────────────
def _parse_file(path: str) -> pd.DataFrame | None:
    fname = os.path.basename(path)
    m = re.match(r'prd_(\d{4})(\d{2})\.xlsx', fname, re.IGNORECASE)
    if not m:
        print(f'  ⏭️  skip (filename mismatch): {fname}')
        return None

    year  = int(m.group(1))
    month = int(m.group(2))
    # Plant is derived from parent directory name (e.g. production_orders/amc/1100/2026/)
    plant = os.path.basename(os.path.dirname(os.path.dirname(path)))

    df = pd.read_excel(path, dtype=str)
    if df.empty:
        return None

    # ── Numeric conversions ──────────────────────────────────────────────────
    amt_cols = (
        ['Actual GI QTY', 'Actual GI Amount',
         'Actual GR QTY', 'Actual GR Amount',
         'Actual ByProduct Scrap QTY', 'Actual ByProduct Scrap Amount',
         'Actual ByProduct Grade B QTY', 'Actual ByProduct Grade B Amount',
         'Actual ByProduct Grade C QTY', 'Actual ByProduct Grade C Amount',
         'Actual D101 QTY', 'Actual D101 Amount',
         'Actual D102 QTY', 'Actual D102 Amount'] +
        [f'Actual I{i:03d} Amount' for i in range(101, 112)]
    )
    for col in amt_cols:
        if col in df.columns:
            df[col] = _to_float(df[col])
        else:
            df[col] = 0.0

    # ── Derive computed columns ───────────────────────────────────────────────
    df['dm_amount']       = df['Actual GI Amount']
    df['cc_direct_amount']   = df['Actual D101 Amount'] + df['Actual D102 Amount']
    df['cc_indirect_amount'] = sum(
        df.get(f'Actual I{i:03d} Amount', pd.Series(0, index=df.index))
        for i in range(101, 112)
    )
    df['cc_amount']   = df['cc_direct_amount'] + df['cc_indirect_amount']
    df['total_cost']  = df['dm_amount'] + df['cc_amount']

    # scrap total (Scrap + Grade B + Grade C)
    df['scrap_qty_kg']  = (df['Actual ByProduct Scrap QTY'] +
                           df.get('Actual ByProduct Grade B QTY', 0) +
                           df.get('Actual ByProduct Grade C QTY', 0))
    df['scrap_amount']  = (df['Actual ByProduct Scrap Amount'] +
                           df.get('Actual ByProduct Grade B Amount', 0) +
                           df.get('Actual ByProduct Grade C Amount', 0))

    # ── Process label ─────────────────────────────────────────────────────────
    df['Process'] = df['Work Center'].apply(_map_process)

    # ── Select & rename output columns ────────────────────────────────────────
    out = pd.DataFrame({
        'Year':             year,
        'Month':            month,
        'Plant':            plant,
        'Process':          df['Process'],
        'WorkCenter':       df['Work Center'].astype(str).str.strip(),
        'WorkCenterDesc':   df['Work Center Description'].astype(str).str.strip(),
        'OrderType':        df['Order Type Name'].astype(str).str.strip(),
        'Order':            df['Order'].astype(str).str.strip(),
        'CombinedOrder':    df['Combined Order'].astype(str).str.strip(),
        'IsCombined':       df['Combined Order Status'].astype(str).str.strip().str.upper() == 'YES',
        'Status':           df['Status'].astype(str).str.strip(),
        'Material':         df['Material'].astype(str).str.strip(),
        'MaterialDesc':     df.get('Description (EN)', pd.Series('', index=df.index)).astype(str).str.strip(),
        'Grade':            df.get('Grade', pd.Series('', index=df.index)).astype(str).str.strip(),
        'GICoating':        df.get('GI Coating', pd.Series('', index=df.index)).astype(str).str.strip(),
        'gi_qty_kg':        df['Actual GI QTY'].round(3),
        'gi_amount':        df['Actual GI Amount'].round(2),
        'gr_qty_kg':        df['Actual GR QTY'].round(3),
        'gr_amount':        df['Actual GR Amount'].round(2),
        'scrap_qty_kg':     df['scrap_qty_kg'].round(3),
        'scrap_amount':     df['scrap_amount'].round(2),
        'dm_amount':        df['dm_amount'].round(2),
        'cc_direct_amount': df['cc_direct_amount'].round(2),
        'cc_indirect_amount': df['cc_indirect_amount'].round(2),
        'cc_amount':        df['cc_amount'].round(2),
        'total_cost':       df['total_cost'].round(2),
    })

    return out

# ─── Main ─────────────────────────────────────────────────────────────────────
def run(target_year: int | None = None):
    # New structure: production_orders/amc/{plant}/{year}/prd_{YYYYMM}.xlsx
    files = sorted(glob.glob(os.path.join(BRONZE, '**', 'prd_*.xlsx'), recursive=True))
    if not files:
        files = sorted(glob.glob(os.path.join(BRONZE, '**', 'prd_*.XLSX'), recursive=True))
    if not files:
        print(f'❌ ไม่พบไฟล์ prd_*.xlsx ใน {BRONZE}')
        sys.exit(1)

    print(f'📂 พบ {len(files)} ไฟล์ใน {BRONZE}')

    # group by year
    by_year: dict[int, list[pd.DataFrame]] = {}
    for f in files:
        m = re.match(r'prd_(\d{4})(\d{2})\.xlsx',
                     os.path.basename(f), re.IGNORECASE)
        if not m:
            continue
        yr = int(m.group(1))
        if target_year and yr != target_year:
            continue
        df = _parse_file(f)
        if df is not None:
            by_year.setdefault(yr, []).append(df)
            print(f'  ✅ {os.path.basename(f)}: {len(df):,} orders')

    if not by_year:
        print('⚠️  ไม่มีข้อมูลที่ตรงกับปีที่เลือก')
        return

    for yr, dfs in sorted(by_year.items()):
        combined = pd.concat(dfs, ignore_index=True)
        out_path = os.path.join(SILVER, f'master_prd_{yr}.parquet')
        os.makedirs(SILVER, exist_ok=True)
        combined["loaded_at"] = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S +07")
        combined.to_parquet(out_path, index=False)

        # preview
        q1 = combined[combined['Month'].isin([1,2,3])]
        summary = q1.groupby(['Plant','Process']).agg(
            orders   =('Order',      'count'),
            gi_amt   =('gi_amount',  'sum'),
            gr_qty_mt=('gr_qty_kg',  lambda x: x.sum()/1000),
            dm_amt   =('dm_amount',  'sum'),
            cc_amt   =('cc_amount',  'sum'),
            total    =('total_cost', 'sum'),
        ).round(0)
        print(f'\n✅ master_prd_{yr}.parquet — {len(combined):,} rows')
        print(f'   columns: {list(combined.columns)}')
        print(f'\nQ1 {yr} per Plant × Process:')
        pd.options.display.float_format = '{:,.0f}'.format
        print(summary.to_string())
        print(f'\n💾 บันทึกแล้ว: {out_path}')


def upsert_file(file_path: str) -> None:
    """Upsert เฉพาะไฟล์เดียว — ลบ rows เดิมของเดือนนั้น แล้ว append ใหม่"""
    fname = os.path.basename(file_path)
    m = re.match(r'prd_(\d{4})(\d{2})\.xlsx', fname, re.IGNORECASE)
    if not m:
        print(f"  ❌ ไม่รู้จักชื่อไฟล์: {fname}")
        return
    year, month = int(m.group(1)), int(m.group(2))
    print(f"  📄 Upsert: {fname} (month={month} year={year})")

    df_new = _parse_file(file_path)
    if df_new is None or df_new.empty:
        print(f"  ⚠️  ไม่มีข้อมูลใน {fname}")
        return

    out_path = os.path.join(SILVER, f'master_prd_{year}.parquet')
    if os.path.exists(out_path):
        df_existing = pd.read_parquet(out_path)
        mask = (df_existing["Year"].astype(int) == year) & (df_existing["Month"].astype(int) == month)
        dropped = mask.sum()
        df_existing = df_existing[~mask]
        if dropped:
            print(f"  🗑  ลบ {dropped:,} rows เดิม (month={month} year={year})")
    else:
        df_existing = pd.DataFrame()

    combined = pd.concat([df_existing, df_new], ignore_index=True)
    os.makedirs(SILVER, exist_ok=True)
    combined["loaded_at"] = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S +07")
    combined.to_parquet(out_path, index=False)
    print(f"  💾 Saved: master_prd_{year}.parquet ({len(combined):,} rows total)")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--year', type=int, default=None)
    parser.add_argument('--file', type=str, default=None, help='Upsert เฉพาะไฟล์นี้ (ไม่ rebuild ทั้งหมด)')
    args = parser.parse_args()
    if args.file:
        upsert_file(args.file)
    else:
        run(args.year)
