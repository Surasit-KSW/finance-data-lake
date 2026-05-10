import pandas as pd
import numpy as np
import os
import datetime
import string

pd.set_option('display.float_format', '{:,.2f}'.format)

# กำหนด project root (06_Scripts/audit → 06_Scripts → project root)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
_SILVER = os.path.join(_PROJECT_ROOT, "02_Silver_Cleaned")
_BRONZE_AR = os.path.join(_PROJECT_ROOT, "01_Bronze_Raw", "AR_Data")

print("⏳ กำลังโหลดและประมวลผลข้อมูล Sales & AR (2023 - 2025)...")

# ========================================================
# 1. โหลดและรวมข้อมูล Sales (2023-2025)
# ========================================================
sales_list = []
for year in [2023, 2024, 2025]:
    path = os.path.join(_SILVER, f'master_sales_{year}.parquet')
    if os.path.exists(path):
        df = pd.read_parquet(path, engine='pyarrow')
        df['Year'] = year
        sales_list.append(df)

if not sales_list:
    print("❌ ไม่พบไฟล์ Sales เลย")
    exit()

df_sales = pd.concat(sales_list, ignore_index=True)

# แปลงยอดขายและดึงชื่อลูกค้า
df_sales['Net Value(THB)'] = pd.to_numeric(df_sales['Net Value(THB)'], errors='coerce').fillna(0)
df_sales['Customer'] = df_sales['Sold-to Name'].astype(str).str.strip()

# 🌟 [NEW] เตรียมข้อมูลวันที่และชื่อสินค้า สำหรับวิเคราะห์รายเดือน
df_sales['Billing Date'] = pd.to_datetime(df_sales.get('Billing Date'), errors='coerce')
df_sales['Month'] = df_sales['Billing Date'].dt.month

# ค้นหาคอลัมน์ชื่อสินค้าที่ถูกต้อง
if 'Mat Group Name' in df_sales.columns:
    prod_col = 'Mat Group Name'
elif 'Material Description' in df_sales.columns:
    prod_col = 'Material Description'
else:
    prod_col = 'Material' # ค่าเริ่มต้นถ้าหาไม่เจอ
df_sales['Product_Group'] = df_sales.get(prod_col, 'ไม่ระบุ').astype(str).str.strip()

# สร้าง Pivot Table สำหรับ AR
sales_pivot = df_sales.groupby(['Customer', 'Year'])['Net Value(THB)'].sum().unstack(fill_value=0)
min_sales_year = df_sales.groupby('Customer')['Year'].min()

# 🌟 [NEW] สร้าง Pivot Table วิเคราะห์ยอดขายรายเดือนแยกตามสินค้า
df_sales_valid_month = df_sales.dropna(subset=['Month']).copy()
sales_monthly_pivot = df_sales_valid_month.pivot_table(
    index=['Year', 'Product_Group'],
    columns='Month',
    values='Net Value(THB)',
    aggfunc='sum',
    fill_value=0
).reset_index()

# เปลี่ยนเลขเดือนให้เป็นชื่อเดือนให้อ่านง่าย
month_dict = {1:'Jan', 2:'Feb', 3:'Mar', 4:'Apr', 5:'May', 6:'Jun', 
              7:'Jul', 8:'Aug', 9:'Sep', 10:'Oct', 11:'Nov', 12:'Dec'}
sales_monthly_pivot.rename(columns=month_dict, inplace=True)

# เติมเดือนที่อาจจะไม่มีข้อมูลให้ครบ 12 เดือน (กัน Error)
for m in month_dict.values():
    if m not in sales_monthly_pivot.columns:
        sales_monthly_pivot[m] = 0

# รวมยอด Total ทั้งปีของสินค้านั้นๆ และจัดเรียง
month_cols = list(month_dict.values())
sales_monthly_pivot['Total_Year'] = sales_monthly_pivot[month_cols].sum(axis=1)
sales_monthly_pivot = sales_monthly_pivot[['Year', 'Product_Group'] + month_cols + ['Total_Year']]
sales_monthly_pivot = sales_monthly_pivot.sort_values(by=['Year', 'Total_Year'], ascending=[False, False])

# ========================================================
# 2. โหลดและรวมข้อมูล AR (2023-2025)
# ========================================================
ar_path = _BRONZE_AR
ar_list = []

for year in [2023, 2024, 2025]:
    path = os.path.join(ar_path, f'AR_{year}.XLSX')
    if os.path.exists(path):
        df = pd.read_excel(path, engine='openpyxl')
        df['Year'] = year
        ar_list.append(df)

if not ar_list:
    print("❌ ไม่พบไฟล์ AR เลย")
    exit()

df_ar = pd.concat(ar_list, ignore_index=True)
df_ar['Company Code Currency Value'] = pd.to_numeric(df_ar['Company Code Currency Value'], errors='coerce').fillna(0)
df_ar['Clearing Date'] = pd.to_datetime(df_ar['Clearing Date'], errors='coerce')
df_ar['Customer'] = df_ar['Customer Account: Name 1'].astype(str).str.strip()
df_ar['Days 1'] = pd.to_numeric(df_ar.get('Days 1', 0), errors='coerce').fillna(0)

min_ar_year = df_ar.groupby('Customer')['Year'].min()

# ========================================================
# 3. ประมวลผล AR (ยอดคงค้าง, เครดิตเทอม และ ปีเริ่มต้น)
# ========================================================
term_pivot = df_ar.groupby(['Customer', 'Year'])['Days 1'].max().unstack(fill_value=0)

open_ar_list = []
for year in [2023, 2024, 2025]:
    open_items = df_ar[(df_ar['Year'] == year) & (df_ar['Clearing Date'].isna() | (df_ar['Clearing Date'].dt.year > year))]
    open_grouped = open_items.groupby('Customer')['Company Code Currency Value'].sum().reset_index()
    open_grouped['Year'] = year
    open_ar_list.append(open_grouped)

df_open_ar = pd.concat(open_ar_list, ignore_index=True)
ar_pivot = df_open_ar.groupby(['Customer', 'Year'])['Company Code Currency Value'].sum().unstack(fill_value=0)

first_year_df = pd.concat([min_sales_year, min_ar_year], axis=1, keys=['Sales_Year', 'AR_Year'])
first_year_df['First_Active_Year'] = first_year_df[['Sales_Year', 'AR_Year']].min(axis=1)

# ========================================================
# 4. ประกอบร่างตาราง Master สำหรับ AR & Sales
# ========================================================
print("🔄 กำลังคำนวณตัวชี้วัด (DSO, Growth, Relationship)...")

for y in [2023, 2024, 2025]:
    if y not in sales_pivot.columns: sales_pivot[y] = 0
    if y not in ar_pivot.columns: ar_pivot[y] = 0
    if y not in term_pivot.columns: term_pivot[y] = 0

all_customers = sorted(list(set(sales_pivot.index) | set(ar_pivot.index)))
master_df = pd.DataFrame(index=all_customers)

master_df['First_Active_Year'] = first_year_df['First_Active_Year']
current_year = 2026 
master_df['Years_of_Relationship'] = current_year - master_df['First_Active_Year']

master_df['Sales_2023'] = sales_pivot[2023]
master_df['Sales_2024'] = sales_pivot[2024]
master_df['Sales_2025'] = sales_pivot[2025]
master_df['AR_End_2023'] = ar_pivot[2023]
master_df['AR_End_2024'] = ar_pivot[2024]
master_df['AR_End_2025'] = ar_pivot[2025]
master_df['Credit_Term_2025'] = term_pivot[2025]

master_df = master_df.fillna(0)

master_df['Sales_Growth_24_25(%)'] = np.where(master_df['Sales_2024'] > 0, (master_df['Sales_2025'] - master_df['Sales_2024']) / master_df['Sales_2024'], 0)
master_df['AR_Growth_24_25(%)'] = np.where(master_df['AR_End_2024'] > 0, (master_df['AR_End_2025'] - master_df['AR_End_2024']) / master_df['AR_End_2024'], 0)
master_df['%AR_to_Sales_2025'] = np.where(master_df['Sales_2025'] > 0, master_df['AR_End_2025'] / master_df['Sales_2025'], 0)
master_df['Est_DSO_2025(Days)'] = np.where(master_df['Sales_2025'] > 0, (master_df['AR_End_2025'] / master_df['Sales_2025']) * 365, 0)

master_df['Risk_Flag'] = np.where(
    (master_df['Est_DSO_2025(Days)'] - master_df['Credit_Term_2025'] > 30) & (master_df['AR_End_2025'] > 0), 
    np.where(master_df['Years_of_Relationship'] <= 1, '🚨 High Risk (New Customer)', '⚠️ High DSO Risk'), 
    'Normal'
)

master_df = master_df.reset_index().rename(columns={'index': 'Customer_Name'})
master_df = master_df.sort_values(by='AR_End_2025', ascending=False)

# ========================================================
# 5. Export to Excel (เพิ่ม Sheet 2: ยอดขายรายสินค้าแยกเดือน)
# ========================================================
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
output_path = f'./02_Silver_Cleaned/AR_Sales_Analytics_{timestamp}.xlsx'

try:
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # ---- Sheet 1: AR & Sales Analytics ----
        master_df.to_excel(writer, sheet_name='AR_Analytics', index=False)
        ws_ar = writer.sheets['AR_Analytics']
        
        number_cols = ['D', 'E', 'F', 'G', 'H', 'I'] 
        pct_cols = ['K', 'L', 'M'] 
        
        for row in range(2, len(master_df) + 2):
            ws_ar[f"B{row}"].number_format = '0' 
            ws_ar[f"C{row}"].number_format = '0' 
            for col in number_cols:
                ws_ar[f"{col}{row}"].number_format = '#,##0.00'
            for col in pct_cols:
                ws_ar[f"{col}{row}"].number_format = '0.00%'
            ws_ar[f"N{row}"].number_format = '#,##0'

        # 🌟 [NEW] ---- Sheet 2: ยอดขายสินค้ารายเดือน ----
        sales_monthly_pivot.to_excel(writer, sheet_name='Sales_Monthly', index=False)
        ws_sales = writer.sheets['Sales_Monthly']
        
        # จัด Format ให้คอลัมน์ C ถึง O (Jan ถึง Total) เป็นตัวเลขมีคอมม่า
        sales_format_cols = list(string.ascii_uppercase)[2:15] # ['C', 'D', 'E', ... 'O']
        for row in range(2, len(sales_monthly_pivot) + 2):
            for col in sales_format_cols:
                ws_sales[f"{col}{row}"].number_format = '#,##0.00'

    print(f"💾 สร้างรายงานวิเคราะห์ AR & Sales สำเร็จเรียบร้อยแล้ว!")
    print(f"📂 ไฟล์ถูกสร้างใหม่ด้วยชื่อ: {output_path}")
    print(f"====================================================================")

except PermissionError:
    print(f"\n❌ Error: ไม่สามารถบันทึกไฟล์ได้! กรุณาปิดโปรแกรม Excel ที่เปิดไฟล์ค้างไว้แล้วรันใหม่")