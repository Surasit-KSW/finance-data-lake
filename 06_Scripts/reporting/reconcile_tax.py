import pandas as pd
import numpy as np
import re
from datetime import datetime

pd.set_option('display.float_format', '{:,.2f}'.format)

print("⏳ กำลังโหลดข้อมูล SAP FBL3N (Excel)...")

# ==========================================
# 1. โหลดข้อมูลและเตรียมคอลัมน์
# ==========================================
try:
    df = pd.read_excel('./01_Bronze_Raw/gl/amc/gl_legacy.xlsx', dtype=str, engine='openpyxl')
    
    df['CCode Curr Value'] = pd.to_numeric(df['CCode Curr Value'], errors='coerce').fillna(0)
    df['Posting Date'] = pd.to_datetime(df['Posting Date'], errors='coerce')
    df['Document Date'] = pd.to_datetime(df['Document Date'], errors='coerce') # 🌟 [NEW] เพิ่ม Document Date
    
    # สร้างคอลัมน์ตั้งต้น
    df['Match_Status'] = 'Open (ยังไม่จับคู่)'
    df['Match_Step'] = '-'
    df['Match_Group_ID'] = '-'     
    df['Remaining_Amount'] = df['CCode Curr Value']
    df['Matched_With'] = '-'
    df['Aging_Days'] = 0
    df['Aging_Bucket'] = '-'
    
except Exception as e:
    print(f"❌ Error โหลดไฟล์: {e}")
    exit()

# ฟังก์ชันสำหรับจับคู่และสร้าง Group ID 
def match_and_group(df, group_cols, step_name, prefix):
    matched_count = 0
    partial_count = 0
    
    if isinstance(group_cols, str):
        valid_mask = df[group_cols].notna() & (df[group_cols] != '') & (df['Remaining_Amount'] != 0)
    else:
        valid_mask = df[group_cols[1]].notna() & (df[group_cols[1]] != '') & (df['Remaining_Amount'] != 0)

    group_counter = 1

    for name, group in df[valid_mask].groupby(group_cols):
        name_str = "-".join([str(x) for x in name]) if isinstance(name, tuple) else str(name)
        group_sum = group['Remaining_Amount'].sum()
        
        # กรณีจับคู่แล้วยอดเป็นศูนย์ (Cleared)
        if abs(group_sum) < 0.01 and len(group) > 1:
            df.loc[group.index, 'Match_Status'] = 'Cleared (จับคู่แล้ว)'
            df.loc[group.index, 'Match_Step'] = step_name
            df.loc[group.index, 'Remaining_Amount'] = 0
            df.loc[group.index, 'Matched_With'] = f"{group_cols}: {name_str}"
            df.loc[group.index, 'Match_Group_ID'] = f"CLEAR-{prefix}-{group_counter:04d}"
            matched_count += len(group)
            
        # กรณี Partial (ยอดไม่ลงตัว)
        else:
            unique_group_id = f"PARTIAL-{prefix}-{group_counter:04d}"
            df.loc[group.index, 'Match_Group_ID'] = unique_group_id
            
            if len(group) > 1:
                df.loc[group.index, 'Match_Status'] = 'Partial (ยอดไม่ลงตัว)'
                df.loc[group.index, 'Match_Step'] = step_name
                df.loc[group.index, 'Matched_With'] = f"[รอเอกสารยอด {group_sum:,.2f}] ข้อมูลอ้างอิง: {name_str}"
                partial_count += len(group)
            else:
                df.loc[group.index, 'Matched_With'] = f"Missing Partner of {name_str}"
                
        group_counter += 1
                
    return matched_count, partial_count

print("🔄 เริ่มกระบวนการ Reconciliation (Smart Grouping)...")

# Step 1: Map จาก DocumentNo กับ Document Header Text
def extract_sap_doc(text):
    text = str(text)
    match = re.search(r'(?<!\d)(\d{9,10})(?!\d)', text)
    return match.group(1) if match else None

df['Extracted_Doc'] = df['Document Header Text'].apply(extract_sap_doc)
step1_matches = 0
grp_step1 = 1

for idx, row in df[(df['Remaining_Amount'] != 0) & (df['Extracted_Doc'].notna())].iterrows():
    target_doc = row['Extracted_Doc']
    target_amt = row['Remaining_Amount']
    
    match_idx = df[(df['DocumentNo'] == target_doc) & 
                   (df['Remaining_Amount'] != 0) & 
                   (abs(df['Remaining_Amount'] + target_amt) < 0.01)].index
    
    if len(match_idx) > 0:
        match_id = match_idx[0]
        df.loc[[idx, match_id], 'Match_Status'] = 'Cleared (จับคู่แล้ว)'
        df.loc[[idx, match_id], 'Match_Step'] = 'Step 1: Header Text Reversal'
        df.loc[[idx, match_id], 'Remaining_Amount'] = 0
        df.loc[[idx, match_id], 'Matched_With'] = f"Reversal Doc: {target_doc}"
        df.loc[[idx, match_id], 'Match_Group_ID'] = f"CLEAR-REV-{grp_step1:04d}"
        step1_matches += 2
        grp_step1 += 1
    else:
        df.loc[idx, 'Match_Group_ID'] = f"PARTIAL-REV-{grp_step1:04d}"
        df.loc[idx, 'Matched_With'] = f"หาบิลต้นทางไม่เจอ Doc: {target_doc}"
        grp_step1 += 1

print(f"  ✅ Step 1 (Header Text Reversal) จับคู่สมบูรณ์: {step1_matches} รายการ")

# Step 2: Map จาก Reference (เลขที่ใบกำกับ) และ Vendor 
df['Clean_Ref'] = df['Reference'].replace({'': np.nan, '0': np.nan})
m2, p2 = match_and_group(df, ['Vendor Account: Name 1', 'Clean_Ref'], 'Step 2: Reference & Vendor Match', 'REF')
print(f"  ✅ Step 2 (Reference Match) จับคู่สมบูรณ์: {m2} รายการ | ติด Partial (รอเอกสาร): {p2} รายการ")

# Step 3: Map จาก Clearing Document
df['Clean_Clearing'] = df['Clearing Document'].replace({'': np.nan, '0': np.nan})
m3, p3 = match_and_group(df, 'Clean_Clearing', 'Step 3: SAP Clearing Document', 'CLR')
print(f"  ✅ Step 3 (Clearing Doc) จับคู่สมบูรณ์: {m3} รายการ | ติด Partial (รอเอกสาร): {p3} รายการ")

# Step 4: Map จาก Assignment
df['Clean_Assign'] = df['Assignment'].replace({'': np.nan, '0': np.nan})
m4, p4 = match_and_group(df, 'Clean_Assign', 'Step 4: Assignment Match', 'ASN')
print(f"  ✅ Step 4 (Assignment) จับคู่สมบูรณ์: {m4} รายการ | ติด Partial (รอเอกสาร): {p4} รายการ")

# Step 5: Vendor Exact Amount (1-to-1)
step5_matches = 0
grp_step5 = 1
for vendor, group in df[(df['Remaining_Amount'] != 0) & (df['Vendor Account: Name 1'].notna())].groupby('Vendor Account: Name 1'):
    open_indices = group.index.tolist()
    
    for i in open_indices:
        if df.loc[i, 'Remaining_Amount'] == 0: continue
        amt_i = df.loc[i, 'Remaining_Amount']
        doc_type_i = str(df.loc[i, 'Document type']).upper()
        
        for j in open_indices:
            if i != j and df.loc[j, 'Remaining_Amount'] != 0:
                amt_j = df.loc[j, 'Remaining_Amount']
                doc_type_j = str(df.loc[j, 'Document type']).upper()
                
                if abs(amt_i + amt_j) < 0.01: 
                    df.loc[[i, j], 'Match_Status'] = 'Cleared (จับคู่แล้ว)'
                    df.loc[[i, j], 'Match_Step'] = 'Step 5: Vendor Exact Amount'
                    df.loc[[i, j], 'Remaining_Amount'] = 0
                    df.loc[[i, j], 'Matched_With'] = f"1-to-1 Offset ({doc_type_i}/{doc_type_j})"
                    df.loc[[i, j], 'Match_Group_ID'] = f"CLEAR-1TO1-{grp_step5:04d}"
                    step5_matches += 2
                    grp_step5 += 1
                    break 
print(f"  ✅ Step 5 (Vendor 1-to-1 Match) จับคู่สมบูรณ์: {step5_matches} รายการ")

# ขั้นตอนทำ Aging Report สำหรับยอดที่ไม่ได้ Cleared
print("📅 กำลังคำนวณอายุยอดคงเหลือ (Aging Analysis)...")
current_date = pd.Timestamp.now().normalize()
unmatched_mask = df['Match_Status'] != 'Cleared (จับคู่แล้ว)'
df.loc[unmatched_mask, 'Aging_Days'] = (current_date - df.loc[unmatched_mask, 'Posting Date']).dt.days

def get_aging_bucket(days):
    if pd.isna(days): return 'Unknown'
    if days <= 30: return '1. 0 - 30 Days (ปกติ)'
    elif days <= 90: return '2. 31 - 90 Days (ต้องติดตาม)'
    elif days <= 180: return '3. 91 - 180 Days (ความเสี่ยงสูง)'
    else: return '4. > 180 Days (เกินกำหนดขอคืน)'

df.loc[unmatched_mask, 'Aging_Bucket'] = df.loc[unmatched_mask, 'Aging_Days'].apply(get_aging_bucket)

# ==========================================
# สรุปผลและ Export (แยก 3 Sheets: All, Outstanding, Matched)
# ==========================================
# 🌟 [NEW] เพิ่ม 'Document Date' ลงไปในคอลัมน์ที่จะแสดงผล
output_cols = ['Vendor Account: Name 1', 'DocumentNo', 'Posting Date', 'Document Date', 'Reference', 'Assignment', 
               'Clearing Document', 'Document Header Text', 'Match_Group_ID', 'CCode Curr Value', 
               'Match_Status', 'Match_Step', 'Remaining_Amount', 'Matched_With', 'Aging_Days', 'Aging_Bucket']

# จัดเรียงโดยเน้น Group ID ให้อยู่ติดกัน
df_all = df[output_cols].sort_values(by=['Match_Status', 'Match_Group_ID', 'Vendor Account: Name 1'], ascending=[False, True, True])

# สร้าง DataFrame แยกแต่ละ Sheet
df_outstanding = df_all[df_all['Match_Status'] != 'Cleared (จับคู่แล้ว)'].copy()
df_matched = df_all[df_all['Match_Status'] == 'Cleared (จับคู่แล้ว)'].copy() # 🌟 [NEW] ดึงเฉพาะยอดที่ชนสำเร็จ

print(f"\n📊 สรุปผลการกระทบยอด (Reconciliation Summary):")
print(f"  - รายการทั้งหมด: {len(df_all):,} บรรทัด")
print(f"  - จับคู่สมบูรณ์ (Matched): {len(df_matched):,} บรรทัด")
print(f"  - ติดสถานะ Partial (ยอดไม่ลงตัว): {len(df_outstanding[df_outstanding['Match_Status'] == 'Partial (ยอดไม่ลงตัว)']):,} บรรทัด")
print(f"  - คงเหลือค้างชำระทั้งหมด: {len(df_outstanding):,} บรรทัด (ยอดเงินสุทธิ: {df_outstanding['Remaining_Amount'].sum():,.2f} บาท)")

output_path = './02_Silver_Cleaned/reconciled_tax_with_groups.xlsx'
with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
    # 🌟 [NEW] เขียนข้อมูลลง 3 Sheets
    df_all.to_excel(writer, sheet_name='All_Items', index=False)
    df_outstanding.to_excel(writer, sheet_name='Outstanding_Items', index=False)
    df_matched.to_excel(writer, sheet_name='Matched_Items', index=False)

print(f"\n💾 บันทึกผลลัพธ์ลงไฟล์ Excel เรียบร้อยแล้วที่: {output_path}")
print(f"====================================================================")