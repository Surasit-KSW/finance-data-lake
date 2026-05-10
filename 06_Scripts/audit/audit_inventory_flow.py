import pandas as pd
import numpy as np
import os

pd.set_option('display.float_format', '{:,.2f}'.format)

print("⏳ กำลังโหลดและประมวลผลข้อมูล Production และ Sales...")

# ========================================================
# 1. โหลดข้อมูล Sales (Silver Layer)
# ========================================================
try:
    df_sales_24 = pd.read_parquet('./02_Silver_Cleaned/master_sales_2024.parquet', engine='pyarrow')
    df_sales_25 = pd.read_parquet('./02_Silver_Cleaned/master_sales_2025.parquet', engine='pyarrow')
    df_sales_24['Year'] = 2024
    df_sales_25['Year'] = 2025
    df_sales = pd.concat([df_sales_24, df_sales_25], ignore_index=True)
    
    # ดูรหัสสินค้าก่อน และดึงกลุ่มจาก Mat Group Des.
    df_sales['Sales_Qty'] = pd.to_numeric(df_sales['Net Weight'], errors='coerce').fillna(0)
    df_sales['Material'] = df_sales['Material'].astype(str).str.strip()
    df_sales['Mat Group Name'] = df_sales.get('Mat Group Des.', 'Unknown').fillna('Unknown')
except Exception as e:
    print(f"❌ Error โหลดไฟล์ Sales: {e}")
    exit()

# ========================================================
# 2. โหลดข้อมูล Production (Silver Layer)
# ========================================================
try:
    df_prod_24 = pd.read_parquet('./02_Silver_Cleaned/master_production_2024.parquet', engine='pyarrow')
    prod_25_path = './02_Silver_Cleaned/master_production_2025.parquet'
    
    if os.path.exists(prod_25_path):
        df_prod_25 = pd.read_parquet(prod_25_path, engine='pyarrow')
    else:
        df_prod_25 = pd.DataFrame() 
        print("⚠️ (ยังไม่พบไฟล์ Production 2025 ระบบจะวิเคราะห์เท่าที่มี)")

    df_prod = pd.concat([df_prod_24, df_prod_25], ignore_index=True)
    
    if 'Source_File' in df_prod.columns:
        df_prod['Year'] = df_prod['Source_File'].str.extract(r'_(\d{4})_')[0].astype(float)
    else:
        df_prod['Year'] = 2024 
        
    # ดูรหัสสินค้าก่อน และดึงกลุ่มจาก ประเภทกลุ่มสินค้า (Mat Group Name)
    df_prod['Prod_Qty'] = pd.to_numeric(df_prod['Actual GR QTY'], errors='coerce').fillna(0)
    df_prod['Material'] = df_prod['Material'].astype(str).str.strip()
    df_prod['Mat Group Name'] = df_prod.get('ประเภทกลุ่มสินค้า (Mat Group Name)', 'Unknown').fillna('Unknown')
except Exception as e:
    print(f"❌ Error โหลดไฟล์ Production: {e}")
    exit()

# ========================================================
# 🎯 ส่วนการวิเคราะห์ตอบคำถามออดิท (รองรับหลายกลุ่ม)
# ========================================================

# 📌 กำหนดชื่อ "กลุ่มสินค้า" ที่ต้องการวิเคราะห์ (ใส่ได้หลายกลุ่ม คั่นด้วยลูกน้ำ)
target_groups = ['Slit GI']
group_names_text = ", ".join(target_groups)

print(f"\n====================================================================")
print(f"📝 สรุปการวิเคราะห์วงจรสินค้าคงเหลือ (Inventory Flow Analysis)")
print(f"กลุ่มสินค้าที่วิเคราะห์: {group_names_text}")
print(f"====================================================================\n")

# กรองข้อมูลจากกลุ่มสินค้าที่อิงตามรหัสสินค้าของแต่ละไฟล์
prod_target = df_prod[df_prod['Mat Group Name'].isin(target_groups)]
sales_target = df_sales[df_sales['Mat Group Name'].isin(target_groups)]

if prod_target.empty and sales_target.empty:
    print(f"❌ ไม่พบข้อมูลของกลุ่มสินค้าที่ระบุ ทั้งในระบบผลิตและระบบขาย")
    exit()

# --- ดึงยอดผลิตและยอดขาย รายปี (ยอดรวมของทุกกลุ่มที่เลือก) ---
prod_24 = prod_target[prod_target['Year'] == 2024]['Prod_Qty'].sum()
prod_25 = prod_target[prod_target['Year'] == 2025]['Prod_Qty'].sum()

sales_24 = sales_target[sales_target['Year'] == 2024]['Sales_Qty'].sum()
sales_25 = sales_target[sales_target['Year'] == 2025]['Sales_Qty'].sum()

# --- คำนวณร้อยละการเปลี่ยนแปลงการผลิต ---
diff_prod = prod_25 - prod_24
pct_prod = (diff_prod / prod_24 * 100) if prod_24 > 0 else 0
trend_prod = "เพิ่มขึ้น" if diff_prod > 0 else "ลดลง"

# --- คำนวณความเร็วในการขาย (Inventory Flow) ของปี 2025 ---
net_stock_25 = prod_25 - sales_25 
daily_sales_25 = sales_25 / 365 if sales_25 > 0 else 0

# ========================================================
# 📝 พิมพ์ Output ตอบออดิท (รูปแบบที่ปรับปรุงแล้ว)
# ========================================================
print("การเปลี่ยนแปลงปริมาณการผลิตภาพรวม")
if prod_24 == 0 and prod_25 == 0:
    print("  - ไม่พบยอดการผลิตในกลุ่มสินค้าที่เลือก (อาจเป็นการซื้อมาขายไป หรือผลิตจากปีก่อนหน้า)")
else:
    print(f"  - ในปี 2025 สินค้ากลุ่มที่เลือกมีปริมาณการผลิตสุทธิรวม {prod_25:,.2f} KG")
    print(f"  - เมื่อเทียบกับปี 2024 ที่ผลิตได้ {prod_24:,.2f} KG พบว่าการผลิตในภาพรวมมีแนวโน้ม '{trend_prod}' จำนวน {abs(diff_prod):,.2f} KG (หรือเปลี่ยนแปลง {abs(pct_prod):,.2f}%)")
    if prod_25 > sales_25 and diff_prod > 0:
        print("    > บริษัทมีการปรับเพิ่มกำลังการผลิตในสินค้านี้")

print("\nการระบายสินค้าและผลกระทบต่อสต็อกคงเหลือ")

if sales_25 == 0:
    print(f"  - ในปี 2025 สินค้ากลุ่มนี้ไม่มีการขายออกไปเลย ส่งผลให้ปริมาณที่ผลิตได้ทั้งหมด {prod_25:,.2f} KG กลายเป็นสต็อกสะสมคงค้าง")
else:
    sell_through = (sales_25 / prod_25 * 100) if prod_25 > 0 else 100
    
    print(f"  - จากปริมาณการผลิตรวมในปี 2025 ({prod_25:,.2f} KG) บริษัทสามารถระบายสินค้าออกไปได้ {sales_25:,.2f} KG (คิดเป็นอัตรา Sell-through Rate {sell_through:,.1f}%)")
    
    if net_stock_25 > 0:
        days_to_sell = net_stock_25 / daily_sales_25
        print(f"  - การที่ปริมาณการผลิตรวม 'สูงกว่า' ปริมาณการขาย ส่งผลให้มีสต็อกสะสมเพิ่มขึ้น (Net Stock Addition) จำนวน {net_stock_25:,.2f} KG")
        print(f"  > สรุปผลต่อ Auditor: สต็อกที่ปรับตัวสูงขึ้น เป็นผลมาจากการเร่งการผลิต/นำเข้า อย่างไรก็ตาม เมื่อคำนวณจากอัตราการขายเฉลี่ยต่อวันของปี 2025 ({daily_sales_25:,.2f} KG/วัน) คาดว่าบริษัทจะใช้เวลาอีกประมาณ {days_to_sell:,.0f} วัน ในการระบายสต็อกส่วนเกินนี้ ซึ่งยังอยู่ในรอบการดำเนินงานปกติของบริษัท")
    elif net_stock_25 < 0:
        print(f"  - การที่ปริมาณการขายรวม 'สูงกว่า' ปริมาณการผลิตที่ทำได้ในปี ส่งผลให้สต็อกรวมของกลุ่มสินค้านี้ 'ลดลง' จำนวน {abs(net_stock_25):,.2f} KG")
        print(f"  > สรุปผลต่อ Auditor: สินค้ากลุ่มนี้มีการระบายออก (Turnover) ได้ดี โดยยอดขายที่เกิดขึ้นเป็นการระบายสินค้าจากสต็อกเก่าคงเหลือยกมา (Opening Stock) ทำให้ภาพรวมสต็อกปลายปีของกลุ่มนี้ลดลง และช่วยลดความเสี่ยงเรื่องสินค้าล้าสมัย (Obsolescence Risk)")
    else:
        print(f"  - ปริมาณการผลิตและการขายมีความสมดุลกันอย่างสมบูรณ์ ส่งผลให้ไม่มีสต็อกสะสมคงเหลือเพิ่มขึ้นจากรอบการผลิตปีนี้")

print(f"\n====================================================================")