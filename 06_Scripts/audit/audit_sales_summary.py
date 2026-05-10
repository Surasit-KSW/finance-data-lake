import pandas as pd
import numpy as np
import calendar
import os
import datetime
import string

# ตั้งค่าให้ Pandas แสดงผลจุดทศนิยม 2 ตำแหน่ง
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
    
    df_sales['Net Value(THB)'] = pd.to_numeric(df_sales['Net Value(THB)'], errors='coerce').fillna(0)
    df_sales['Net Weight'] = pd.to_numeric(df_sales['Net Weight'], errors='coerce').fillna(0)
    
    # แปลงหน่วยเป็น ตัน และ ล้านบาท
    df_sales['Vol_Ton'] = df_sales['Net Weight'] / 1000
    df_sales['Amount_MB'] = df_sales['Net Value(THB)'] / 1000000
    
    # หาคอลัมน์ชื่อกลุ่มสินค้า
    group_col = 'Mat Group Des.' if 'Mat Group Des.' in df_sales.columns else 'Material Group'
    if group_col not in df_sales.columns:
        group_col = 'Material'
        
    df_sales['Raw_Group'] = df_sales.get(group_col, df_sales.get('Material', 'ไม่ระบุ')).fillna('ไม่ระบุ')
    
    # 🌟 [NEW] หาคอลัมน์ชื่อลูกค้าเพื่อใช้คัดกรอง Related Party
    cust_col = 'Sold-to Name' if 'Sold-to Name' in df_sales.columns else 'Customer'
    df_sales['Customer_Name'] = df_sales.get(cust_col, '').astype(str).str.strip()
    
except Exception as e:
    print(f"❌ Error โหลดไฟล์ Sales: {e}")
    exit()

# ========================================================
# 2. ฟังก์ชันจัดกลุ่มอัจฉริยะ (Smart Grouping)
# ========================================================
def smart_group(name):
    words = str(name).strip().split()
    if len(words) > 1:
        return f"{words[0]} {words[-1]}"
    elif len(words) == 1:
        return words[0]
    else:
        return "ไม่ระบุ"

print("🧠 กำลังจัดกลุ่มสินค้าแบบอัจฉริยะ...")
df_sales['Smart_Group'] = df_sales['Raw_Group'].apply(smart_group)

# ========================================================
# 🎯 3. ดึงข้อมูลเดือน (Extract Month)
# ========================================================
print("📅 กำลังดึงข้อมูลเดือนจากคอลัมน์วันที่...")
target_date_col = 'Billing Date' 

if target_date_col in df_sales.columns:
    df_sales['Date'] = pd.to_datetime(df_sales[target_date_col], errors='coerce')
else:
    possible_dates = [col for col in df_sales.columns if 'date' in col.lower()]
    if possible_dates:
        target_date_col = possible_dates[0]
        df_sales['Date'] = pd.to_datetime(df_sales[target_date_col], errors='coerce')
    else:
        print("❌ ไม่พบคอลัมน์วันที่สำหรับดึงเดือน กรุณาตรวจสอบข้อมูล")
        exit()

# สร้างคอลัมน์เดือน (1-12) และกรองข้อมูล
df_sales['Month'] = df_sales['Date'].dt.month.fillna(0).astype(int)
df_sales = df_sales[df_sales['Month'] > 0]

month_names = {i: calendar.month_abbr[i] for i in range(1, 13)}

# ========================================================
# 🌟 [NEW] คัดแยกลูกค้าที่เป็น Related Parties
# ========================================================
related_companies = [
    "บริษัท ไพร์ม สตีล มิลล์ จำกัด",
    "บริษัท แกรนด์ เอเซีย สตีลโพรเซสซิ่ง เซ็นเตอร์ จำกัด"
]

is_related = df_sales['Customer_Name'].isin(related_companies)
df_related = df_sales[is_related].copy()
df_general = df_sales[~is_related].copy()

# ========================================================
# 📊 4. สร้าง Pivot DataFrames สำหรับ Excel
# ========================================================
print("🔄 กำลังเตรียมตารางข้อมูลสำหรับ Excel...")

def prepare_pivot_for_excel(df, value_col):
    # ป้องกันกรณีที่ไม่มีข้อมูลในกลุ่มนั้นๆ เลย
    if df.empty:
        empty_cols = ['Year', 'Smart_Group'] + list(month_names.values()) + ['Total_Year']
        return pd.DataFrame(columns=empty_cols)
        
    # Pivot ข้อมูลโดยใช้ Year และ Smart_Group เป็นแกน Y
    pivot = df.pivot_table(
        index=['Year', 'Smart_Group'],
        columns='Month',
        values=value_col,
        aggfunc='sum',
        fill_value=0
    ).reset_index()
    
    # เปลี่ยนชื่อคอลัมน์จากเลข 1-12 เป็น Jan-Dec
    pivot.rename(columns=month_names, inplace=True)
    
    # เติมเดือนที่หายไปให้ครบ 12 เดือน (กัน Error)
    for m in month_names.values():
        if m not in pivot.columns:
            pivot[m] = 0
            
    # เรียงคอลัมน์ให้ถูกต้อง
    cols_order = ['Year', 'Smart_Group'] + list(month_names.values())
    pivot = pivot[cols_order]
    
    # รวมยอดทั้งปี (Total Year)
    month_cols = list(month_names.values())
    pivot['Total_Year'] = pivot[month_cols].sum(axis=1)
    
    # เรียงลำดับตามปี (ล่าสุดขึ้นก่อน) และยอดขายทั้งปี (มากไปน้อย)
    pivot = pivot.sort_values(by=['Year', 'Total_Year'], ascending=[False, False])
    
    return pivot

# สร้าง Pivot ของฝั่งลูกค้าทั่วไป (General)
df_rev_gen = prepare_pivot_for_excel(df_general, 'Amount_MB')
df_vol_gen = prepare_pivot_for_excel(df_general, 'Vol_Ton')

# สร้าง Pivot ของฝั่ง Related Parties
df_rev_rel = prepare_pivot_for_excel(df_related, 'Amount_MB')
df_vol_rel = prepare_pivot_for_excel(df_related, 'Vol_Ton')

# ========================================================
# 💾 5. ส่งออกเป็นไฟล์ Excel (Export)
# ========================================================
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
output_path = f'./02_Silver_Cleaned/Monthly_Sales_Summary_{timestamp}.xlsx'

# จับคู่ DataFrame กับชื่อ Sheet ที่ต้องการสร้าง
sheets_to_export = {
    'Rev_General_MB': df_rev_gen,
    'Vol_General_Ton': df_vol_gen,
    'Rev_Related_MB': df_rev_rel,
    'Vol_Related_Ton': df_vol_rel
}

try:
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        format_cols = list(string.ascii_uppercase)[2:15] # ['C', 'D', 'E', ... 'O'] สำหรับเดือน Jan-Dec และ Total
        
        # วนลูปสร้าง Sheet และใส่ Format ตัวเลข
        for sheet_name, df_sheet in sheets_to_export.items():
            df_sheet.to_excel(writer, sheet_name=sheet_name, index=False)
            ws = writer.sheets[sheet_name]
            
            # ใส่ Format #,##0.00
            for row in range(2, len(df_sheet) + 2):
                for col in format_cols:
                    ws[f"{col}{row}"].number_format = '#,##0.00'

    print(f"\n✅ สร้างรายงาน Excel สำเร็จเรียบร้อยแล้ว!")
    print(f"📂 ไฟล์ถูกบันทึกไว้ที่: {output_path}")
    print(f"📊 โครงสร้างไฟล์มี 4 Sheets:")
    print(f"   - Rev_General_MB (รายได้ลูกค้าภายนอก)")
    print(f"   - Vol_General_Ton (ปริมาณลูกค้าภายนอก)")
    print(f"   - Rev_Related_MB (รายได้กิจการที่เกี่ยวข้องกัน)")
    print(f"   - Vol_Related_Ton (ปริมาณกิจการที่เกี่ยวข้องกัน)")
    print(f"====================================================================")

except PermissionError:
    print(f"\n❌ Error: ไม่สามารถบันทึกไฟล์ได้!")
    print(f"   ระบบตรวจสอบพบว่าไฟล์ถูกเปิดค้างไว้ กรุณาปิดโปรแกรม Excel แล้วกดรันใหม่อีกครั้งครับ")