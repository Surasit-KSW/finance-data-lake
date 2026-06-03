"""
create_gold_gp.py — Silver Sales + GL → Gold: GP by Plant (Monthly)

สร้าง gold_gp_by_plant.parquet
  Year × Month × Plant → revenue, cogs_std, cogs_ml, cogs_other, gp_actual, gp_margin

วิธีคิด (validated Q1 2026):
  รวม COGS ทุกหมวด 5xxx เป็น company pool per month (net หลัง reversal แล้ว)
    - cogs_std  : 5111xxx excl 5119020
    - cogs_ml   : 5119020
    - cogs_other: หมวด 5xxx อื่นๆ
  จากนั้นกระจายลง plant ตามสัดส่วน qty_sold_st per month

  เหตุผล: GL มี reversal entry ยกเลิก STD ผิดโดยไม่มี DO reference
  → DO-join ดึงได้แค่ debit ไม่เห็น credit กลับ ทำให้ COGS บวม
  → ใช้ net pool ทำให้ reversal ถูก absorb อัตโนมัติก่อนกระจาย

รัน: python 04_Data_Pipelines/gold_aggregation/create_gold_gp.py
"""
import os, sys, glob
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
SILVER       = os.path.join(PROJECT_ROOT, '02_Silver_Cleaned')
GOLD         = os.path.join(PROJECT_ROOT, '03_Gold_DataMarts')
OUTPUT_FILE  = os.path.join(GOLD, 'gold_gp_by_plant.parquet')

# ─── 1. Load Sales (Silver) ───────────────────────────────────────────────────
print('📂 Loading Sales...')
sale_files = sorted(glob.glob(os.path.join(SILVER, 'master_sales_*.parquet')))
sales = pd.concat([pd.read_parquet(f) for f in sale_files], ignore_index=True)

sales['Plant']          = sales['Plant'].astype(str).str.strip()
sales['Net Value(THB)'] = pd.to_numeric(sales['Net Value(THB)'], errors='coerce').fillna(0)
sales['Billed Qty']     = pd.to_numeric(sales['Billed Qty'],     errors='coerce').fillna(0)
sales['Year']           = sales['Year'].astype(int)
sales['Month']          = sales['Month'].astype(int)

sales = sales[
    (sales['Net Value(THB)'] > 0) &
    sales['Cancelled'].astype(str).isin(['nan', 'None', ''])
]
print(f'   Sales rows (active): {len(sales):,}')

# Revenue + Qty per Year × Month × Plant
revenue = (
    sales.groupby(['Year', 'Month', 'Plant'], as_index=False)
    .agg(revenue_thb=('Net Value(THB)', 'sum'),
         qty_sold_st =('Billed Qty',     'sum'))
)

# ─── 2. Load GL (Silver) ─────────────────────────────────────────────────────
print('📂 Loading GL...')
gl_files = sorted(glob.glob(os.path.join(SILVER, 'Master_GL_*.parquet')))
gl = pd.concat([pd.read_parquet(f) for f in gl_files], ignore_index=True)
gl = gl.dropna(subset=['Year', 'Month'])
gl['Year']  = gl['Year'].astype(float).astype(int)
gl['Month'] = gl['Month'].astype(float).astype(int)
gl['acct']  = gl['G/L Account'].astype(str)
print(f'   GL rows: {len(gl):,}')

# ─── 3. COGS pool per month (company level, net) ─────────────────────────────
print('📊 Computing COGS pool (company net)...')

# 3a. COGS STD: 5111xxx + 5119010, excl 5119020
std_gl = gl[
    (gl['acct'].str.startswith('5111') | gl['acct'].str.startswith('51190')) &
    ~gl['acct'].str.startswith('5119020')
]
cogs_std_monthly = (
    std_gl.groupby(['Year', 'Month'], as_index=False)
    .agg(cogs_std_total=('Net_Amount', 'sum'))
)

# 3b. COGS ML: 5119020
ml_gl = gl[gl['acct'].str.startswith('5119020')]
cogs_ml_monthly = (
    ml_gl.groupby(['Year', 'Month'], as_index=False)
    .agg(cogs_ml_total=('Net_Amount', 'sum'))
)

# 3c. Other 5xxx (ไม่ใช่ 5111xxx และไม่ใช่ 51190xx)
other_gl = gl[
    gl['acct'].str.startswith('5') &
    ~gl['acct'].str.startswith('5111') &
    ~gl['acct'].str.startswith('51190')
]
cogs_other_monthly = (
    other_gl.groupby(['Year', 'Month'], as_index=False)
    .agg(cogs_other_total=('Net_Amount', 'sum'))
)

# รวม pool ทั้ง 3 หมวด
pool = (
    cogs_std_monthly
    .merge(cogs_ml_monthly,    on=['Year', 'Month'], how='outer')
    .merge(cogs_other_monthly, on=['Year', 'Month'], how='outer')
    .fillna(0)
)
pool['cogs_total'] = pool['cogs_std_total'] + pool['cogs_ml_total'] + pool['cogs_other_total']

# preview
for _, r in pool[(pool['Year']==2026) & (pool['Month'].isin([1,2,3]))].iterrows():
    print(f'   {int(r.Year)}-{int(r.Month):02d}  STD={r.cogs_std_total:>15,.0f}  '
          f'ML={r.cogs_ml_total:>14,.0f}  Other={r.cogs_other_total:>12,.0f}  '
          f'Total={r.cogs_total:>15,.0f}')

# ─── 4. Allocate COGS pool to plants by qty proportion ───────────────────────
print('🔧 Allocating by qty proportion...')

# qty per plant per month
qty_by_plant = revenue[['Year', 'Month', 'Plant', 'qty_sold_st']].copy()
qty_total    = qty_by_plant.groupby(['Year', 'Month'])['qty_sold_st'].transform('sum')
qty_by_plant['qty_pct'] = (qty_by_plant['qty_sold_st'] / qty_total).fillna(0)

# join pool
qty_by_plant = qty_by_plant.merge(pool, on=['Year', 'Month'], how='left')

qty_by_plant['cogs_std_thb']   = (qty_by_plant['qty_pct'] * qty_by_plant['cogs_std_total']).round(2)
qty_by_plant['cogs_ml_thb']    = (qty_by_plant['qty_pct'] * qty_by_plant['cogs_ml_total']).round(2)
qty_by_plant['cogs_other_thb'] = (qty_by_plant['qty_pct'] * qty_by_plant['cogs_other_total']).round(2)
qty_by_plant['cogs_total_thb'] = (qty_by_plant['qty_pct'] * qty_by_plant['cogs_total']).round(2)

# ─── 5. Combine ───────────────────────────────────────────────────────────────
gold = revenue.merge(
    qty_by_plant[['Year','Month','Plant','cogs_std_thb','cogs_ml_thb','cogs_other_thb','cogs_total_thb']],
    on=['Year','Month','Plant'], how='left'
).fillna(0)

gold['gp_actual'] = (gold['revenue_thb'] - gold['cogs_total_thb']).round(2)
gold['gp_margin_pct'] = (
    (gold['gp_actual'] / gold['revenue_thb'] * 100)
    .where(gold['revenue_thb'] > 0)
    .round(2)
)
gold = gold.sort_values(['Year', 'Month', 'Plant']).reset_index(drop=True)

# ─── 6. Preview & Save ────────────────────────────────────────────────────────
print(f'\n✅ Gold GP table: {len(gold)} rows')

q1 = gold[(gold['Year']==2026) & (gold['Month'].isin([1,2,3]))]
summary = q1.groupby('Plant').agg(
    revenue    =('revenue_thb',    'sum'),
    cogs_std   =('cogs_std_thb',   'sum'),
    cogs_ml    =('cogs_ml_thb',    'sum'),
    cogs_other =('cogs_other_thb', 'sum'),
    cogs_total =('cogs_total_thb', 'sum'),
    gp_actual  =('gp_actual',      'sum'),
).assign(gp_margin=lambda d: (d['gp_actual'] / d['revenue'] * 100).round(2))

pd.options.display.float_format = '{:,.0f}'.format
print('\nQ1 2026 per plant:')
print(summary.to_string())

# company total check
tot = summary.sum()
print(f'\nCompany total  Revenue={tot["revenue"]:>15,.0f}  COGS={tot["cogs_total"]:>15,.0f}  GP={tot["gp_actual"]:>15,.0f}  ({tot["gp_actual"]/tot["revenue"]*100:.1f}%)')

os.makedirs(GOLD, exist_ok=True)
gold.to_parquet(OUTPUT_FILE, index=False)
print(f'\n💾 บันทึกแล้ว: {OUTPUT_FILE}')
