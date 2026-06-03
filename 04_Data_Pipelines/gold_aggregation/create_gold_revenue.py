"""
create_gold_revenue.py — Silver Sales → Gold: Monthly Revenue by Plant

อ่าน master_sales_*.parquet ทุกปีจาก Silver
Aggregate: Year × Month × Plant → revenue_thb, qty_sold_mt
Output: 03_Gold_DataMarts/gold_revenue_monthly.parquet

รัน: python 04_Data_Pipelines/gold_aggregation/create_gold_revenue.py
"""
import os
import sys
import glob

import pandas as pd

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
SILVER       = os.path.join(PROJECT_ROOT, '02_Silver_Cleaned')
GOLD         = os.path.join(PROJECT_ROOT, '03_Gold_DataMarts')
OUTPUT_FILE  = os.path.join(GOLD, 'gold_revenue_monthly.parquet')

# ── Load Silver ───────────────────────────────────────────────────────────────
files = sorted(glob.glob(os.path.join(SILVER, 'master_sales_*.parquet')))
if not files:
    print(f'❌ ไม่พบ master_sales_*.parquet ใน {SILVER}')
    sys.exit(1)

print(f'📂 พบ {len(files)} ไฟล์:')
dfs = []
for f in files:
    df = pd.read_parquet(f)
    print(f'   {os.path.basename(f)}: {len(df):,} rows')
    dfs.append(df)

df = pd.concat(dfs, ignore_index=True)
print(f'\n📊 รวม: {len(df):,} rows | ปี: {sorted(df["Year"].unique())}')

# ── Validate required columns ─────────────────────────────────────────────────
required = {'Year', 'Month', 'Plant', 'Net Value(THB)', 'Billed Qty', 'Cancelled'}
missing  = required - set(df.columns)
if missing:
    print(f'❌ ขาด columns: {sorted(missing)}')
    sys.exit(1)

# ── Filter — exclude cancelled billings ───────────────────────────────────────
df['Cancelled'] = df['Cancelled'].astype(str).str.strip()
before = len(df)
df = df[
    (df['Net Value(THB)'].notna()) &
    (pd.to_numeric(df['Net Value(THB)'], errors='coerce').fillna(0) > 0) &
    (df['Cancelled'].isin(['nan', 'None', '']))
]
print(f'🔍 หลัง filter cancelled + Net Value > 0: {len(df):,} rows (ลบออก {before - len(df):,})')

# ── Aggregate: Year × Month × Plant ──────────────────────────────────────────
df['Net Value(THB)'] = pd.to_numeric(df['Net Value(THB)'], errors='coerce').fillna(0)
df['Billed Qty']     = pd.to_numeric(df['Billed Qty'],     errors='coerce').fillna(0)
df['Plant']          = df['Plant'].astype(str).str.strip()

gold = (
    df.groupby(['Year', 'Month', 'Plant'], as_index=False)
    .agg(
        revenue_thb  = ('Net Value(THB)', 'sum'),
        qty_sold_st  = ('Billed Qty',     'sum'),
        billing_count= ('Billing No',     'count'),
    )
)

gold['revenue_thb'] = gold['revenue_thb'].round(2)
gold['qty_sold_st'] = gold['qty_sold_st'].round(3)
gold = gold.sort_values(['Year', 'Month', 'Plant']).reset_index(drop=True)

print(f'\n✅ Gold table: {len(gold):,} rows')
print(gold.to_string(index=False))

# ── Save ──────────────────────────────────────────────────────────────────────
os.makedirs(GOLD, exist_ok=True)
gold.to_parquet(OUTPUT_FILE, index=False)
print(f'\n💾 บันทึกแล้ว: {OUTPUT_FILE}')
