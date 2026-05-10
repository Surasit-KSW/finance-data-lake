import pandas as pd

# --- ตั้งค่าให้หน้าจอ Terminal ดูง่าย ---
# 1. ให้ตัวเลขมีลูกน้ำคั่น และมีทศนิยม 2 ตำแหน่ง (เช่น 1,234,567.89)
pd.set_option('display.float_format', '{:,.2f}'.format)
# 2. ปรับให้แสดงผลตารางได้กว้างขึ้น จะได้ไม่ตัดขึ้นบรรทัดใหม่จนดูยาก
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

print("กำลังโหลดข้อมูล...")
# โหลดข้อมูล (เปลี่ยน Path ให้ตรงกับเครื่องของคุณ)
df_sales = pd.read_parquet('./02_Silver_Cleaned/master_sales_2025.parquet', engine='pyarrow')
df_sales['Net Value(THB)'] = pd.to_numeric(df_sales['Net Value(THB)'], errors='coerce').fillna(0)
df_sales['Billing Date'] = pd.to_datetime(df_sales['Billing Date'], errors='coerce')

# ========================================================
# 🎯 ส่วนวิเคราะห์หาคำตอบให้ออดิท (เปลี่ยนชื่อบริษัทตรงนี้ได้เลย)
# ========================================================
target_customer = 'บริษัท ดูโฮม จำกัด (มหาชน)'  # <--- ลองเปลี่ยนเป็นบริษัทอื่นที่ออดิทถามได้เลย

print(f"\n" + "="*50)
print(f"📊 สรุปข้อมูลวิเคราะห์ลูกค้า: {target_customer}")
print("="*50)

# กรองข้อมูลเอาเฉพาะลูกค้ารายนี้
df_target = df_sales[df_sales['Sold-to Name'] == target_customer]

if df_target.empty:
    print("❌ ไม่พบยอดขายของลูกค้ารายนี้ในปี 2025 (อาจเป็นลูกค้าที่ยอดหายไป 100%)")
else:
    # 1. หาสินค้าที่ซื้อหลักๆ (ตอบคำถาม: ลดลงจากสินค้าตัวไหน?)
    top_products = df_target.groupby('Material Description').agg(
        จำนวนที่ซื้อ_Qty=('Billed Qty', 'sum'),
        ยอดขาย_THB=('Net Value(THB)', 'sum')
    ).reset_index().sort_values('ยอดขาย_THB', ascending=False).head(5)

    print("\n📦 Top 5 สินค้าหลักที่ซื้อในปี 2025:")
    # ใช้ .to_string(index=False) เพื่อตัดเลข Index รกๆ ด้านหน้าออก
    print(top_products.to_string(index=False))

    # 2. หาความถี่และพฤติกรรม (ตอบคำถาม: เป็นลูกค้าประจำหรือไม่?)
    months_active = sorted(df_target['Billing Date'].dt.month.dropna().unique())
    invoice_count = df_target['Billing No'].nunique()
    total_sales = df_target['Net Value(THB)'].sum()

    print("\n📅 พฤติกรรมการสั่งซื้อ (ความถี่):")
    print(f"- ยอดขายรวมทั้งปี: {total_sales:,.2f} บาท")
    print(f"- จำนวนใบแจ้งหนี้ (บิล) ทั้งหมด: {invoice_count} ใบ")
    print(f"- ซื้อในเดือนที่: {months_active} (รวม {len(months_active)} เดือน จาก 12 เดือน)")
    
    if len(months_active) <= 2:
        print("  >> 📌 ข้อสังเกต: น่าจะเป็นลูกค้าโปรเจกต์ หรือขาจร เพราะซื้อแค่ 1-2 เดือน")
    elif len(months_active) >= 6:
        print("  >> 📌 ข้อสังเกต: น่าจะเป็นลูกค้าระยะยาว/ซื้อประจำ")