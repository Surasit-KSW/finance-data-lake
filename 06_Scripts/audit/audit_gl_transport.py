import pandas as pd
import numpy as np
import os

pd.set_option('display.float_format', '{:,.2f}'.format)

# กำหนด project root (06_Scripts/audit → 06_Scripts → project root)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
_SILVER = os.path.join(_PROJECT_ROOT, "02_Silver_Cleaned")

print("⏳ กำลังโหลดและประมวลผลข้อมูล GL (General Ledger)...")

# ========================================================
# 1. โหลดข้อมูล GL จาก Silver layer (ไฟล์รวม 2024-2025)
# ========================================================
try:
    gl_file = os.path.join(_SILVER, 'Master_GL_24_25.parquet')
    if not os.path.exists(gl_file):
        print(f"❌ ไม่พบไฟล์ GL: {gl_file}")
        exit()
    df_gl = pd.read_parquet(gl_file, engine='pyarrow')
    
    # 🌟 ตั้งค่าชื่อคอลัมน์มาตรฐาน (เปลี่ยนชื่อคอลัมน์ด้านขวาให้ตรงกับไฟล์ GL ของคุณ)
    col_amount = 'Amount in local currency' # ยอดเงิน (อาจจะเป็น Company Code Currency)
    col_date = 'Posting Date'             # วันที่บันทึกบัญชี
    col_gl_name = 'G/L Account Long Text' # ชื่อบัญชี
    col_desc = 'Text'                     # คำอธิบายรายการ
    col_vendor = 'Vendor Name'            # ชื่อผู้ขาย/ผู้ให้บริการ (ถ้ามี)
    
    # Clean ประเภทข้อมูล
    df_gl[col_amount] = pd.to_numeric(df_gl[col_amount], errors='coerce').fillna(0)
    df_gl[col_date] = pd.to_datetime(df_gl[col_date], errors='coerce')
    df_gl['Month'] = df_gl[col_date].dt.month
    
    # ถ้าไม่มีคอลัมน์ Vendor ให้ใช้คำอธิบายรายการ (Text) แทน
    if col_vendor not in df_gl.columns:
        df_gl[col_vendor] = df_gl[col_desc]
        
except Exception as e:
    print(f"❌ Error โหลดไฟล์ GL: {e}\n(กรุณาตรวจสอบ Path หรือชื่อคอลัมน์อีกครั้ง)")
    exit()

# ========================================================
# 🎯 ส่วนการวิเคราะห์ (Transport Expense Analysis)
# ========================================================

# 1. กรองเฉพาะบัญชีที่เกี่ยวกับ "ค่าขนส่ง"
# (สามารถเพิ่ม Keyword เข้าไปใน list นี้ได้ เช่น 'ค่าส่ง', 'Freight', 'Delivery')
keywords = ['Transport', 'ขนส่ง', 'Freight', 'Shipping', 'ค่าระวาง']
pattern = '|'.join(keywords)

df_transport = df_gl[df_gl[col_gl_name].astype(str).str.contains(pattern, case=False, na=False)].copy()

if df_transport.empty:
    print("❌ ไม่พบข้อมูลบัญชีค่าขนส่งใน GL (โปรดตรวจสอบชื่อบัญชีอีกครั้ง)")
    exit()

# โดยธรรมชาติ ค่าใช้จ่ายใน GL ฝั่งเดบิต (Debit) จะเป็นบวก เราจะรวมเฉพาะยอดบวก (หรือถ้ายอดรวมเป็นลบตามระบบ SAP ให้ใส่ .abs())
total_24 = df_transport[df_transport['Year'] == 2024][col_amount].sum()
total_25 = df_transport[df_transport['Year'] == 2025][col_amount].sum()

diff_total = total_25 - total_24
pct_total = (diff_total / total_24 * 100) if total_24 > 0 else 0

# หากยอดลดลง หรือไม่มีการเพิ่มขึ้น
if diff_total <= 0:
    print(f"✅ ภาพรวมค่าขนส่งในปี 2025 ({total_25:,.2f} บาท) ไม่ได้เพิ่มขึ้นเมื่อเทียบกับปี 2024 ({total_24:,.2f} บาท)")
    exit()

# 2. วิเคราะห์รายเดือน (หาเดือนที่ค่าใช้จ่ายพุ่งกระฉูด)
month_group = df_transport.groupby(['Month', 'Year'])[col_amount].sum().unstack(fill_value=0)
if 2024 not in month_group.columns: month_group[2024] = 0
if 2025 not in month_group.columns: month_group[2025] = 0
month_group['Diff'] = month_group[2025] - month_group[2024]
top_spike_months = month_group.sort_values('Diff', ascending=False).head(3)

# 3. วิเคราะห์ผู้ให้บริการ หรือ คำอธิบายรายการ (Vendor / Text)
vendor_group = df_transport.groupby([col_vendor, 'Year'])[col_amount].sum().unstack(fill_value=0)
if 2024 not in vendor_group.columns: vendor_group[2024] = 0
if 2025 not in vendor_group.columns: vendor_group[2025] = 0
vendor_group['Diff'] = vendor_group[2025] - vendor_group[2024]
top_vendors = vendor_group[vendor_group['Diff'] > 0].sort_values('Diff', ascending=False).head(5)

# ========================================================
# 📝 พิมพ์ Output ตอบออดิท (Copy & Paste ได้เลย)
# ========================================================
print(f"\n====================================================================")
print(f"📝 สรุปการวิเคราะห์สาเหตุการเพิ่มขึ้นของค่าขนส่ง (Transport Expenses Variance Analysis)")
print(f"====================================================================\n")

print("1️⃣ ภาพรวมการเปลี่ยนแปลง (Overall Variance)")
print(f"  - ค่าใช้จ่ายขนส่งรวม ปี 2024: {total_24:,.2f} บาท")
print(f"  - ค่าใช้จ่ายขนส่งรวม ปี 2025: {total_25:,.2f} บาท")
print(f"  > สรุป: ค่าขนส่งในปี 2025 ปรับตัว 'เพิ่มขึ้น' {diff_total:,.2f} บาท (คิดเป็น {pct_total:,.2f}%) จากปีก่อน\n")

print("2️⃣ ช่วงเวลาที่มีนัยสำคัญ (Timing & Seasonality)")
print("  การเพิ่มขึ้นของค่าขนส่งกระจุกตัวอยู่ในช่วงเดือนต่อไปนี้เป็นหลัก:")
month_names_th = {1:'ม.ค.', 2:'ก.พ.', 3:'มี.ค.', 4:'เม.ย.', 5:'พ.ค.', 6:'มิ.ย.', 7:'ก.ค.', 8:'ส.ค.', 9:'ก.ย.', 10:'ต.ค.', 11:'พ.ย.', 12:'ธ.ค.'}
for m, row in top_spike_months.iterrows():
    if row['Diff'] > 0:
        print(f"  - เดือน {month_names_th.get(m, m)}: ค่าขนส่งเพิ่มขึ้น {row['Diff']:,.2f} บาท (ยอดปี 25: {row[2025]:,.2f} บ. | ยอดปี 24: {row[2024]:,.2f} บ.)")
print()

print("3️⃣ ปัจจัยหลักที่ขับเคลื่อนต้นทุน (Top Cost Drivers by Vendor / Description)")
print("  สาเหตุหลักเกิดจากการทำธุรกรรมกับผู้ให้บริการขนส่ง หรือประเภทรายการดังต่อไปนี้ที่สูงขึ้น:")
for idx, row in top_vendors.iterrows():
    print(f"  - รายการ/ผู้ให้บริการ '{idx}':")
    print(f"    มียอดจ่ายเพิ่มขึ้น {row['Diff']:,.2f} บาท (ยอดปี 25: {row[2025]:,.2f} บ. | ยอดปี 24: {row[2024]:,.2f} บ.)")

print("\n💡 ข้อสรุปสำหรับ Auditor (Executive Conclusion):")
print(f"  การเพิ่มขึ้นของค่าขนส่งจำนวน {diff_total:,.2f} บาทนั้น มีสาเหตุหลักมาจากผู้ให้บริการขนส่งรายใหญ่ตามที่ระบุในข้อ 3 ซึ่งบริษัทได้มีการใช้บริการเพิ่มสูงขึ้นในช่วงเดือนตามที่ระบุในข้อ 2 ทั้งนี้ ฝ่ายบริหารแนะนำให้พิจารณาเปรียบเทียบกับ 'ปริมาณการขาย (Sales Volume)' หรือสัดส่วนเงื่อนไขการจัดส่งแบบ Delivery ประกอบ เพื่อประเมินความสมเหตุสมผลเชิงปริมาณ (Volume Driven) ต่อไป")
print(f"====================================================================")