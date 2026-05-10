# %%
# 1. โหลดข้อมูล Raw Data
import pandas as pd
df = pd.read_excel('sap_raw_sales.xlsx')

# %%
# 2. แปลงวันที่และดึงข้อมูลปี (Year)
df['Billing Date'] = pd.to_datetime(df['Billing Date'])
df['Year'] = df['Billing Date'].dt.year

# %%
# 3. สร้าง Pivot Table สรุปยอดขายรายลูกค้าและรายสินค้า เทียบปี 2024 กับ 2025
pivot_sales = pd.pivot_table(df, 
                             index=['Customer Name', 'Material Description'], 
                             columns='Year', 
                             values='Net Value', 
                             aggfunc='sum', 
                             fill_value=0).reset_index()

# %%
# 4. คำนวณหาผลต่าง (Variance)
pivot_sales['Variance'] = pivot_sales[2025] - pivot_sales[2024]

# %%
# 5. กรองดูเฉพาะลูกค้าที่ยอดลดลง (เช่น บริษัท ไพร์ม สตีล มิลส์ จำกัด)
customer_a2 = pivot_sales[pivot_sales['Customer Name'] == 'บริษัท ไพร์ม สตีล มิลส์ จำกัด']

# %%
# 6. เรียงลำดับสินค้าที่ยอดหายไปมากที่สุด (ติดลบเยอะสุด)
top_dropped_items = customer_a2.sort_values(by='Variance').head(5)
print(top_dropped_items)