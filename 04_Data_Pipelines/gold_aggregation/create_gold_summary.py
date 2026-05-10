import pandas as pd
import os

print("⏳ กำลังสร้างไฟล์ข้อมูลระดับ Gold (Summary) แบบมีชื่อบัญชี...")

script_dir = os.path.dirname(os.path.abspath(__file__))   # gold_aggregation/
project_root = os.path.dirname(os.path.dirname(script_dir))  # → project root

input_file = os.path.join(project_root, '02_Silver_Cleaned', 'Master_GL_24_25.parquet')
if not os.path.exists(input_file):
    print(f"❌ ไม่พบไฟล์ Silver GL: {input_file}")
    raise SystemExit(1)

output_dir = os.path.join(project_root, '03_Gold_DataMarts')
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, 'Summary_GL_24_25.parquet')

print(f"📂 กำลังอ่านไฟล์จาก: {input_file}")
# 🌟 [เพิ่มใหม่] สั่งดึงคอลัมน์ชื่อบัญชี 'G/L Account: Long Text' มาด้วย
df = pd.read_parquet(input_file, columns=['Year', 'Month', 'G/L Account', 'G/L Account: Long Text', 'Net_Amount'])

def get_gl_group(gl):
    gl_str = str(gl)
    if gl_str.startswith('1'): return '1. Assets'
    elif gl_str.startswith('2'): return '2. Liabilities'
    elif gl_str.startswith('3'): return '3. Equity'
    elif gl_str.startswith('4'): return '4. Revenue'
    elif gl_str.startswith('5'): return '5. COGS'
    elif gl_str.startswith('6'): return '6. Selling Exp'
    elif gl_str.startswith('7'): return '7. Admin Exp'
    elif gl_str.startswith('8'): return '8. Finance Cost'
    elif gl_str.startswith('9'): return '9. Tax'
    else: return '0. Others'

df['GL_Group'] = df['G/L Account'].apply(get_gl_group)

print("🧮 กำลังสรุปยอดรวม (Aggregation)...")
# 🌟 [เพิ่มใหม่] กรุ๊ปรวมและจำชื่อบัญชีเอาไว้
summary_df = df.groupby(['Year', 'Month', 'GL_Group', 'G/L Account']).agg({
    'Net_Amount': 'sum',
    'G/L Account: Long Text': 'first' # ดึงชื่อบัญชีชื่อแรกที่เจอมาแสดง
}).reset_index()

# เปลี่ยนชื่อคอลัมน์ให้สั้นลงเป็น GL_Name
summary_df.rename(columns={'G/L Account: Long Text': 'GL_Name'}, inplace=True)
summary_df['GL_Name'] = summary_df['GL_Name'].fillna('Unknown')

print(f"💾 กำลังบันทึกไฟล์ Gold Data ไปที่: {output_file}")
summary_df.to_parquet(output_file, engine='pyarrow', index=False)
print("✅ สำเร็จ! ไฟล์ Summary อัปเดตชื่อบัญชีเรียบร้อยแล้ว")