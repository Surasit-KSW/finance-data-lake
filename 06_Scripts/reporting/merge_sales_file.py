import pandas as pd
import numpy as np
import os

print("⏳ กำลังโหลดและประมวลผลข้อมูล Sales 2023 - 2025...")

# ========================================================
# 1. โหลดข้อมูล Sales (Silver Layer) แบบ 3 ปี
# ========================================================
try:
    df_23 = pd.read_parquet('./02_Silver_Cleaned/master_sales_2023.parquet', engine='pyarrow')
    df_24 = pd.read_parquet('./02_Silver_Cleaned/master_sales_2024.parquet', engine='pyarrow')
    df_25 = pd.read_parquet('./02_Silver_Cleaned/master_sales_2025.parquet', engine='pyarrow')
    
    df_23['Year'] = 2023
    df_24['Year'] = 2024
    df_25['Year'] = 2025
    
    df_sales = pd.concat([df_23, df_24, df_25], ignore_index=True)
    
    df_sales['Net Value(THB)'] = pd.to_numeric(df_sales['Net Value(THB)'], errors='coerce').fillna(0)
    df_sales['Net Weight'] = pd.to_numeric(df_sales['Net Weight'], errors='coerce').fillna(0)
    
    df_sales['Vol_Ton'] = df_sales['Net Weight'] / 1000
    df_sales['Amount_MB'] = df_sales['Net Value(THB)'] / 1000000
    
    group_col = 'Mat Group Des.' if 'Mat Group Des.' in df_sales.columns else 'Material Group'
    if group_col not in df_sales.columns:
        group_col = 'Material'
        
    df_sales['Product_Group'] = df_sales.get(group_col, df_sales.get('Material', 'ไม่ระบุ')).fillna('ไม่ระบุ')
    
except Exception as e:
    print(f"❌ Error โหลดไฟล์ Sales: {e}")
    exit()

# ========================================================
# 🎯 2. จัดเตรียมข้อมูลสำหรับ Excel
# ========================================================
print("กำลังคำนวณ Variance และจัดรูปแบบตารางสำหรับ Excel...")

# จัดกลุ่มตาม Product_Group และ Year
group_summary = df_sales.groupby(['Product_Group', 'Year']).agg(
    Revenue_MB=('Amount_MB', 'sum'),
    Volume_Ton=('Vol_Ton', 'sum')
).unstack(fill_value=0)

# จัดการชื่อคอลัมน์ให้เป็นชั้นเดียว (Flatten MultiIndex) เพื่อให้ Excel อ่านง่าย
group_summary.columns = [f"{col[0]}_{col[1]}" for col in group_summary.columns]
group_summary.reset_index(inplace=True)

# เติมคอลัมน์ปีที่อาจจะหายไป (กรณีบางปีไม่มีข้อมูล)
expected_cols = ['Revenue_MB_2023', 'Revenue_MB_2024', 'Revenue_MB_2025', 
                 'Volume_Ton_2023', 'Volume_Ton_2024', 'Volume_Ton_2025']
for col in expected_cols:
    if col not in group_summary.columns:
        group_summary[col] = 0

# คำนวณ Variance ยอดขาย (2024 vs 2023)
group_summary['Var_Rev_24_vs_23_MB'] = group_summary['Revenue_MB_2024'] - group_summary['Revenue_MB_2023']
group_summary['Var_Rev_24_vs_23_%'] = np.where(group_summary['Revenue_MB_2023'] > 0, 
                                               (group_summary['Var_Rev_24_vs_23_MB'] / group_summary['Revenue_MB_2023']) * 100, 0)

# คำนวณ Variance ยอดขาย (2025 vs 2024)
group_summary['Var_Rev_25_vs_24_MB'] = group_summary['Revenue_MB_2025'] - group_summary['Revenue_MB_2024']
group_summary['Var_Rev_25_vs_24_%'] = np.where(group_summary['Revenue_MB_2024'] > 0, 
                                               (group_summary['Var_Rev_25_vs_24_MB'] / group_summary['Revenue_MB_2024']) * 100, 0)

# คำนวณสัดส่วนการขายของปี 2025 (Product Mix %)
total_rev_25 = group_summary['Revenue_MB_2025'].sum()
group_summary['Mix_2025_%'] = np.where(total_rev_25 > 0, (group_summary['Revenue_MB_2025'] / total_rev_25) * 100, 0)

# เรียงลำดับคอลัมน์ใหม่ให้สวยงามเวลาเปิดใน Excel
final_columns = [
    'Product_Group',
    'Volume_Ton_2023', 'Revenue_MB_2023',
    'Volume_Ton_2024', 'Revenue_MB_2024',
    'Var_Rev_24_vs_23_MB', 'Var_Rev_24_vs_23_%',
    'Volume_Ton_2025', 'Revenue_MB_2025', 'Mix_2025_%',
    'Var_Rev_25_vs_24_MB', 'Var_Rev_25_vs_24_%'
]
group_summary = group_summary[final_columns]

# เรียงลำดับจากยอดขายปี 2025 มากไปน้อย
group_summary = group_summary.sort_values(by='Revenue_MB_2025', ascending=False)

# ========================================================
# 💾 3. บันทึกเป็นไฟล์ Excel (ชั้น Gold Data Mart)
# ========================================================
# ตรวจสอบและสร้างโฟลเดอร์ถ้ายังไม่มี
output_folder = './03_Gold_DataMarts'
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

output_file = f'{output_folder}/Audit_Sales_Summary_23_24_25.xlsx'

print("กำลังสร้างไฟล์รายงาน Excel...")

# ใช้ ExcelWriter บันทึก
with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
    group_summary.to_excel(writer, sheet_name='Sales_by_Product_Group', index=False)

print(f"\n🎉 สร้างรายงานสำเร็จเรียบร้อย! เปิดดูไฟล์ได้ที่: {output_file}")