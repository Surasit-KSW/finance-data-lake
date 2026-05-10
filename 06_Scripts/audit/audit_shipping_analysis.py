import pandas as pd
import numpy as np

pd.set_option('display.float_format', '{:,.2f}'.format)

print("⏳ กำลังโหลดและประมวลผลข้อมูล Sales 2024 - 2025...")

# ========================================================
# 1. โหลดข้อมูล Sales (Silver Layer)
# ========================================================
try:
    df_24 = pd.read_parquet('./02_Silver_Cleaned/master_sales_2024.parquet', engine='pyarrow')
    df_25 = pd.read_parquet('./02_Silver_Cleaned/master_sales_2025.parquet', engine='pyarrow')
    df_24['Year'] = 2024
    df_25['Year'] = 2025
    df_sales = pd.concat([df_24, df_25], ignore_index=True)
    
    # Clean คอลัมน์ที่ต้องการใช้งาน
    df_sales['Net Value(THB)'] = pd.to_numeric(df_sales['Net Value(THB)'], errors='coerce').fillna(0)
    df_sales['Net Weight'] = pd.to_numeric(df_sales['Net Weight'], errors='coerce').fillna(0)
    
    # ตรวจสอบคอลัมน์ Shipping Condition
    ship_col = 'Shipping Condition Name'
    if ship_col not in df_sales.columns:
        print(f"⚠️ คำเตือน: ไม่พบคอลัมน์ '{ship_col}' ระบบจะลองหาคอลัมน์ที่ชื่อใกล้เคียง...")
        possible_cols = [c for c in df_sales.columns if 'shipping' in c.lower() or 'condition' in c.lower()]
        if possible_cols:
            ship_col = possible_cols[0]
            print(f"👉 พบคอลัมน์ '{ship_col}' แทน")
        else:
            df_sales[ship_col] = 'ไม่ระบุเงื่อนไขการส่ง'
            
    df_sales[ship_col] = df_sales[ship_col].astype(str).str.strip().fillna('ไม่ระบุ')
    
    # 🌟 [เพิ่มใหม่] ยุบรวมเงื่อนไขการจัดส่ง ถ้ามีคำว่า "รับเอง" ให้เปลี่ยนเป็น "รับเอง" คำเดียว
    df_sales.loc[df_sales[ship_col].str.contains('รับเอง', case=False, na=False), ship_col] = 'รับเอง'
    
except Exception as e:
    print(f"❌ Error โหลดไฟล์ Sales: {e}")
    exit()

# ========================================================
# 🎯 ส่วนการวิเคราะห์ (Shipping Condition Analysis)
# ========================================================

# 1. สรุปภาพรวมปริมาณการขาย (Total Volume) แยกตามปี
total_vol_24 = df_sales[df_sales['Year'] == 2024]['Net Weight'].sum()
total_vol_25 = df_sales[df_sales['Year'] == 2025]['Net Weight'].sum()

# 2. กรุ๊ปข้อมูลตาม Shipping Condition และ ปี (หาผลรวม Net Weight)
ship_group = df_sales.groupby([ship_col, 'Year'])['Net Weight'].sum().unstack(fill_value=0)

# จัดการกรณีบางปีไม่มีข้อมูล
if 2024 not in ship_group.columns: ship_group[2024] = 0
if 2025 not in ship_group.columns: ship_group[2025] = 0

# 3. คำนวณสัดส่วน (Mix %) และผลต่าง (Variance)
ship_group['Vol_Diff (KG)'] = ship_group[2025] - ship_group[2024]
ship_group['%_Change'] = np.where(ship_group[2024] > 0, (ship_group['Vol_Diff (KG)'] / ship_group[2024]) * 100, 100)

ship_group['Mix_2024 (%)'] = (ship_group[2024] / total_vol_24 * 100) if total_vol_24 > 0 else 0
ship_group['Mix_2025 (%)'] = (ship_group[2025] / total_vol_25 * 100) if total_vol_25 > 0 else 0

# จัดเรียงตามปริมาณปี 2025 จากมากไปน้อย
ship_group = ship_group.sort_values(by=2025, ascending=False)

# ========================================================
# 📝 พิมพ์ Output ตอบออดิท (Copy & Paste ได้เลย)
# ========================================================
print(f"\n====================================================================")
print(f"📝 สรุปการวิเคราะห์เงื่อนไขการจัดส่ง (Shipping Condition Analysis)")
print(f"วัตถุประสงค์: เพื่อประเมินความสมเหตุสมผลของค่าใช้จ่ายในการขนส่ง (Freight Cost)")
print(f"====================================================================\n")

print(f"📌 ภาพรวมปริมาณขายสุทธิ (Total Volume)")
print(f"  - ปริมาณขายรวม ปี 2024: {total_vol_24:,.2f} KG")
print(f"  - ปริมาณขายรวม ปี 2025: {total_vol_25:,.2f} KG\n")

print(f"🚚 เจาะลึกปริมาณขายแยกตามรูปแบบการจัดส่ง (Volume by Shipping Condition)")
print("-" * 65)

# ลูปเพื่อแสดงผลทีละรูปแบบการจัดส่ง
for condition, row in ship_group.iterrows():
    print(f"📍 รูปแบบ: {condition}")
    print(f"    - ปี 2024: {row[2024]:,.2f} KG (คิดเป็น {row['Mix_2024 (%)']:,.1f}% ของยอดรวม)")
    print(f"    - ปี 2025: {row[2025]:,.2f} KG (คิดเป็น {row['Mix_2025 (%)']:,.1f}% ของยอดรวม)")
    
    trend = "เพิ่มขึ้น" if row['Vol_Diff (KG)'] > 0 else "ลดลง"
    print(f"    > เทียบ YoY: ปริมาณ {trend} {abs(row['Vol_Diff (KG)']):,.2f} KG (เปลี่ยนแปลง {row['%_Change']:,.1f}%)")
    print("-" * 65)

print("\n💡 แนวทางการสรุปผลกระทบต่อค่าขนส่ง (Freight Cost Implication):")
print(f"  - หากสัดส่วน (%) ของ 'รับเอง' ในปี 2025 ปรับตัว 'สูงขึ้น' เมื่อเทียบกับปี 2024 -> ต้นทุนค่าขนส่งของบริษัทควรจะมีสัดส่วนที่ลดลงเมื่อเทียบกับรายได้")
print(f"  - หากสัดส่วน (%) ของ 'บริษัทจัดส่งให้ (Delivery)' ปรับตัว 'สูงขึ้น' หรือมีการเติบโตของปริมาณ (KG) อย่างมีนัยสำคัญ -> ค่าขนส่งโดยรวมของบริษัทในปี 2025 ย่อมปรับตัวสูงขึ้นตาม Volume ที่เพิ่มขึ้น")

print(f"\n====================================================================")