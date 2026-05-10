import pandas as pd
import numpy as np

# --- ⚙️ ตั้งค่าให้หน้าจอ Terminal ดูง่าย ---
pd.set_option('display.float_format', '{:,.2f}'.format)

print("⏳ กำลังโหลดและวิเคราะห์ข้อมูล...")
# 1. โหลดข้อมูล 2 ปี
df_24 = pd.read_parquet('./02_Silver_Cleaned/master_sales_2024.parquet', engine='pyarrow')
df_25 = pd.read_parquet('./02_Silver_Cleaned/master_sales_2025.parquet', engine='pyarrow')

df_24['Year'] = 2024
df_25['Year'] = 2025

# รวมร่าง
df_sales = pd.concat([df_24, df_25], ignore_index=True)

# 2. Clean ข้อมูลและคอลัมน์ที่ต้องการใช้งาน
df_sales['Net Value(THB)'] = pd.to_numeric(df_sales['Net Value(THB)'], errors='coerce').fillna(0)
df_sales['Net Weight'] = pd.to_numeric(df_sales['Net Weight'], errors='coerce').fillna(0) # 👈 ใช้ Net Weight เป็นปริมาณ
df_sales['Billing Date'] = pd.to_datetime(df_sales['Billing Date'], errors='coerce')

# เติมคำว่า "หน่วย" เป็นค่าตั้งต้นเผื่อมีบรรทัดที่ว่าง
if 'หน่วย Unit Price' in df_sales.columns:
    df_sales['หน่วย Unit Price'] = df_sales['หน่วย Unit Price'].fillna('หน่วย')
else:
    df_sales['หน่วย Unit Price'] = 'หน่วย'
    
df_sales['Mat Group Des.'] = df_sales.get('Mat Group Des.', 'Unknown Group').fillna('Unknown Group')

# ========================================================
# 🎯 ส่วนวิเคราะห์และสร้างข้อความตอบออดิท (ไม่รวม VAT)
# ========================================================
target_customer = 'บริษัท แกรนด์ เอเซีย สตีลโพรเซสซิ่ง เซ็นเตอร์ จำกัด'  # <--- เปลี่ยนชื่อลูกค้าตรงนี้

df_target = df_sales[df_sales['Sold-to Name'] == target_customer].copy()

if df_target.empty:
    print(f"❌ ไม่พบประวัติการซื้อของลูกค้ารายนี้ ({target_customer}) ทั้งในปี 2024 และ 2025")
else:
    # หาหน่วยนับหลักของลูกค้ารายนี้ (เผื่อเอาไปใช้ในสรุปภาพรวม)
    primary_unit = df_target['หน่วย Unit Price'].mode()[0] if not df_target.empty else 'หน่วย'

    # --- คำนวณข้อ 1: ภาพรวม (ยอด Net ไม่รวม VAT, ปริมาณจาก Net Weight) ---
    summary_yoy = df_target.groupby('Year').agg(
        Total_Qty=('Net Weight', 'sum'),
        Total_Amount=('Net Value(THB)', 'sum') 
    ).reset_index()

    data_dict = summary_yoy.set_index('Year').to_dict('index')
    qty_24 = data_dict.get(2024, {}).get('Total_Qty', 0)
    qty_25 = data_dict.get(2025, {}).get('Total_Qty', 0)
    amt_24 = data_dict.get(2024, {}).get('Total_Amount', 0)
    amt_25 = data_dict.get(2025, {}).get('Total_Amount', 0)
    
    price_24 = amt_24 / qty_24 if qty_24 > 0 else 0
    price_25 = amt_25 / qty_25 if qty_25 > 0 else 0

    def get_pct(old, new):
        if old == 0 and new > 0: return "N/A (ลูกค้าใหม่)"
        if old == 0 and new == 0: return "0.00%"
        pct = ((new - old) / old) * 100
        return f"{pct:,.2f}%"
        
    def get_trend_text(old, new):
        if old == 0 and new > 0: return "มีรายการสั่งซื้อใหม่"
        if old == 0 and new == 0: return "ไม่มีการเปลี่ยนแปลง"
        return "เพิ่มขึ้น" if new > old else "ลดลง"

    # --- คำนวณข้อ 2: กลุ่มสินค้า (ใช้ Mat Group Des.) ---
    prod_agg = df_target.groupby(['Mat Group Des.', 'Year']).agg(
        Amt=('Net Value(THB)', 'sum'),
        Qty=('Net Weight', 'sum')
    ).unstack(fill_value=0)
    
    prod_agg.columns = [f"{col[0]}_{col[1]}" for col in prod_agg.columns]
    
    for y in [2024, 2025]:
        if f'Amt_{y}' not in prod_agg.columns: prod_agg[f'Amt_{y}'] = 0
        if f'Qty_{y}' not in prod_agg.columns: prod_agg[f'Qty_{y}'] = 0
        
    prod_agg['Diff_Amt'] = prod_agg['Amt_2025'] - prod_agg['Amt_2024']
    prod_agg['Diff_Qty'] = prod_agg['Qty_2025'] - prod_agg['Qty_2024']
    
    top_inc = prod_agg[prod_agg['Diff_Amt'] > 0].sort_values('Diff_Amt', ascending=False).head(2)
    top_dec = prod_agg[prod_agg['Diff_Amt'] < 0].sort_values('Diff_Amt', ascending=True).head(2)

    # --- คำนวณข้อ 3: ความถี่ ---
    df_target['Month'] = df_target['Billing Date'].dt.month
    freq_yoy = df_target.groupby('Year').agg(
        Invoice_Count=('Billing No', 'nunique'),
        Active_Months=('Month', 'nunique')
    ).reset_index()
    freq_dict = freq_yoy.set_index('Year').to_dict('index')
    
    inv_24 = freq_dict.get(2024, {}).get('Invoice_Count', 0)
    inv_25 = freq_dict.get(2025, {}).get('Invoice_Count', 0)
    mo_24 = freq_dict.get(2024, {}).get('Active_Months', 0)
    mo_25 = freq_dict.get(2025, {}).get('Active_Months', 0)

    # ========================================================
    # 📝 พิมพ์ Output รูปแบบร้อยแก้ว (พร้อม Copy & Paste)
    # ========================================================
    print(f"\n====================================================================")
    print(f"📝 สรุปคำอธิบายความผันผวนของยอดขาย (Sales Variance Explanation)")
    print(f"ลูกค้าราย: {target_customer}")
    print(f"====================================================================\n")

    print("คำตอบข้อที่ 1: เปรียบเทียบปริมาณ, จำนวนเงิน และราคาขายเฉลี่ย (2024 vs 2025)")
    print(f"จากการเปรียบเทียบยอดขายของปี 2024 และ 2025 พบว่าภาพรวมยอดขาย {get_trend_text(amt_24, amt_25)} {get_pct(amt_24, amt_25)} (จาก {amt_24:,.2f} บาท เป็น {amt_25:,.2f} บาท) โดยมีรายละเอียดดังนี้:")
    print(f"  - ปริมาณขาย (Volume): {get_trend_text(qty_24, qty_25)} {get_pct(qty_24, qty_25)} (ปี 2024: {qty_24:,.2f} {primary_unit} -> ปี 2025: {qty_25:,.2f} {primary_unit})")
    print(f"  - ราคาขายเฉลี่ย (Price): {get_trend_text(price_24, price_25)} {get_pct(price_24, price_25)} (ปี 2024: {price_24:,.2f} บาท/{primary_unit} -> ปี 2025: {price_25:,.2f} บาท/{primary_unit})")
    print(f"  > สรุปสาเหตุหลัก: การเปลี่ยนแปลงของยอดขายเป็นผลมาจากปริมาณการสั่งซื้อที่{get_trend_text(qty_24, qty_25)} ควบคู่กับราคาขายเฉลี่ยที่{get_trend_text(price_24, price_25)}ตามสภาวะตลาด\n")

    print("คำตอบข้อที่ 2: สรุปยอดที่เปลี่ยนแปลงจำแนกตามกลุ่มสินค้า (Material Group)")
    if amt_25 > amt_24:
        print(f"ยอดขายที่เพิ่มขึ้นในปี 2025 ได้รับแรงหนุนหลักจากการสั่งซื้อกลุ่มสินค้าต่อไปนี้เพิ่มขึ้น:")
        for idx, row in top_inc.iterrows():
            qty_trend = "เพิ่มขึ้น" if row['Diff_Qty'] > 0 else "ลดลง"
            # หาหน่วยนับของกลุ่มสินค้านั้น
            unit_val = df_target[df_target['Mat Group Des.'] == idx]['หน่วย Unit Price'].iloc[0] if not df_target[df_target['Mat Group Des.'] == idx].empty else primary_unit
            print(f"  - {idx}: มียอดขายเพิ่มขึ้น {row['Diff_Amt']:,.2f} บาท (มาจากปริมาณขายที่{qty_trend} {abs(row['Diff_Qty']):,.2f} {unit_val})")
    elif amt_25 < amt_24:
        print(f"ยอดขายที่ลดลงในปี 2025 มีสาเหตุหลักมาจากการชะลอการสั่งซื้อในกลุ่มสินค้าต่อไปนี้:")
        for idx, row in top_dec.iterrows():
            qty_trend = "เพิ่มขึ้น" if row['Diff_Qty'] > 0 else "ลดลง"
            unit_val = df_target[df_target['Mat Group Des.'] == idx]['หน่วย Unit Price'].iloc[0] if not df_target[df_target['Mat Group Des.'] == idx].empty else primary_unit
            print(f"  - {idx}: มียอดขายลดลง {abs(row['Diff_Amt']):,.2f} บาท (มาจากปริมาณขายที่{qty_trend} {abs(row['Diff_Qty']):,.2f} {unit_val})")
    else:
        print("ภาพรวมกลุ่มสินค้าที่สั่งซื้อไม่มีการเปลี่ยนแปลงอย่างมีสาระสำคัญ\n")
    print()

    print("คำตอบข้อที่ 3: ความถี่ในการสั่งซื้อ (2024 vs 2025)")
    freq_trend = "สม่ำเสมอมากขึ้น" if mo_25 > mo_24 else ("ลดลง" if mo_25 < mo_24 else "คงที่และสม่ำเสมอ")
    print(f"พฤติกรรมการสั่งซื้อของลูกค้ารายนี้มีความถี่ที่{freq_trend} เมื่อเทียบกับปีก่อน โดยมีรายละเอียดดังนี้:")
    print(f"  - ปี 2024: มีการสั่งซื้อรวม {inv_24} บิล (กระจายตัวอยู่ใน {mo_24} เดือน จาก 12 เดือน)")
    print(f"  - ปี 2025: มีการสั่งซื้อรวม {inv_25} บิล (กระจายตัวอยู่ใน {mo_25} เดือน จาก 12 เดือน)")
    if mo_25 <= 3 and mo_24 > 3:
        print("  > หมายเหตุสำหรับออดิท: ความถี่ที่ลดลงอย่างชัดเจน อาจเกิดจากลูกค้าจบงานโปรเจกต์ หรือเปลี่ยนไปสั่งซื้อจากแหล่งอื่น")
    
    print(f"\n====================================================================")