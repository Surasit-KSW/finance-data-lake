import streamlit as st
import pandas as pd
import duckdb
import os

# ==========================================
# 1. ตั้งค่าหน้าเพจ & ระบบค้นหา Path อัตโนมัติ
# ==========================================
st.set_page_config(page_title="AMC Audit Analytics 2024-2025", page_icon="📊", layout="wide")
st.title("📊 AMC Audit Analytics: 2024 vs 2025")
st.markdown("ระบบวิเคราะห์ความผันผวนบัญชีแบบ Enterprise-Grade (Medallion Architecture & DuckDB)")

# หา Path อัตโนมัติตามโครงสร้าง Finance_Data_Lake
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir) # ถอย 1 ชั้นไปที่หน้าบ้าน

# กำหนดเป้าหมายไฟล์
GOLD_FILE = os.path.join(project_root, '03_Gold_DataMarts', 'Summary_GL_24_25.parquet')
SILVER_FILE = os.path.join(project_root, '02_Silver_Cleaned', 'Master_GL_24_25.parquet')

# เช็คว่ามีไฟล์ไหม
if not os.path.exists(GOLD_FILE):
    st.error(f"❌ ไม่พบไฟล์ Gold Layer: {GOLD_FILE}")
    st.stop()
if not os.path.exists(SILVER_FILE):
    st.error(f"❌ ไม่พบไฟล์ Silver Layer: {SILVER_FILE}")
    st.stop()

# ==========================================
# 2. โหลดข้อมูลชั้น Gold (เฉพาะ 7,468 บรรทัด โหลดไวมาก)
# ==========================================
@st.cache_data
def load_summary_data():
    return pd.read_parquet(GOLD_FILE)

with st.spinner("⏳ กำลังโหลดข้อมูลสรุป..."):
    df_summary = load_summary_data()

# ==========================================
# 3. สร้าง UI แบ่งเป็น 2 หน้า
# ==========================================
tab1, tab2 = st.tabs(["📈 YoY Variance Analysis (งบเปรียบเทียบ)", "🔍 GL Drill-Down (เจาะลึกรายบิลด้วย DuckDB)"])

import calendar # นำเข้าไลบรารีปฏิทินสำหรับดึงชื่อเดือน
import numpy as np

# ------------------------------------------
# Tab 1: YoY Variance Analysis (ใช้ข้อมูล Gold Layer)
# ------------------------------------------
with tab1:
    st.subheader("เปรียบเทียบยอดรวมรายบัญชี (2024 vs 2025)")
    
    col1, col2 = st.columns(2)
    gl_groups = sorted(df_summary['GL_Group'].dropna().unique().tolist())
    selected_group = col1.selectbox("📂 เลือกหมวดหมู่บัญชี (GL Group)", ['All'] + gl_groups)
    
    # 🌟 1. แปลงตัวเลขเดือนเป็นชื่อเดือน (Jan, Feb, Mar...)
    month_dict = {i: calendar.month_abbr[i] for i in range(1, 13)}
    selected_month_names = col2.multiselect("📅 เลือกเดือน (เว้นว่างเพื่อดูทั้งปี)", options=list(month_dict.values()))
    
    # แปลงชื่อเดือนกลับเป็นตัวเลขเพื่อเอาไป Filter ข้อมูล
    selected_months = [k for k, v in month_dict.items() if v in selected_month_names]
    
    # กรองข้อมูล
    df_filtered = df_summary.copy()
    if selected_group != 'All':
        df_filtered = df_filtered[df_filtered['GL_Group'] == selected_group]
    if selected_months:
        df_filtered = df_filtered[df_filtered['Month'].isin(selected_months)]
        
    df_filtered['Year'] = df_filtered['Year'].astype(int)
        
    # 🌟 2. เพิ่มชื่อบัญชี (GL_Name) เข้าไปใน Index
    index_cols = ['GL_Group', 'G/L Account', 'GL_Name'] if 'GL_Name' in df_filtered.columns else ['GL_Group', 'G/L Account']
    
    # 🌟 3. สร้าง Pivot Table และเพิ่มบรรทัด Sum (margins=True)
    pivot_df = df_filtered.pivot_table(index=index_cols, 
                                       columns='Year', 
                                       values='Net_Amount', 
                                       aggfunc='sum',
                                       margins=True,       # คำสั่งเปิดใช้งานแถวผลรวม
                                       margins_name='TOTAL').fillna(0) # ตั้งชื่อบรรทัดผลรวมว่า TOTAL
    
    # ลบคอลัมน์ TOTAL (ผลรวม 2024+2025 แนวนอน) ทิ้ง เพราะเราต้องการแค่ผลรวมแนวตั้ง
    if 'TOTAL' in pivot_df.columns:
        pivot_df = pivot_df.drop(columns='TOTAL')
    
    if 2024 not in pivot_df.columns: pivot_df[2024] = 0
    if 2025 not in pivot_df.columns: pivot_df[2025] = 0
    
    pivot_df['Variance (Amount)'] = pivot_df[2025] - pivot_df[2024]
    pivot_df['Variance (%)'] = np.where(
        pivot_df[2024] != 0, 
        (pivot_df['Variance (Amount)'] / pivot_df[2024].abs()) * 100, 
        0
    )
    
    # 🌟 ฟังก์ชันไฮไลท์แถว TOTAL ให้เป็นตัวหนาและมีสีพื้นหลัง
    def highlight_total(row):
        if row.name[0] == 'TOTAL':
            return ['background-color: #D6EAF8; font-weight: bold; color: black;'] * len(row)
        return [''] * len(row)
    
    # ตกแต่งตาราง
    styled_df = pivot_df.style.format({
        2024: "{:,.2f}", 2025: "{:,.2f}",
        'Variance (Amount)': "{:,.2f}", 'Variance (%)': "{:,.1f}%"
    }).map(lambda x: 'color: white; background-color: #E74C3C; font-weight: bold;' if abs(x) > 10 else '', subset=['Variance (%)'])\
      .apply(highlight_total, axis=1) # นำฟังก์ชันไฮไลท์บรรทัด Sum มาใช้
    
    st.dataframe(styled_df, use_container_width=True, height=600)
    st.caption("💡 ไฮไลท์สีแดง: บัญชีที่มีการเปลี่ยนแปลง (Variance) มากกว่า 10% | 🟦 แถบสีฟ้า: ผลรวมยอดสุทธิ (Net Total)")
    
# ------------------------------------------
# Tab 2: GL Drill-Down (ใช้ DuckDB คิวรีข้อมูลดิบแบบ On-Demand)
# ------------------------------------------
with tab2:
    st.subheader("เครื่องมือเจาะดูรายการรายบิล (Direct Query via DuckDB)")
    st.markdown("ระบบจะวิ่งเข้าไปดึงข้อมูลจากไฟล์ **2.7 ล้านบรรทัด** เฉพาะรายการที่คุณค้นหาในเสี้ยววินาที (Zero Memory Load) 🚀")
    
    c1, c2, c3 = st.columns(3)
    search_gl = c1.text_input("🔍 พิมพ์เลขที่บัญชี (G/L Account)", placeholder="เช่น 711000")
    search_year = c2.selectbox("📆 เลือกปี", [2025, 2024, 'Both'])
    search_text = c3.text_input("📝 ค้นหาคำใน Text/Assignment", placeholder="เช่น OT, Bonus, ค่าไฟ")
    
    if st.button("🚀 ค้นหาข้อมูลรายบิล", type="primary"):
        if search_gl:
            with st.spinner("⚡ DuckDB กำลังสแกนไฟล์ 2.7 ล้านบรรทัด..."):
                # Escape user inputs ก่อน interpolate เพื่อป้องกัน SQL injection
                safe_gl = search_gl.replace("'", "''")

                # สั่ง DuckDB ดึงข้อมูลตรงจากไฟล์ Parquet (ไม่ต้องโหลดลง RAM)
                query = f"""
                    SELECT "Posting Date", "Document Date", "Year", "Month",
                           "G/L Account", "Net_Amount", "Dashboard_Amount",
                           "Text", "Assignment", "Document Number"
                    FROM '{SILVER_FILE}'
                    WHERE "G/L Account" LIKE '%{safe_gl}%'
                """

                # เพิ่มเงื่อนไขปี
                if search_year != 'Both':
                    query += f" AND Year = {int(search_year)}"

                # เพิ่มเงื่อนไขคำค้นหา
                if search_text:
                    safe_text = search_text.replace("'", "''").upper()
                    query += f" AND (UPPER(Text) LIKE '%{safe_text}%' OR UPPER(Assignment) LIKE '%{safe_text}%')"
                    
                query += " ORDER BY \"Posting Date\" DESC"
                
                try:
                    # ประมวลผล SQL
                    df_drill_show = duckdb.query(query).df()
                    
                    st.success(f"พบข้อมูลทั้งหมด **{len(df_drill_show):,}** รายการ (ดึงข้อมูลสำเร็จในพริบตา!)")
                    st.dataframe(df_drill_show, use_container_width=True)
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
        else:
            st.warning("👈 กรุณาพิมพ์เลขที่บัญชีก่อนกดค้นหา")