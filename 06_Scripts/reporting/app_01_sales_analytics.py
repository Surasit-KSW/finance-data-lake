# %%
# Cell 1: โหลดข้อมูลจากชั้น Silver
import pandas as pd
import os

print("กำลังโหลดข้อมูล Master Sales...")

# ใช้ relative path จาก project root (06_Scripts/reporting → 06_Scripts → project root)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
parquet_file_path = os.path.join(_PROJECT_ROOT, '02_Silver_Cleaned', 'master_sales_2025.parquet')

# เช็กก่อนว่ามีไฟล์นี้อยู่จริงไหม
if os.path.exists(parquet_file_path):
    df_sales = pd.read_parquet(parquet_file_path, engine='pyarrow')

    # แปลงคอลัมน์วันที่ให้เป็นรูปแบบ Datetime 
    df_sales['Billing Date'] = pd.to_datetime(df_sales['Billing Date'], errors='coerce')

    # สร้างคอลัมน์ 'Month' เพื่อใช้วิเคราะห์รายเดือน
    df_sales['Month'] = df_sales['Billing Date'].dt.month

    # แปลงคอลัมน์ตัวเลขให้คำนวณได้
    numeric_cols = ['Billed Qty', 'Net Value(THB)']
    for col in numeric_cols:
        df_sales[col] = pd.to_numeric(df_sales[col], errors='coerce').fillna(0)

    print(f"โหลดข้อมูลสำเร็จ! จำนวนทั้งหมด: {df_sales.shape[0]:,} Transaction")
else:
    print(f"❌ หาไฟล์ไม่เจอ กรุณาเช็กว่ามีไฟล์นี้อยู่ที่: {parquet_file_path}")

# %%
# Cell 2: วิเคราะห์ Product Mix และ Volume
print("--- สรุปยอดขายแยกตามกลุ่มสินค้า (Product Mix) ---")

# จัดกลุ่มตามชื่อกลุ่มสินค้า (Mat Group Des.) หรือชื่อสินค้า (Material Description)
product_mix = df_sales.groupby('Mat Group Des.').agg(
    Total_Volume_Qty=('Billed Qty', 'sum'),
    Total_Sales_THB=('Net Value(THB)', 'sum')
).reset_index()

# เรียงลำดับจากยอดขายมากไปน้อย
product_mix = product_mix.sort_values('Total_Sales_THB', ascending=False)

# คำนวณสัดส่วน % ของยอดขายแต่ละกลุ่ม
total_sales = product_mix['Total_Sales_THB'].sum()
product_mix['% of Total Sales'] = (product_mix['Total_Sales_THB'] / total_sales) * 100

# แสดงผล Top 10 กลุ่มสินค้า
print(product_mix.head(10))

# %%
# Cell 3: วิเคราะห์พฤติกรรมลูกค้า (Frequency)
print("--- วิเคราะห์ความถี่ในการสั่งซื้อของลูกค้า ---")

# จัดกลุ่มรายลูกค้า (ใช้ Sold-to Name)
customer_freq = df_sales.groupby('Sold-to Name').agg(
    Total_Sales_THB=('Net Value(THB)', 'sum'),
    Invoice_Count=('Billing No', 'nunique'), # นับจำนวนบิลที่ไม่ซ้ำกัน
    Active_Months=('Month', 'nunique')       # นับว่าซื้อกี่เดือนใน 1 ปี
).reset_index()

# เรียงตามลูกค้ารายใหญ่สุด
customer_freq = customer_freq.sort_values('Total_Sales_THB', ascending=False)

# แบ่งกลุ่มลูกค้าเบื้องต้น: ซื้อมากกว่า 6 เดือน = ลูกค้าประจำ (Recurring), ซื้อ 1-2 เดือน = ขาจร/โปรเจกต์ (Project-based)
def check_behavior(months):
    if months >= 6:
        return 'ลูกค้าประจำ (Recurring)'
    elif months <= 2:
        return 'ขาจร/โปรเจกต์ (Project-based)'
    else:
        return 'ซื้อเป็นช่วงๆ (Seasonal)'

customer_freq['Customer_Type'] = customer_freq['Active_Months'].apply(check_behavior)

print(customer_freq.head(10))

# %%
# Cell 4: Export เป็นรายงาน Excel (Working Paper)
import pandas as pd
import os

output_report = './03_Gold_DataMarts/Audit_Sales_Analysis_2025_v2.xlsx'

# ตรวจสอบและสร้างโฟลเดอร์ถ้ายังไม่มี
if not os.path.exists('./03_Gold_DataMarts'):
    os.makedirs('./03_Gold_DataMarts')

print("กำลังสร้างไฟล์รายงาน Excel...")

# ใช้ ExcelWriter เพื่อเซฟหลายๆ Sheet ในไฟล์เดียว
with pd.ExcelWriter(output_report, engine='openpyxl') as writer:
    product_mix.to_excel(writer, sheet_name='Product_Mix', index=False)
    customer_freq.to_excel(writer, sheet_name='Customer_Frequency', index=False)

print(f"🎉 สร้างรายงานสำเร็จ! เปิดดูได้ที่: {output_report}")