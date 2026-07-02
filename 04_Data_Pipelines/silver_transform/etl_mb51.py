"""
etl_mb51.py — Bronze MB51 → Silver: Material Document (GI for Order)

อ่านไฟล์:
  1. material_docs/amc/all/{year}/mb51_all_{YYYYMM}.xlsx  — movement 261 (GI for order, RM/semi-FG)
Output: 02_Silver_Cleaned/master_mb51_{year}.parquet

โครงสร้างผลลัพธ์ per order:
  Year, Month, Plant, Order
  gi_hrc_amount   → HRC steel (RM)
  gi_gic_amount   → GIC/semi-FG จาก Plant 1300
  gi_crc_amount   → Cold Rolled Coil (Plant 1300)
  gi_chem_amount  → Zinc/GI ingots + HCl + chemical consumables (core material Plant 1300)
  gi_other_amount → อื่นๆ
  gi_dm_amount    → HRC + GIC + CRC + chem
  gi_total_amount → dm + other
  input_type      → dominant type (HRC / GIC / CRC / chem)

Input material classification (by material code prefix):
  HRC  : 10HRC, 20HRL, 20HRC          → HRC ซื้อจาก supplier
  GIC  : 20GIL, 20GIC, 20GML, 20GMC,  → GIC/semi-FG จาก Plant 1300
         20ZML, 20ZMC, 10GIC, 10GMC     (= RM ใน Plant 1100/1200)
  CRC  : 20CRC                         → Cold Rolled Coil (Plant 1300)
  chem : 10ING*                         → Zinc/GI ingots (galvanizing core, movement Z61)
         50xxx                          → HCl, consumables
  other: 90xxx (scrap), อื่นๆ

หมายเหตุ:
  - 10xxx ที่ไม่ใช่ 10HRC* และ 10ING* → HRC (fallback RM จาก supplier)
  - 20xxx → GIC หรือ CRC ตาม prefix
  - 30xxx = FG ไม่ควรอยู่ใน GI for order

รัน: python 04_Data_Pipelines/silver_transform/etl_mb51.py
     python 04_Data_Pipelines/silver_transform/etl_mb51.py --year 2026
"""
import os, sys, re, glob, argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
BRONZE       = os.path.join(PROJECT_ROOT, '01_Bronze_Raw', 'material_docs', 'amc')
SILVER       = os.path.join(PROJECT_ROOT, '02_Silver_Cleaned')

# ─── Input type classifier ────────────────────────────────────────────────────
HRC_PREFIXES  = {'20HRL', '20HRC', '10HRC'}
GIC_PREFIXES  = {'20GIL', '20GIC', '20GML', '20GMC', '20ZML', '20ZMC',
                 '10GIC', '10GMC'}
CRC_PREFIXES  = {'20CRC'}
CHEM_PREFIXES = {'10ING'}   # Zinc/GI ingots (10INGZM*, 10INGGI*, 10INGPZ*, …)

def _classify_input(mat: str) -> str:
    mat     = str(mat).strip().upper()
    prefix5 = mat[:5]
    p2      = mat[:2]

    if prefix5 in HRC_PREFIXES:   return 'HRC'
    if prefix5 in GIC_PREFIXES:   return 'GIC'
    if prefix5 in CRC_PREFIXES:   return 'CRC'
    if prefix5 in CHEM_PREFIXES:  return 'chem'   # Zinc/GI ingots
    if p2 == '10':                return 'HRC'    # other 10xxx = RM from supplier
    if p2 == '50':                return 'chem'   # 50xxx = HCl, consumables
    return 'other'

# ─── Parse one MB51 file ──────────────────────────────────────────────────────
def _parse_file(path: str, mvt_filter: str = '261') -> pd.DataFrame | None:
    fname = os.path.basename(path)
    m = re.match(r'mb51_all_(\d{4})(\d{2})\.xlsx', fname, re.IGNORECASE)
    if not m:
        print(f'  ⏭️  skip (filename mismatch): {fname}')
        return None

    year  = int(m.group(1))
    month = int(m.group(2))

    df = pd.read_excel(path, dtype=str)
    df.columns = df.columns.str.strip()

    # Filter movement type
    df = df[df['Movement type'] == mvt_filter].copy()
    if df.empty:
        return None

    # Drop rows without Order
    df = df[df['Order'].notna() & (df['Order'].str.strip() != '') & (df['Order'] != 'nan')]
    if df.empty:
        return None

    # Numeric
    df['qty_raw'] = pd.to_numeric(
        df['Qty in unit of entry'].astype(str).str.replace(',', ''), errors='coerce'
    ).fillna(0)
    df['amt_raw'] = pd.to_numeric(
        df['Amt.in Loc.Cur.'].astype(str).str.replace(',', ''), errors='coerce'
    ).fillna(0)

    # SAP GI amounts are negative (credit inventory) → take abs for cost
    df['qty_kg']     = df['qty_raw'].abs()
    df['amount_thb'] = df['amt_raw'].abs()

    # Plant normalise
    df['Plant'] = pd.to_numeric(df['Plant'], errors='coerce').fillna(0).astype(int).astype(str)

    # Input type
    df['input_type']      = df['Material'].apply(_classify_input)
    df['material_prefix'] = df['Material'].astype(str).str[:5].str.upper()

    out = pd.DataFrame({
        'Year':            year,
        'Month':           month,
        'Plant':           df['Plant'],
        'Order':           df['Order'].astype(str).str.strip(),
        'Material':        df['Material'].astype(str).str.strip(),
        'MaterialDesc':    df.get('Material description', pd.Series('', index=df.index)).astype(str).str.strip(),
        'material_prefix': df['material_prefix'],
        'input_type':      df['input_type'],
        'qty_kg':          df['qty_kg'].round(3),
        'amount_thb':      df['amount_thb'].round(2),
    })

    return out

# ─── Aggregate to order level ─────────────────────────────────────────────────
def _aggregate_to_order(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate MB51 line items to Order level.
    Produces: gi_hrc_amount, gi_gic_amount, gi_crc_amount, gi_chem_amount,
              gi_other_amount, gi_dm_amount, gi_total_amount, input_type (dominant).
    """
    grp = (
        df.groupby(['Year', 'Month', 'Plant', 'Order', 'input_type'], as_index=False)
        .agg(qty_kg=('qty_kg', 'sum'), amount_thb=('amount_thb', 'sum'))
    )

    pivot = grp.pivot_table(
        index=['Year', 'Month', 'Plant', 'Order'],
        columns='input_type',
        values='amount_thb',
        aggfunc='sum',
        fill_value=0
    ).reset_index()
    pivot.columns.name = None

    for col in ('HRC', 'GIC', 'CRC', 'chem', 'other'):
        if col not in pivot.columns:
            pivot[col] = 0.0

    pivot = pivot.rename(columns={
        'HRC':   'gi_hrc_amount',
        'GIC':   'gi_gic_amount',
        'CRC':   'gi_crc_amount',
        'chem':  'gi_chem_amount',   # Zinc/GI ingots + HCl + consumables
        'other': 'gi_other_amount',
    })
    pivot['gi_dm_amount'] = (
        pivot['gi_hrc_amount'] + pivot['gi_gic_amount'] +
        pivot['gi_crc_amount'] + pivot['gi_chem_amount']
    )
    pivot['gi_total_amount'] = pivot['gi_dm_amount'] + pivot['gi_other_amount']

    # Dominant RM input type (HRC vs GIC vs CRC — ignore chem/other)
    pivot['input_type'] = 'HRC'
    pivot.loc[pivot['gi_gic_amount'] > pivot['gi_hrc_amount'], 'input_type'] = 'GIC'
    pivot.loc[pivot['gi_crc_amount'] > pivot['gi_hrc_amount'], 'input_type'] = 'CRC'
    pivot.loc[
        (pivot['gi_hrc_amount'] == 0) & (pivot['gi_gic_amount'] == 0) &
        (pivot['gi_crc_amount'] == 0),
        'input_type'
    ] = 'chem'

    return pivot.round(2)

# ─── Main ─────────────────────────────────────────────────────────────────────
def run(target_year: int | None = None):
    # New structure: material_docs/amc/all/{year}/mb51_all_{YYYYMM}.xlsx
    all_plant_files = sorted(glob.glob(os.path.join(BRONZE, 'all', '**', 'mb51_all_*.xlsx'), recursive=True))
    if not all_plant_files:
        all_plant_files = sorted(glob.glob(os.path.join(BRONZE, 'all', '**', 'mb51_all_*.XLSX'), recursive=True))

    if not all_plant_files:
        print(f'❌ ไม่พบไฟล์ mb51_all_*.xlsx ใน {BRONZE}/all/')
        sys.exit(1)

    print(f'📂 MB51_all: {len(all_plant_files)} ไฟล์')

    file_specs = [(f, '261') for f in all_plant_files]

    by_year: dict[int, list[pd.DataFrame]] = {}
    for path, mvt in file_specs:
        fname = os.path.basename(path)
        m = re.match(r'mb51_all_(\d{4})(\d{2})\.xlsx', fname, re.IGNORECASE)
        if not m:
            continue
        yr = int(m.group(1))
        if target_year and yr != target_year:
            continue
        df = _parse_file(path, mvt_filter=mvt)
        if df is not None:
            by_year.setdefault(yr, []).append(df)
            print(f'  ✅ {fname} (mvt={mvt}): {len(df):,} GI lines')

    if not by_year:
        print('⚠️  ไม่มีข้อมูล')
        return

    for yr, dfs in sorted(by_year.items()):
        raw = pd.concat(dfs, ignore_index=True)
        agg = _aggregate_to_order(raw)

        out_path = os.path.join(SILVER, f'master_mb51_{yr}.parquet')
        os.makedirs(SILVER, exist_ok=True)
        agg["loaded_at"] = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S +07")
        agg.to_parquet(out_path, index=False)

        pd.options.display.float_format = '{:,.0f}'.format
        print(f'\n✅ master_mb51_{yr}.parquet — {len(agg):,} orders')
        print(f'   columns: {list(agg.columns)}')

        by_plant = agg.groupby(['Plant', 'input_type']).agg(
            orders=('Order',          'count'),
            hrc   =('gi_hrc_amount',  'sum'),
            gic   =('gi_gic_amount',  'sum'),
            chem  =('gi_chem_amount', 'sum'),
            total =('gi_total_amount','sum'),
        )
        print(f'\nSummary per Plant × input_type:')
        print(by_plant.to_string())
        print(f'\n💾 บันทึกแล้ว: {out_path}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--year', type=int, default=None)
    args = parser.parse_args()
    run(args.year)
