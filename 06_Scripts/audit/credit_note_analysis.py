"""
Credit Note Analysis — Sales Data 2026
รวมไฟล์ขายรายเดือน → สรุปใบลดหนี้ Trend รายเดือน
Output: credit_note_report_2026.xlsx
"""

import pandas as pd
from pathlib import Path
import warnings
import re

warnings.filterwarnings("ignore")

try:
    import xlsxwriter  # noqa
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "xlsxwriter", "-q"])

# ─────────────────────────────────────────────────────────────────────────────
# 1. LOAD & COMBINE
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

MONTH_MAP = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
}

dfs = []
for fp in sorted(BASE_DIR.glob("sale_*.XLSX"), key=lambda p: p.stem):
    m = re.search(r"sale_(\d{2})\.\d{4}", fp.stem, re.IGNORECASE)
    if not m:
        continue
    mon_num = m.group(1)
    xl = pd.ExcelFile(fp)
    sheet = "Sheet1" if "Sheet1" in xl.sheet_names else xl.sheet_names[0]
    df = pd.read_excel(fp, sheet_name=sheet, dtype={"Material": str, "Plant": str})
    df["_month_num"]   = mon_num
    df["_month_label"] = MONTH_MAP.get(mon_num, mon_num)
    dfs.append(df)
    print(f"  Loaded {fp.name}: {len(df):,} rows")

raw = pd.concat(dfs, ignore_index=True)
print(f"\nTotal rows: {len(raw):,}")

# ─────────────────────────────────────────────────────────────────────────────
# 2. FILTER CREDIT NOTES
# ─────────────────────────────────────────────────────────────────────────────
CREDIT_TYPES = {"ZCN1": "Credit Note", "ZBR1": "Credit Note-Returns"}

cn = raw[raw["Billing Type"].isin(CREDIT_TYPES)].copy()
cn["Billing Type Label"] = cn["Billing Type"].map(CREDIT_TYPES)
cn["Net Value(THB)"]     = pd.to_numeric(cn["Net Value(THB)"], errors="coerce").fillna(0)
cn["Net Weight"]         = pd.to_numeric(cn["Net Weight"],     errors="coerce").fillna(0)
cn["Billing Date"]       = pd.to_datetime(cn["Billing Date"],  errors="coerce")
print(f"Credit note rows: {len(cn):,}")

# ─────────────────────────────────────────────────────────────────────────────
# 3. SUMMARIES
# ─────────────────────────────────────────────────────────────────────────────

# Monthly total
monthly = (
    cn.groupby(["_month_num", "_month_label"])
    .agg(
        Doc_Count     = ("Billing No",    "nunique"),
        Net_Value_THB = ("Net Value(THB)", "sum"),
        Net_Weight    = ("Net Weight",     "sum"),
    )
    .reset_index()
    .sort_values("_month_num")
)
monthly["Net_Value_THB"] = monthly["Net_Value_THB"].abs()
monthly["Net_Weight"]    = monthly["Net_Weight"].abs()

# Monthly by billing type (for stacked chart)
monthly_type = (
    cn.groupby(["_month_num", "_month_label", "Billing Type Label"])
    .agg(Net_Value_THB=("Net Value(THB)", "sum"))
    .reset_index()
    .sort_values("_month_num")
)
monthly_type["Net_Value_THB"] = monthly_type["Net_Value_THB"].abs()

# Monthly by product group (Mat Group Des.)
monthly_grp = (
    cn.groupby(["_month_num", "_month_label", "Mat Group Des."])
    .agg(Net_Value_THB=("Net Value(THB)", "sum"))
    .reset_index()
    .sort_values("_month_num")
)
monthly_grp["Net_Value_THB"] = monthly_grp["Net_Value_THB"].abs()

# Raw detail — เก็บค่าจริง (negative) ตาม SAP
cn_detail = cn[[
    "Billing No", "Billing Date", "Billing Type Label",
    "_month_label", "Sold-to Name",
    "Net Weight", "Net Value(THB)", "Gross Amount(THB)",
    "Ref.Tax Inv.", "Remark Billing",
]].rename(columns={
    "_month_label": "Month",
    "Net Value(THB)": "Net Value (THB)",
    "Gross Amount(THB)": "Gross Amount (THB)",
}).copy()
cn_detail["Billing Date"] = cn_detail["Billing Date"].dt.strftime("%Y-%m-%d")

# ─────────────────────────────────────────────────────────────────────────────
# 4. WRITE EXCEL
# ─────────────────────────────────────────────────────────────────────────────
OUTPUT = BASE_DIR / "credit_note_report_2026.xlsx"

with pd.ExcelWriter(OUTPUT, engine="xlsxwriter") as writer:
    wb = writer.book

    # ── Shared formats ────────────────────────────────────────────────────────
    fmt_title  = wb.add_format({"bold": True, "font_size": 16, "font_color": "#FFFFFF",
                                 "bg_color": "#1F3864", "align": "center", "valign": "vcenter"})
    fmt_header = wb.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#2E75B6",
                                 "align": "center", "valign": "vcenter", "border": 1})
    fmt_num    = wb.add_format({"num_format": "#,##0.00", "border": 1})
    fmt_num_i  = wb.add_format({"num_format": "#,##0",    "border": 1})
    fmt_text   = wb.add_format({"border": 1})
    fmt_num_a  = wb.add_format({"num_format": "#,##0.00", "border": 1, "bg_color": "#EBF3FB"})
    fmt_num_ia = wb.add_format({"num_format": "#,##0",    "border": 1, "bg_color": "#EBF3FB"})
    fmt_text_a = wb.add_format({"border": 1, "bg_color": "#EBF3FB"})
    fmt_label  = wb.add_format({"bold": True, "font_size": 11, "font_color": "#1F3864"})
    fmt_kpi_lbl= wb.add_format({"bold": True, "font_size": 10, "font_color": "#7F7F7F",
                                  "bg_color": "#F2F2F2", "border": 1, "align": "center"})
    fmt_kpi_val= wb.add_format({"bold": True, "font_size": 20, "font_color": "#1F3864",
                                  "bg_color": "#DEEAF1", "border": 2, "align": "center",
                                  "num_format": "#,##0.00"})
    fmt_kpi_vi = wb.add_format({"bold": True, "font_size": 20, "font_color": "#1F3864",
                                  "bg_color": "#DEEAF1", "border": 2, "align": "center",
                                  "num_format": "#,##0"})

    def row_fmt(i, is_num=False, is_int=False):
        """Alternate row shading helpers."""
        if i % 2 == 0:
            return fmt_num_a if is_num else (fmt_num_ia if is_int else fmt_text_a)
        return fmt_num if is_num else (fmt_num_i if is_int else fmt_text)

    # ─────────────────────────────────────────────────────────────────────────
    # SHEET 1: Monthly Summary + Charts
    # ─────────────────────────────────────────────────────────────────────────
    ws = wb.add_worksheet("Summary")
    ws.set_zoom(90)
    ws.hide_gridlines(2)

    # Title
    ws.merge_range("A1:N2", "CREDIT NOTE REPORT  |  2026", fmt_title)
    ws.set_row(0, 26); ws.set_row(1, 26)

    # KPI row
    total_val = monthly["Net_Value_THB"].sum()
    total_wt  = monthly["Net_Weight"].sum()
    total_doc = cn["Billing No"].nunique()

    ws.set_row(3, 16); ws.set_row(4, 44)
    kpis = [
        ("Total Credit Value (THB)", total_val, fmt_kpi_val, 1),
        ("Total Weight (KG)",        total_wt,  fmt_kpi_val, 4),
        ("No. of Documents",         total_doc, fmt_kpi_vi,  7),
    ]
    for lbl, val, fmt_v, c in kpis:
        ws.merge_range(3, c, 3, c+1, lbl, fmt_kpi_lbl)
        ws.merge_range(4, c, 4, c+1, val, fmt_v)

    # Column widths
    ws.set_column(0, 0, 2)   # spacer
    ws.set_column(1, 1, 10)  # Month
    ws.set_column(2, 2, 10)  # Docs
    ws.set_column(3, 4, 18)  # Values

    # Monthly table
    ROW = 7
    ws.write(ROW, 1, "Monthly Credit Note Summary", fmt_label)
    ROW += 1
    for ci, h in enumerate(["Month", "No. Docs", "Net Value (THB)", "Net Weight (KG)"], 1):
        ws.write(ROW, ci, h, fmt_header)
    ROW += 1

    tbl_start = ROW
    for i, r in monthly.reset_index(drop=True).iterrows():
        ws.write(ROW, 1, r["_month_label"],  row_fmt(i))
        ws.write(ROW, 2, r["Doc_Count"],     row_fmt(i, is_int=True))
        ws.write(ROW, 3, r["Net_Value_THB"], row_fmt(i, is_num=True))
        ws.write(ROW, 4, r["Net_Weight"],    row_fmt(i, is_num=True))
        ROW += 1
    tbl_end = ROW - 1

    # Chart 1: Column — Monthly CN Value
    ch1 = wb.add_chart({"type": "column"})
    ch1.add_series({
        "name":       "Credit Value (THB)",
        "categories": ["Summary", tbl_start, 1, tbl_end, 1],
        "values":     ["Summary", tbl_start, 3, tbl_end, 3],
        "fill":       {"color": "#2E75B6"},
        "gap": 70,
    })
    ch1.set_title({"name": "Monthly Credit Note Value (THB)"})
    ch1.set_x_axis({"name": "Month", "major_gridlines": {"visible": False}})
    ch1.set_y_axis({"name": "THB", "num_format": "#,##0", "major_gridlines": {"visible": True}})
    ch1.set_legend({"none": True})
    ch1.set_style(10)
    ch1.set_size({"width": 480, "height": 300})
    ws.insert_chart("F8", ch1)

    # Pivot by billing type for stacked chart
    pivot_type = monthly_type.pivot_table(
        index="_month_label", columns="Billing Type Label",
        values="Net_Value_THB", aggfunc="sum", fill_value=0
    ).reindex(monthly["_month_label"].tolist())

    # Write pivot data below table (for chart source)
    pivot_row = ROW + 2
    ws.write(pivot_row, 1, "Month", fmt_header)
    for ci, col in enumerate(pivot_type.columns, 2):
        ws.write(pivot_row, ci, col, fmt_header)
        ws.set_column(ci, ci, 18)
    for i, (month_lbl, row_data) in enumerate(pivot_type.iterrows()):
        ws.write(pivot_row + 1 + i, 1, month_lbl, row_fmt(i))
        for ci, v in enumerate(row_data, 2):
            ws.write(pivot_row + 1 + i, ci, v, row_fmt(i, is_num=True))
    piv_end = pivot_row + len(pivot_type)

    # Chart 2: Stacked column — CN Type breakdown
    ch2 = wb.add_chart({"type": "column", "subtype": "stacked"})
    type_colors = {"Credit Note": "#C00000", "Credit Note-Returns": "#ED7D31"}
    for ci, col in enumerate(pivot_type.columns, 2):
        ch2.add_series({
            "name":       col,
            "categories": ["Summary", pivot_row + 1, 1, piv_end, 1],
            "values":     ["Summary", pivot_row + 1, ci, piv_end, ci],
            "fill":       {"color": type_colors.get(col, "#2E75B6")},
            "gap": 70,
        })
    ch2.set_title({"name": "Credit Note by Type per Month (THB)"})
    ch2.set_x_axis({"name": "Month", "major_gridlines": {"visible": False}})
    ch2.set_y_axis({"name": "THB", "num_format": "#,##0"})
    ch2.set_style(10)
    ch2.set_size({"width": 480, "height": 300})
    ws.insert_chart("F25", ch2)

    # ── Pivot: Monthly × Product Group ───────────────────────────────────────
    pivot_grp = monthly_grp.pivot_table(
        index="_month_label", columns="Mat Group Des.",
        values="Net_Value_THB", aggfunc="sum", fill_value=0
    ).reindex(monthly["_month_label"].tolist())

    # Sort groups by total value desc (biggest group leftmost in legend)
    grp_order = pivot_grp.sum().sort_values(ascending=False).index.tolist()
    pivot_grp = pivot_grp[grp_order]

    grp_pivot_row = piv_end + 3
    ws.write(grp_pivot_row, 1, "Month", fmt_header)
    for ci, col in enumerate(pivot_grp.columns, 2):
        ws.write(grp_pivot_row, ci, col, fmt_header)
        ws.set_column(ci, ci, 16)
    for i, (month_lbl, row_data) in enumerate(pivot_grp.iterrows()):
        ws.write(grp_pivot_row + 1 + i, 1, month_lbl, row_fmt(i))
        for ci, v in enumerate(row_data, 2):
            ws.write(grp_pivot_row + 1 + i, ci, v, row_fmt(i, is_num=True))
    grp_end = grp_pivot_row + len(pivot_grp)

    # 10 distinct colors for product groups
    grp_colors = [
        "#1F3864", "#2E75B6", "#ED7D31", "#A9D18E", "#FFC000",
        "#5B9BD5", "#70AD47", "#C00000", "#9DC3E6", "#7030A0",
    ]
    ch3 = wb.add_chart({"type": "column", "subtype": "stacked"})
    for ci, col in enumerate(pivot_grp.columns, 2):
        ch3.add_series({
            "name":       col,
            "categories": ["Summary", grp_pivot_row + 1, 1, grp_end, 1],
            "values":     ["Summary", grp_pivot_row + 1, ci, grp_end, ci],
            "fill":       {"color": grp_colors[(ci - 2) % len(grp_colors)]},
            "gap": 70,
        })
    ch3.set_title({"name": "Credit Note by Product Group per Month (THB)"})
    ch3.set_x_axis({"name": "Month", "major_gridlines": {"visible": False}})
    ch3.set_y_axis({"name": "THB", "num_format": "#,##0"})
    ch3.set_style(10)
    ch3.set_size({"width": 560, "height": 360})
    ws.insert_chart("F42", ch3)

    # ─────────────────────────────────────────────────────────────────────────
    # SHEET 2: CN Detail
    # ─────────────────────────────────────────────────────────────────────────
    ws2 = wb.add_worksheet("CN Detail")
    ws2.hide_gridlines(2)
    ws2.merge_range("A1:J2", "Credit Note Transactions — Raw Detail", fmt_title)

    COLS = cn_detail.columns.tolist()
    WIDTHS = [16, 12, 22, 8, 32, 14, 16, 18, 18, 20]
    R = 3
    for ci, (c, w) in enumerate(zip(COLS, WIDTHS)):
        ws2.write(R, ci, c, fmt_header)
        ws2.set_column(ci, ci, w)
    R += 1
    for i, row in cn_detail.reset_index(drop=True).iterrows():
        for ci, col in enumerate(COLS):
            v = row[col]
            if col in ("Net Value (THB)", "Gross Amount (THB)", "Net Weight"):
                ws2.write(R, ci, v if pd.notna(v) else 0, row_fmt(i, is_num=True))
            else:
                ws2.write(R, ci, str(v) if pd.notna(v) else "", row_fmt(i))
        R += 1
    ws2.autofilter(3, 0, R - 1, len(COLS) - 1)

print(f"\n[OK] Report saved -> {OUTPUT}")
print(f"     Sheets: Summary | CN Detail")
print(f"     CN rows: {len(cn):,} | Total Value: {total_val:,.2f} THB")
