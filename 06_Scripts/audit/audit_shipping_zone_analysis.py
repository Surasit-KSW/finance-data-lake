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
    
    df_sales['Net Value(THB)'] = pd.to_numeric(df_sales['Net Value(THB)'], errors='coerce').fillna(0)
    df_sales['Net Weight'] = pd.to_numeric(df_sales['Net Weight'], errors='coerce').fillna(0)
    
except Exception as e:
    print(f"❌ Error โหลดไฟล์ Sales: {e}")
    exit()

# ========================================================
# 2. กรองเฉพาะสินค้า FG (Finished Goods)
# ========================================================
print("🧹 กำลังกรองข้อมูลเฉพาะสินค้าสำเร็จรูป (FG)...")
# ค้นหาคอลัมน์ที่ระบุประเภทสินค้า
mat_type_col = None
for col in df_sales.columns:
    if col.lower() in ['material type description', 'mat type', 'ประเภทวัตถุดิบ', 'material type']:
        mat_type_col = col
        break

if mat_type_col:
    # กรองเฉพาะบรรทัดที่มีคำว่า FG หรือ Finished Goods
    df_sales = df_sales[df_sales[mat_type_col].astype(str).str.contains('FG|Finished Goods|FERT', case=False, na=False)]
    print(f"  ✅ กรอง FG สำเร็จ (อ้างอิงจากคอลัมน์ '{mat_type_col}')")
else:
    print("  ⚠️ ไม่พบคอลัมน์ประเภทสินค้า (Material Type) ระบบจะคำนวณจากยอดขายทั้งหมดแทน")

# ========================================================
# 3. จัดการเงื่อนไขการส่งและแบ่งโซนจังหวัด
# ========================================================
# --- Shipping Condition ---
ship_col = 'Shipping Condition Name'
if ship_col not in df_sales.columns:
    possible_cols = [c for c in df_sales.columns if 'shipping' in c.lower() or 'condition' in c.lower()]
    ship_col = possible_cols[0] if possible_cols else 'Shipping_Cond'
    if ship_col == 'Shipping_Cond': df_sales[ship_col] = 'ไม่ระบุ'

df_sales[ship_col] = df_sales[ship_col].astype(str).str.strip().fillna('ไม่ระบุ')
df_sales.loc[df_sales[ship_col].str.contains('รับเอง', case=False, na=False), ship_col] = 'รับเอง'

# --- Province / Zone Mapping ---
province_col = None
for col in df_sales.columns:
    if col.lower() in ['province', 'จังหวัด', 'ship-to city', 'city', 'region']:
        province_col = col
        break

if not province_col:
    print("  ⚠️ ไม่พบคอลัมน์ 'จังหวัด' (Province/City) ระบบจะจัดให้อยู่โซน 'ไม่ระบุโซน'")
    df_sales['Zone'] = 'ไม่ระบุโซน'
else:
    # สร้าง Mapping ภูมิภาค
    zone_mapping = {
        'ภาคเหนือ': ['เชียงใหม่', 'เชียงราย', 'ลำปาง', 'ลำพูน', 'แม่ฮ่องสอน', 'พะเยา', 'แพร่', 'น่าน', 'อุตรดิตถ์', 'นครสวรรค์', 'กำแพงเพชร', 'พิจิตร', 'พิษณุโลก', 'สุโขทัย', 'เพชรบูรณ์', 'อุทัยธานี'],
        'ภาคอีสาน': ['นครราชสีมา', 'ขอนแก่น', 'อุบลราชธานี', 'อุดรธานี', 'บุรีรัมย์', 'สุรินทร์', 'ศรีสะเกษ', 'ร้อยเอ็ด', 'มหาสารคาม', 'ชัยภูมิ', 'เลย', 'หนองบัวลำภู', 'หนองคาย', 'บึงกาฬ', 'สกลนคร', 'นครพนม', 'มุกดาหาร', 'ยโสธร', 'อำนาจเจริญ', 'กาฬสินธุ์'],
        'ภาคกลาง': ['กรุงเทพมหานคร', 'กทม', 'bangkok', 'นนทบุรี', 'ปทุมธานี', 'สมุทรปราการ', 'สมุทรสาคร', 'สมุทรสงคราม', 'นครปฐม', 'พระนครศรีอยุธยา', 'สระบุรี', 'ลพบุรี', 'สิงห์บุรี', 'อ่างทอง', 'ชัยนาท', 'สุพรรณบุรี', 'นครนายก'],
        'ภาคตะวันออก': ['ชลบุรี', 'ระยอง', 'จันทบุรี', 'ตราด', 'ฉะเชิงเทรา', 'ปราจีนบุรี', 'สระแก้ว'],
        'ภาคตะวันตก': ['กาญจนบุรี', 'ราชบุรี', 'เพชรบุรี', 'ประจวบคีรีขันธ์', 'ตาก'],
        'ภาคใต้': ['สงขลา', 'ภูเก็ต', 'สุราษฎร์ธานี', 'นครศรีธรรมราช', 'ชุมพร', 'ระนอง', 'พังงา', 'กระบี่', 'ตรัง', 'พัทลุง', 'ปัตตานี', 'ยะลา', 'นราธิวาส', 'สตูล']
    }
    
    # ฟังก์ชันแปลงจังหวัดเป็นโซน
    def get_zone(prov_name):
        prov_str = str(prov_name).replace('จ.', '').strip()
        for zone, prov_list in zone_mapping.items():
            if any(p in prov_str for p in prov_list):
                return zone
        return 'ไม่ระบุโซน / อื่นๆ'

    df_sales['Zone'] = df_sales[province_col].apply(get_zone)

# ========================================================
# 🎯 ส่วนการวิเคราะห์ (Analysis Output)
# ========================================================
total_vol_24 = df_sales[df_sales['Year'] == 2024]['Net Weight'].sum()
total_vol_25 = df_sales[df_sales['Year'] == 2025]['Net Weight'].sum()

print(f"\n====================================================================")
print(f"📝 สรุปการวิเคราะห์เงื่อนไขการจัดส่งแยกตามภูมิภาค (Shipping & Zone Analysis - FG Only)")
print(f"====================================================================\n")

print(f"📌 ภาพรวมปริมาณขายสุทธิ (เฉพาะสินค้าสำเร็จรูป FG)")
print(f"  - ปี 2024: {total_vol_24:,.2f} KG")
print(f"  - ปี 2025: {total_vol_25:,.2f} KG\n")

# กรุ๊ปข้อมูล: Zone -> Shipping Condition -> Year
zone_ship_group = df_sales.groupby(['Zone', ship_col, 'Year'])['Net Weight'].sum().unstack(fill_value=0)

if 2024 not in zone_ship_group.columns: zone_ship_group[2024] = 0
if 2025 not in zone_ship_group.columns: zone_ship_group[2025] = 0

zone_ship_group['Vol_Diff'] = zone_ship_group[2025] - zone_ship_group[2024]
zone_ship_group['%_Change'] = np.where(zone_ship_group[2024] > 0, (zone_ship_group['Vol_Diff'] / zone_ship_group[2024]) * 100, 100)

# ดึงรายชื่อโซนทั้งหมด
zones = df_sales['Zone'].unique()

for zone in sorted(zones):
    if zone not in zone_ship_group.index.get_level_values('Zone'): continue
        
    print(f"🌍 ภูมิภาค (Zone): {zone}")
    zone_data = zone_ship_group.loc[zone]
    
    # หายอดรวมของโซนนี้
    zone_total_24 = zone_data[2024].sum()
    zone_total_25 = zone_data[2025].sum()
    print(f"   [ยอดขายรวมโซนนี้ -> ปี 2024: {zone_total_24:,.2f} KG | ปี 2025: {zone_total_25:,.2f} KG]")
    
    for condition, row in zone_data.iterrows():
        # คำนวณ % สัดส่วนในโซน
        mix_24 = (row[2024] / zone_total_24 * 100) if zone_total_24 > 0 else 0
        mix_25 = (row[2025] / zone_total_25 * 100) if zone_total_25 > 0 else 0
        
        trend = "เพิ่มขึ้น" if row['Vol_Diff'] > 0 else "ลดลง"
        
        print(f"     📍 {condition}:")
        print(f"        - ปี 2024: {row[2024]:,.2f} KG (สัดส่วน {mix_24:,.1f}%)")
        print(f"        - ปี 2025: {row[2025]:,.2f} KG (สัดส่วน {mix_25:,.1f}%)")
        if row['Vol_Diff'] != 0:
            print(f"        > ปริมาณ {trend} {abs(row['Vol_Diff']):,.2f} KG ({row['%_Change']:,.1f}%)")
    print("-" * 65)

print("\n💡 ข้อสังเกตสำหรับ Auditor (Freight Cost Analysis):")
print("  - หากพบว่าในโซนที่อยู่ 'ไกล' (เช่น ภาคเหนือ, ภาคใต้, ภาคอีสาน) มีสัดส่วนของ 'บริษัทจัดส่งให้' เพิ่มสูงขึ้น ย่อมเป็นสาเหตุหลักที่ทำให้ค่าขนส่งเฉลี่ยต่อกิโลกรัม (Freight per KG) ของบริษัทปรับตัวสูงขึ้น")
print("  - ในทางกลับกัน หากโซนไกลๆ ลูกค้าเปลี่ยนมาใช้เงื่อนไข 'รับเอง' มากขึ้น ค่าใช้จ่ายในการจัดส่งของบริษัทควรจะมีแนวโน้มลดลง")
print(f"====================================================================")