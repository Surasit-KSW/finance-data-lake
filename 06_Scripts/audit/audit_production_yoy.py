import pandas as pd
import numpy as np
import os

print("⏳ กำลังโหลดและประมวลผลข้อมูล Production 2023 - 2025...")

# ========================================================
# 1. โหลดข้อมูล Production (Silver Layer)
# ========================================================
df_list = []

for year in [2023, 2024, 2025]:
    file_path = f'./02_Silver_Cleaned/master_production_{year}.parquet'
    if os.path.exists(file_path):
        try:
            df = pd.read_parquet(file_path, engine='pyarrow')
            df['Year'] = year
            df_list.append(df)
            print(f"  ✅ โหลดข้อมูลปี {year} สำเร็จ")
        except Exception as e:
            print(f"  ❌ ไม่สามารถโหลดไฟล์ปี {year} ได้: {e}")
    else:
        print(f"  ⚠️ ไม่พบไฟล์ master_production_{year}.parquet (ข้ามการประมวลผล)")

if not df_list:
    print("❌ ไม่มีข้อมูลสำหรับการวิเคราะห์เลย โปรดตรวจสอบโฟลเดอร์")
    exit()

# รวมข้อมูลที่โหลดได้ทั้งหมด
df_prod = pd.concat(df_list, ignore_index=True)

# ========================================================
# 2. จัดเตรียมคอลัมน์และทำความสะอาดข้อมูล (Data Cleansing)
# ========================================================
# แปลงยอดผลิตเป็นตัวเลข
df_prod['Prod_Qty'] = pd.to_numeric(df_prod.get('Actual GR QTY', 0), errors='coerce').fillna(0)

# ตัดช่องว่างของ Plant
df_prod['Plant'] = df_prod.get('Plant', 'Unspecified').astype(str).str.strip()

# หาคอลัมน์ชื่อกลุ่มสินค้า (รองรับหลายชื่อเผื่อหน้าจอ SAP ดึงมาไม่เหมือนกัน)
if 'ประเภทกลุ่มสินค้า (Mat Group Name)' in df_prod.columns:
    mat_col = 'ประเภทกลุ่มสินค้า (Mat Group Name)'
elif 'Mat Group Des.' in df_prod.columns:
    mat_col = 'Mat Group Des.'
elif 'Material Group' in df_prod.columns:
    mat_col = 'Material Group'
else:
    mat_col = 'Material' # ถ้าไม่มีเลยใช้รหัสสินค้าแทน

df_prod['Mat_Group'] = df_prod[mat_col].fillna('ไม่ระบุ').astype(str)

# ========================================================
# 3. จัดกลุ่มและคำนวณ Variance (Pivot Table)
# ========================================================
print("🔄 กำลังคำนวณยอดรวมและผลต่าง (Variance)...")

# Group by Plant, Mat_Group, Year
pivot_df = df_prod.groupby(['Plant', 'Mat_Group', 'Year'])['Prod_Qty'].sum().unstack(fill_value=0)

# เช็คว่ามีคอลัมน์ปีครบไหม ถ้าไม่มีให้เติม 0
for y in [2023, 2024, 2025]:
    if y not in pivot_df.columns:
        pivot_df[y] = 0

# คำนวณผลต่าง (Variance) และ % Change
pivot_df['Diff_23_24 (KG)'] = pivot_df[2024] - pivot_df[2023]
pivot_df['%_Change_23_24'] = np.where(pivot_df[2023] > 0, (pivot_df['Diff_23_24 (KG)'] / pivot_df[2023]), 0)

pivot_df['Diff_24_25 (KG)'] = pivot_df[2025] - pivot_df[2024]
pivot_df['%_Change_24_25'] = np.where(pivot_df[2024] > 0, (pivot_df['Diff_24_25 (KG)'] / pivot_df[2024]), 0)

# รีเซ็ต Index เพื่อให้กลายเป็นตารางปกติ (Flat Table) สำหรับ Export Excel
output_df = pivot_df.reset_index()

# จัดเรียงคอลัมน์ให้ดูง่าย
columns_order = [
    'Plant', 'Mat_Group', 
    2023, 2024, 'Diff_23_24 (KG)', '%_Change_23_24', 
    2025, 'Diff_24_25 (KG)', '%_Change_24_25'
]
output_df = output_df[columns_order]

# เรียงลำดับข้อมูลตาม Plant และยอดผลิตปี 2025 จากมากไปน้อย
output_df = output_df.sort_values(by=['Plant', 2025], ascending=[True, False])

# ========================================================
# 4. บันทึกผลลัพธ์ลง Excel (Export to Excel)
# ========================================================
output_path = './02_Silver_Cleaned/Production_Summary_Plant_MatGroup.xlsx'

# ใช้ ExcelWriter เพื่อปรับแต่ง Format เล็กน้อย
with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
    output_df.to_excel(writer, sheet_name='Production_Summary', index=False)
    
    # ดึง worksheet ออกมาปรับ Format
    worksheet = writer.sheets['Production_Summary']
    
    # ปรับ Format ตัวเลขให้มีคอมม่า
    for row in range(2, len(output_df) + 2):
        worksheet.cell(row=row, column=3).number_format = '#,##0.00' # 2023
        worksheet.cell(row=row, column=4).number_format = '#,##0.00' # 2024
        worksheet.cell(row=row, column=5).number_format = '#,##0.00' # Diff 23-24
        worksheet.cell(row=row, column=6).number_format = '0.00%'    # Pct 23-24
        worksheet.cell(row=row, column=7).number_format = '#,##0.00' # 2025
        worksheet.cell(row=row, column=8).number_format = '#,##0.00' # Diff 24-25
        worksheet.cell(row=row, column=9).number_format = '0.00%'    # Pct 24-25

print(f"💾 สร้างไฟล์ Excel สำเร็จเรียบร้อยแล้ว!")
print(f"📂 ไฟล์ถูกบันทึกไว้ที่: {output_path}")