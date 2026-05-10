import pandas as pd
import numpy as np

pd.set_option('display.float_format', '{:,.2f}'.format)

print("⏳ กำลังประมวลผลสาเหตุรายได้ลดลง (2024 vs 2025)...")

# 1. โหลดข้อมูล
try:
    df_24 = pd.read_parquet('./02_Silver_Cleaned/master_sales_2024.parquet', engine='pyarrow')
    df_25 = pd.read_parquet('./02_Silver_Cleaned/master_sales_2025.parquet', engine='pyarrow')
except Exception as e:
    print(f"❌ Error โหลดไฟล์: {e}")
    exit()

df_24['Year'] = 2024
df_25['Year'] = 2025
df_sales = pd.concat([df_24, df_25], ignore_index=True)

# 2. Clean ข้อมูล
df_sales['Net Value(THB)'] = pd.to_numeric(df_sales['Net Value(THB)'], errors='coerce').fillna(0)
df_sales['Net Weight'] = pd.to_numeric(df_sales['Net Weight'], errors='coerce').fillna(0)
df_sales['Mat Group Des.'] = df_sales.get('Mat Group Des.', 'Unknown Group').fillna('Unknown Group')

# ========================================================
# 🎯 ส่วนวิเคราะห์หา "สาเหตุที่ยอดลดลง"
# ========================================================

# 1. ภาพรวมบริษัท (Company Overall)
total_24 = df_sales[df_sales['Year'] == 2024]['Net Value(THB)'].sum()
total_25 = df_sales[df_sales['Year'] == 2025]['Net Value(THB)'].sum()
qty_24 = df_sales[df_sales['Year'] == 2024]['Net Weight'].sum()
qty_25 = df_sales[df_sales['Year'] == 2025]['Net Weight'].sum()

diff_total = total_25 - total_24
pct_total = (diff_total / total_24 * 100) if total_24 > 0 else 0

price_24 = total_24 / qty_24 if qty_24 > 0 else 0
price_25 = total_25 / qty_25 if qty_25 > 0 else 0

# 2. เจาะลึกรายลูกค้า (Top 5 ลูกค้าที่ยอดหายไปมากที่สุด)
cust_yoy = df_sales.groupby(['Sold-to Name', 'Year'])['Net Value(THB)'].sum().unstack(fill_value=0)
if 2024 not in cust_yoy.columns: cust_yoy[2024] = 0
if 2025 not in cust_yoy.columns: cust_yoy[2025] = 0
cust_yoy['Diff_Amt'] = cust_yoy[2025] - cust_yoy[2024]
top_drop_cust = cust_yoy[cust_yoy['Diff_Amt'] < 0].sort_values('Diff_Amt', ascending=True).head(5)

# 3. เจาะลึกรายกลุ่มสินค้า (Top 5 สินค้าที่ยอดตกมากที่สุด)
prod_yoy = df_sales.groupby(['Mat Group Des.', 'Year']).agg(
    Amt=('Net Value(THB)', 'sum'),
    Qty=('Net Weight', 'sum')
).unstack(fill_value=0)

prod_yoy.columns = [f"{col[0]}_{col[1]}" for col in prod_yoy.columns]
for y in [2024, 2025]:
    if f'Amt_{y}' not in prod_yoy.columns: prod_yoy[f'Amt_{y}'] = 0
    if f'Qty_{y}' not in prod_yoy.columns: prod_yoy[f'Qty_{y}'] = 0

prod_yoy['Diff_Amt'] = prod_yoy['Amt_2025'] - prod_yoy['Amt_2024']
prod_yoy['Diff_Qty'] = prod_yoy['Qty_2025'] - prod_yoy['Qty_2024']
top_drop_prod = prod_yoy[prod_yoy['Diff_Amt'] < 0].sort_values('Diff_Amt', ascending=True).head(5)

# ========================================================
# 📝 พิมพ์ Output ตอบออดิท (Copy & Paste ได้เลย)
# ========================================================
print(f"\n====================================================================")
print(f"📝 สรุปวิเคราะห์สาเหตุการลดลงของรายได้ (Revenue Decline Analysis)")
print(f"เปรียบเทียบปี 2024 และ 2025 (ภาพรวมทั้งบริษัท)")
print(f"====================================================================\n")

if diff_total >= 0:
    print(f"✅ หมายเหตุ: ภาพรวมรายได้ปี 2025 ไม่ได้ลดลง (เติบโต {pct_total:,.2f}%)")
    print(f"ยอดขายปี 2024: {total_24:,.2f} บาท | ยอดขายปี 2025: {total_25:,.2f} บาท")
else:
    print(f"ภาพรวมรายได้จากการขายสุทธิในปี 2025 ปรับตัวลดลง {abs(pct_total):,.2f}% เมื่อเทียบกับปี 2024")
    print(f"(ลดลงจำนวน {abs(diff_total):,.2f} บาท จาก {total_24:,.2f} บาท เป็น {total_25:,.2f} บาท)")
    print(f"โดยฝ่ายบริหารได้ทำการวิเคราะห์สาเหตุหลัก (Root Cause Analysis) ซึ่งประกอบด้วยปัจจัยดังต่อไปนี้:\n")

    # --- สาเหตุที่ 1: Volume vs Price ---
    print("1️⃣ ปัจจัยด้านปริมาณ (Volume) และ ราคาขาย (Price)")
    if qty_25 < qty_24 and price_25 < price_24:
        print(f"  - รายได้ที่ลดลงเกิดจาก 'ปริมาณการขายที่ลดลง' {abs((qty_25-qty_24)/qty_24*100):,.2f}% (จาก {qty_24:,.2f} เป็น {qty_25:,.2f} หน่วย)")
        print(f"  - ควบคู่ไปกับ 'ราคาขายเฉลี่ยที่ปรับตัวลดลง' {abs((price_25-price_24)/price_24*100):,.2f}% (จาก {price_24:,.2f} เป็น {price_25:,.2f} บาท/หน่วย)")
    elif qty_25 < qty_24:
        print(f"  - สาเหตุหลักเกิดจาก 'ปริมาณความต้องการสินค้า (Volume) ลดลง' เป็นหลัก จำนวน {abs(qty_25-qty_24):,.2f} หน่วย (ลดลง {abs((qty_25-qty_24)/qty_24*100):,.2f}%)")
        print(f"  - แม้ว่าราคาขายเฉลี่ยจะปรับตัวสูงขึ้นเล็กน้อยเป็น {price_25:,.2f} บาท/หน่วย แต่ไม่สามารถชดเชยปริมาณที่หายไปได้")
    elif price_25 < price_24:
        print(f"  - สาเหตุหลักเกิดจาก 'การปรับลดราคาขายเฉลี่ย (Price Down)' ตามสภาวะการแข่งขันตลาด ลงเหลือ {price_25:,.2f} บาท/หน่วย")
        print(f"  - แม้ว่าบริษัทจะสามารถผลักดันปริมาณขาย (Volume) ให้สูงขึ้นเป็น {qty_25:,.2f} หน่วย แต่ราคาที่ลดลงส่งผลกระทบต่อรายได้รวมมากกว่า")

    print()
    
    # --- สาเหตุที่ 2: กลุ่มสินค้า ---
    print("2️⃣ ผลกระทบจากการชะลอตัวของกลุ่มสินค้าหลัก (Product Mix Impact)")
    print("ยอดขายที่หดตัวลงกระจุกตัวอยู่ในกลุ่มสินค้าหลักต่อไปนี้:")
    for idx, row in top_drop_prod.iterrows():
        qty_drop_text = f"ปริมาณขายลดลง {abs(row['Diff_Qty']):,.2f} หน่วย" if row['Diff_Qty'] < 0 else "ปริมาณขายเพิ่มขึ้นแต่ราคาตลาดปรับลดลง"
        print(f"  - กลุ่ม {idx}: รายได้ลดลง {abs(row['Diff_Amt']):,.2f} บาท ({qty_drop_text})")
        
    print()

    # --- สาเหตุที่ 3: ลูกค้าหลัก ---
    print("3️⃣ ผลกระทบจากฐานลูกค้า (Customer Impact)")
    print("รายได้ที่ลดลงมีนัยสำคัญมาจากลูกค้ารายใหญ่ที่มีการปรับลดคำสั่งซื้อ หรือชะลอโครงการ ดังนี้:")
    for idx, row in top_drop_cust.iterrows():
        print(f"  - {idx}: ยอดสั่งซื้อลดลง {abs(row['Diff_Amt']):,.2f} บาท (ยอดปี 25: {row[2025]:,.2f} บ.)")

print(f"\n====================================================================")