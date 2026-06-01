import glob
import os

import pandas as pd

print("⏳ กำลังสร้างไฟล์ข้อมูลระดับ Gold (Summary) แบบมีชื่อบัญชี...")

script_dir = os.path.dirname(os.path.abspath(__file__))   # gold_aggregation/
project_root = os.path.dirname(os.path.dirname(script_dir))  # → project root

# หาไฟล์ Silver GL อัตโนมัติ — รองรับทุกชื่อ เช่น Master_GL_24_25.parquet, Master_GL_24_26.parquet
silver_dir = os.path.join(project_root, '02_Silver_Cleaned')
gl_candidates = sorted(glob.glob(os.path.join(silver_dir, 'Master_GL_*.parquet')))
if not gl_candidates:
    print(f"❌ ไม่พบไฟล์ Silver GL (Master_GL_*.parquet) ใน: {silver_dir}")
    raise SystemExit(1)

# ใช้ไฟล์ล่าสุด (sort alphabetically → ปีใหม่กว่ามาหลัง)
input_file = gl_candidates[-1]
print(f"📂 ใช้ไฟล์ Silver GL: {os.path.basename(input_file)}")

# ตั้งชื่อ output ตามปีที่มีข้อมูลจริง (อ่านจากข้อมูล)
output_dir = os.path.join(project_root, '03_Gold_DataMarts')
os.makedirs(output_dir, exist_ok=True)

print(f"📂 กำลังอ่านไฟล์จาก: {input_file}")
df_full = pd.read_parquet(input_file)
available = set(df_full.columns)

# Required columns — bail if any are missing
required = {'Year', 'Month', 'G/L Account', 'Net_Amount'}
missing = required - available
if missing:
    print(f"❌ Silver GL file ขาด columns: {sorted(missing)}")
    print("   กรุณา re-export FBL3N จาก SAP ให้รวม G/L Account + Amount in LC + Fiscal Year")
    raise SystemExit(1)

# Optional: account long text
use_cols = ['Year', 'Month', 'G/L Account', 'Net_Amount']
has_long_text = 'G/L Account: Long Text' in available
if has_long_text:
    use_cols.append('G/L Account: Long Text')

df = df_full[use_cols].copy()
if not has_long_text:
    df['G/L Account: Long Text'] = None
    print("   ℹ️  'G/L Account: Long Text' not found — GL_Name will be empty")

# ตั้งชื่อ output ตามช่วงปีจริงในข้อมูล เช่น Summary_GL_24_26.parquet
years = sorted(df['Year'].dropna().astype(int).unique())
if len(years) >= 2:
    year_suffix = f"{str(years[0])[-2:]}_{str(years[-1])[-2:]}"
elif len(years) == 1:
    y = str(years[0])[-2:]
    year_suffix = f"{y}_{y}"
else:
    year_suffix = "all"
output_file = os.path.join(output_dir, f'Summary_GL_{year_suffix}.parquet')
print(f"💾 Output: {os.path.basename(output_file)}  (ปีในข้อมูล: {years})")

def get_gl_group(gl):
    gl_str = str(gl)
    if gl_str.startswith('1'): return '1. Assets'
    elif gl_str.startswith('2'): return '2. Liabilities'
    elif gl_str.startswith('3'): return '3. Equity'
    elif gl_str.startswith('4'): return '4. Revenue'
    elif gl_str.startswith('5'): return '5. COGS'
    elif gl_str.startswith('6'): return '6. Selling Exp'
    elif gl_str.startswith('7'): return '7. Admin Exp'
    elif gl_str.startswith('8'): return '8. Finance Cost'
    elif gl_str.startswith('9'): return '9. Tax'
    else: return '0. Others'

df['GL_Group'] = df['G/L Account'].apply(get_gl_group)

print("🧮 กำลังสรุปยอดรวม (Aggregation)...")
# 🌟 [เพิ่มใหม่] กรุ๊ปรวมและจำชื่อบัญชีเอาไว้
summary_df = df.groupby(['Year', 'Month', 'GL_Group', 'G/L Account']).agg({
    'Net_Amount': 'sum',
    'G/L Account: Long Text': 'first' # ดึงชื่อบัญชีชื่อแรกที่เจอมาแสดง
}).reset_index()

# เปลี่ยนชื่อคอลัมน์ให้สั้นลงเป็น GL_Name
summary_df.rename(columns={'G/L Account: Long Text': 'GL_Name'}, inplace=True)
summary_df['GL_Name'] = summary_df['GL_Name'].fillna('Unknown')

print(f"💾 กำลังบันทึกไฟล์ Gold Data ไปที่: {output_file}")
summary_df.to_parquet(output_file, engine='pyarrow', index=False)

# ลบ Gold files เก่าที่ชื่อต่างออกไป (เช่น Summary_GL_24_25.parquet เมื่อมี _24_26 แล้ว)
for old_file in glob.glob(os.path.join(output_dir, 'Summary_GL_*.parquet')):
    if old_file != output_file:
        os.remove(old_file)
        print(f"🗑️  ลบไฟล์เก่า: {os.path.basename(old_file)}")

print("✅ สำเร็จ! ไฟล์ Summary อัปเดตชื่อบัญชีเรียบร้อยแล้ว")