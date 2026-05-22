"""
format_gi_template.py
Professional formatting for Plant_GI_Costing_Template_2026
Sheet: 1Q-JFK0zPNWaHs77Nu-VLDaNkem0-netkF1CcLt4i76U

Row indices are 0-based (Google Sheets API standard).

Prepared by: Claude Code
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.auth import get_credentials
from googleapiclient.discovery import build

SHEET_ID = "1Q-JFK0zPNWaHs77Nu-VLDaNkem0-netkF1CcLt4i76U"

# ─── Helpers ─────────────────────────────────────────────────
def c(r, g, b):   return {"red": r/255, "green": g/255, "blue": b/255}

NAVY    = c(31,  63, 100)
BLUE    = c(47,  85, 151)
ACCENT  = c(68, 114, 196)
TBLUE   = c(189,215,238)   # table header light blue
LBLUE   = c(221,235,247)   # PK+CR rows
LGREEN  = c(226,239,218)   # GI rows
LYELLOW = c(255,242,204)   # total rows
LORANGE = c(252,232,216)   # material rows
LGREY   = c(242,242,242)   # alternate / placeholder
WHITE   = c(255,255,255)
BLACK   = c(0,0,0)
GREY    = c(150,150,150)
DKGREY  = c(80,80,80)

def rng(sid, r1, c1, r2, c2):
    return {"sheetId": sid, "startRowIndex": r1, "endRowIndex": r2,
            "startColumnIndex": c1, "endColumnIndex": c2}

def repeat(sid, r1, c1, r2, c2, fmt, fields):
    return {"repeatCell": {"range": rng(sid, r1, c1, r2, c2),
                           "cell": {"userEnteredFormat": fmt},
                           "fields": "userEnteredFormat(" + fields + ")"}}

def dims(sid, dim, i1, i2, px):
    return {"updateDimensionProperties": {
        "range": {"sheetId": sid, "dimension": dim,
                  "startIndex": i1, "endIndex": i2},
        "properties": {"pixelSize": px}, "fields": "pixelSize"}}

def freeze(sid, rows=0, cols=0):
    return {"updateSheetProperties": {
        "properties": {"sheetId": sid,
                       "gridProperties": {"frozenRowCount": rows,
                                          "frozenColumnCount": cols}},
        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}}

def merge_cells(sid, r1, c1, r2, c2):
    return {"mergeCells": {"range": rng(sid, r1, c1, r2, c2),
                           "mergeType": "MERGE_ALL"}}

def border_top(sid, row, c1, c2, weight="SOLID_MEDIUM"):
    b = {"style": weight, "color": c(100,100,100)}
    fmt = {"borders": {"top": b}}
    return repeat(sid, row, c1, row+1, c2, fmt, "borders")

def border_bottom(sid, row, c1, c2, weight="SOLID"):
    b = {"style": weight, "color": c(100,100,100)}
    fmt = {"borders": {"bottom": b}}
    return repeat(sid, row, c1, row+1, c2, fmt, "borders")

def row_style(sid, r1, c1, r2, c2,
              bg=None, fg=None, bold=False, italic=False,
              size=10, align=None, valign="MIDDLE", wrap=None,
              num_fmt=None):
    tf = {"fontSize": size, "bold": bold, "italic": italic}
    if fg: tf["foregroundColor"] = fg
    fmt = {"textFormat": tf, "verticalAlignment": valign}
    if bg:     fmt["backgroundColor"] = bg
    if align:  fmt["horizontalAlignment"] = align
    if wrap:   fmt["wrapStrategy"] = wrap
    if num_fmt: fmt["numberFormat"] = num_fmt
    fields = ["textFormat", "verticalAlignment"]
    if bg:     fields.append("backgroundColor")
    if align:  fields.append("horizontalAlignment")
    if wrap:   fields.append("wrapStrategy")
    if num_fmt: fields.append("numberFormat")
    return repeat(sid, r1, c1, r2, c2, fmt, ",".join(fields))

def num(sid, r1, c1, r2, c2, pattern):
    fmt = {"numberFormat": {"type": "NUMBER", "pattern": pattern}}
    return repeat(sid, r1, c1, r2, c2, fmt, "numberFormat")

def num_pct(sid, r1, c1, r2, c2):
    return num(sid, r1, c1, r2, c2, "0.00%")


# ─── ANNUAL TOTAL ─────────────────────────────────────────────
# Exact 0-indexed row positions (verified from sheet read):
#  0  PREPARED
#  1  Title "ASIA METAL PLC —..."
#  2  Month headers: "Items" | Jan | "" | Feb | "" ... | YE | ""
#  3  Sub-headers: "" | "Amount (THB)" | "MT" ...
#  4  HRC Used
#  5  CRC Output (GR)
#  6  Scrap Actual
#  7  % Yield Loss
#  8  Pickling Conversion
#  9  Cold Rolling Conversion
# 10  Total CRC Cost
# 11  " GALVANIZING"  ← section header
# 12  CRC Used (GI input)
# 13  Zinc + ZAM Alloy
# 14  GI Galvanized Output
# 15  Scrap (Dross+Slag)
# 16  GI Conversion Cost
# 17  Total GI Cost
#
# Column layout: A(0)=spacer | B(1)=label
#   Jan: C(2)=amt D(3)=MT  Feb: E(4) F(5)  ...  Dec: Y(24) Z(25)
#   YE:  AA(26) AB(27)
#   Total usable width: 28 cols (0..27)

AT_COLS = 28

def fmt_annual_total(sid):
    reqs = []

    # ── Column widths ──────────────────────────────────────────
    reqs += [dims(sid, "COLUMNS", 0, 1,  16),    # A spacer
             dims(sid, "COLUMNS", 1, 2, 225),    # B label
             # Monthly amount cols (even indices 2,4,6...24): 108px
             # Monthly MT cols (odd indices 3,5,7...25): 72px
             ]
    for m in range(12):
        reqs.append(dims(sid, "COLUMNS", 2+m*2, 3+m*2, 108))  # amount
        reqs.append(dims(sid, "COLUMNS", 3+m*2, 4+m*2,  68))  # MT
    reqs.append(dims(sid, "COLUMNS", 26, 27, 110))   # YE amount
    reqs.append(dims(sid, "COLUMNS", 27, 28,  68))   # YE MT

    # ── Row heights ────────────────────────────────────────────
    reqs += [dims(sid, "ROWS", 0,  1, 14),   # PREPARED: thin
             dims(sid, "ROWS", 1,  2, 28),   # Title
             dims(sid, "ROWS", 2,  3, 22),   # Month names
             dims(sid, "ROWS", 3,  4, 18),   # Amount/MT sub-header
             dims(sid, "ROWS", 4, 18, 19)]   # Data rows

    # ── Base reset ─────────────────────────────────────────────
    reqs.append(row_style(sid, 0, 0, 18, AT_COLS, bg=WHITE, fg=BLACK, size=10))

    # ── Row 0: PREPARED ────────────────────────────────────────
    reqs.append(row_style(sid, 0, 0, 1, AT_COLS, fg=GREY, italic=True, size=8))

    # ── Row 1: Title ───────────────────────────────────────────
    reqs.append(row_style(sid, 1, 0, 2, AT_COLS, bg=NAVY))
    reqs.append(row_style(sid, 1, 1, 2, AT_COLS,
                          bg=NAVY, fg=WHITE, bold=True, size=12, align="LEFT"))

    # ── Row 2: Month header — merge each month pair ─────────────
    reqs.append(row_style(sid, 2, 0, 3, AT_COLS,
                          bg=NAVY, fg=WHITE, bold=True, size=10, align="CENTER"))
    # Merge: label col B stays alone; month pairs C:D, E:F ... Y:Z; YE: AA:AB
    for m in range(12):
        reqs.append(merge_cells(sid, 2, 2+m*2, 3, 4+m*2))
    reqs.append(merge_cells(sid, 2, 26, 3, 28))  # YE pair

    # ── Row 3: Amount/MT sub-header ────────────────────────────
    reqs.append(row_style(sid, 3, 0, 4, AT_COLS,
                          bg=BLUE, fg=WHITE, bold=True, size=9, align="CENTER"))
    # "B. PICKLING & COLD ROLLING" label in col B
    reqs.append(row_style(sid, 3, 1, 4, 2,
                          bg=BLUE, fg=WHITE, bold=True, size=9, align="LEFT"))

    # ── PK+CR block (rows 4–10) ────────────────────────────────
    # Row 4: HRC material — warm tint
    reqs.append(row_style(sid, 4, 0, 5, AT_COLS, bg=LORANGE))
    reqs.append(row_style(sid, 4, 1, 5, 2, bg=LORANGE, bold=True))
    # Rows 5–9: alternate LBLUE / white
    for i, r in enumerate(range(5, 10)):
        bg_ = LBLUE if i % 2 == 0 else WHITE
        reqs.append(row_style(sid, r, 0, r+1, AT_COLS, bg=bg_))
    # Row 10: Total CRC — yellow, bold, top border
    reqs.append(row_style(sid, 10, 0, 11, AT_COLS, bg=LYELLOW, bold=True))
    reqs.append(border_top(sid, 10, 1, AT_COLS))

    # ── Row 11: GALVANIZING section header ─────────────────────
    reqs.append(row_style(sid, 11, 0, 12, AT_COLS,
                          bg=ACCENT, fg=WHITE, bold=True, size=10))

    # ── GI block (rows 12–17) ──────────────────────────────────
    # Rows 12–13: material rows (CRC used + Zinc/ZAM)
    reqs.append(row_style(sid, 12, 0, 14, AT_COLS, bg=LORANGE))
    reqs.append(row_style(sid, 12, 1, 13, 2, bg=LORANGE, bold=True))
    reqs.append(row_style(sid, 13, 1, 14, 2, bg=LORANGE, bold=True))
    # Row 14: GI Output — highlight
    reqs.append(row_style(sid, 14, 0, 15, AT_COLS, bg=LGREEN, bold=True))
    # Rows 15–16: alternate
    reqs.append(row_style(sid, 15, 0, 16, AT_COLS, bg=WHITE))
    reqs.append(row_style(sid, 16, 0, 17, AT_COLS, bg=LBLUE))
    # Row 17: Total GI — yellow, bold, top+bottom border
    reqs.append(row_style(sid, 17, 0, 18, AT_COLS, bg=LYELLOW, bold=True))
    reqs.append(border_top(sid, 17, 1, AT_COLS))
    reqs.append(border_bottom(sid, 17, 1, AT_COLS))

    # ── Label column: left-align, slight indent ─────────────────
    reqs.append(row_style(sid, 4, 1, 18, 2, align="LEFT", size=10))
    reqs.append(row_style(sid, 6, 1, 7,  2, fg=DKGREY, italic=True))  # Scrap
    reqs.append(row_style(sid, 7, 1, 8,  2, fg=DKGREY, italic=True))  # Yield%
    reqs.append(row_style(sid, 15, 1, 16, 2, fg=DKGREY, italic=True)) # Scrap GI

    # ── Number formats ─────────────────────────────────────────
    # Amount cols (0-indexed C=2,E=4...AA=26): #,##0
    # MT / rate cols (D=3,F=5...AB=27): #,##0.00
    for m in range(13):  # 12 months + YE
        ac = 2 + m*2  # amount col
        mc = 3 + m*2  # MT col
        reqs.append(num(sid, 4, ac, 18, ac+1, "#,##0"))
        reqs.append(num(sid, 4, mc, 18, mc+1, "#,##0.00"))
    # Yield row: percentage
    reqs.append(num_pct(sid, 7, 2, 8, AT_COLS))
    # Number cells: right-align
    reqs.append(row_style(sid, 4, 2, 18, AT_COLS, align="RIGHT"))

    # ── Freeze: first 4 rows + col B ───────────────────────────
    reqs.append(freeze(sid, rows=4, cols=2))

    return reqs


# ─── SUMMARY ──────────────────────────────────────────────────
# Exact 0-indexed row positions:
#  0  PREPARED
#  1  "Metric / Item" + Jan..Dec + YTD  (header)
#  2  blank
#  3  " PRODUCTION VOLUME (MT)"
#  4   Pickling & Cold Rolling (CRC Output)
#  5   Galvanizing (GI Output)
#  6  blank
#  7  " CONVERSION COST (THB/MT)"
#  8   Pickling & Cold Rolling
#  9   Galvanizing
# 10   Total Conversion Cost
# 11  blank
# 12  " MATERIAL COST (THB/MT)"
# 13   Hot Rolled Coil (HRC) / MT
# 14   Zinc + ZAM Alloy / MT
# 15   Total Material Cost
# 16  blank
# 17  " FINISHED GOODS COST..." (section)
# 18   GI/ZAM Z60
# 19   GI/ZAM Z80
# 20   GI/ZAM Z120
# 21   GI/ZAM Z180
# 22   GI/ZAM Z275
# 23  blank
# 24  " SG&A (THB/MT)"
# 25   SG&A per MT
# 26  blank
# 27  " GRAND TOTAL..." (section label)
# 28   Grand Total (Z120 base)
# 29  blank
# 30  Note
#
# Cols: A(0) B(1)label C(2)Jan ... N(13)Dec O(14)YTD

SUM_COLS = 15

def fmt_summary(sid):
    reqs = []

    # ── Column widths ──────────────────────────────────────────
    reqs += [dims(sid, "COLUMNS", 0, 1, 16),     # A spacer
             dims(sid, "COLUMNS", 1, 2, 240),    # B label
             ]
    for c_ in range(2, 14):                      # Jan–Dec
        reqs.append(dims(sid, "COLUMNS", c_, c_+1, 88))
    reqs.append(dims(sid, "COLUMNS", 14, 15, 95))  # YTD

    # ── Row heights ────────────────────────────────────────────
    reqs += [dims(sid, "ROWS", 0,  1, 14),
             dims(sid, "ROWS", 1,  2, 24),
             dims(sid, "ROWS", 2, 31, 19)]

    # ── Base reset ─────────────────────────────────────────────
    reqs.append(row_style(sid, 0, 0, 31, SUM_COLS, bg=WHITE, fg=BLACK, size=10))

    # ── Row 0: PREPARED ────────────────────────────────────────
    reqs.append(row_style(sid, 0, 0, 1, SUM_COLS, fg=GREY, italic=True, size=8))

    # ── Row 1: Column header ───────────────────────────────────
    reqs.append(row_style(sid, 1, 0, 2, SUM_COLS, bg=NAVY, fg=WHITE))
    reqs.append(row_style(sid, 1, 1, 2, SUM_COLS,
                          bg=NAVY, fg=WHITE, bold=True, size=11, align="LEFT"))
    reqs.append(row_style(sid, 1, 2, 2, SUM_COLS,
                          bg=NAVY, fg=WHITE, bold=True, size=10, align="CENTER"))

    # ── Section headers ────────────────────────────────────────
    for r in [3, 7, 12, 17, 24, 27]:
        reqs.append(row_style(sid, r, 0, r+1, SUM_COLS,
                              bg=BLUE, fg=WHITE, bold=True, size=10))

    # ── PRODUCTION VOLUME (rows 4–5) ──────────────────────────
    reqs.append(row_style(sid, 4, 0, 5, SUM_COLS, bg=LBLUE))
    reqs.append(row_style(sid, 5, 0, 6, SUM_COLS, bg=LBLUE))
    reqs.append(num(sid, 4, 2, 6, SUM_COLS, "#,##0.00"))

    # ── CONVERSION COST (rows 8–10) ───────────────────────────
    reqs.append(row_style(sid, 8,  0, 9,  SUM_COLS, bg=WHITE))
    reqs.append(row_style(sid, 9,  0, 10, SUM_COLS, bg=LBLUE))
    reqs.append(row_style(sid, 10, 0, 11, SUM_COLS, bg=LYELLOW, bold=True))
    reqs.append(num(sid, 8, 2, 11, SUM_COLS, "#,##0.00"))
    reqs.append(border_top(sid, 10, 1, SUM_COLS, "SOLID"))

    # ── MATERIAL COST (rows 13–15) ────────────────────────────
    reqs.append(row_style(sid, 13, 0, 14, SUM_COLS, bg=LORANGE))
    reqs.append(row_style(sid, 14, 0, 15, SUM_COLS, bg=LORANGE))
    reqs.append(row_style(sid, 15, 0, 16, SUM_COLS, bg=LYELLOW, bold=True))
    reqs.append(num(sid, 13, 2, 16, SUM_COLS, "#,##0.00"))
    reqs.append(border_top(sid, 15, 1, SUM_COLS, "SOLID"))

    # ── FINISHED GOODS (rows 18–22) ── placeholder ─────────────
    for r in range(18, 23):
        reqs.append(row_style(sid, r, 0, r+1, SUM_COLS, bg=LGREY, fg=DKGREY, italic=True))

    # ── SG&A (row 25) ─────────────────────────────────────────
    reqs.append(row_style(sid, 25, 0, 26, SUM_COLS, bg=LGREY))

    # ── GRAND TOTAL (row 28) ──────────────────────────────────
    reqs.append(row_style(sid, 28, 0, 29, SUM_COLS, bg=LYELLOW, bold=True, size=11))
    reqs.append(num(sid, 28, 2, 29, SUM_COLS, "#,##0.00"))
    reqs.append(border_top(sid,    28, 1, SUM_COLS, "SOLID_MEDIUM"))
    reqs.append(border_bottom(sid, 28, 1, SUM_COLS, "SOLID_MEDIUM"))

    # ── Note row ──────────────────────────────────────────────
    reqs.append(row_style(sid, 30, 0, 31, SUM_COLS,
                          fg=GREY, italic=True, size=8))

    # ── Number cells: right-align ─────────────────────────────
    reqs.append(row_style(sid, 4, 2, 29, SUM_COLS, align="RIGHT"))

    # ── Label column: left-align ──────────────────────────────
    reqs.append(row_style(sid, 1, 1, 31, 2, align="LEFT"))

    # ── Freeze ────────────────────────────────────────────────
    reqs.append(freeze(sid, rows=2, cols=2))

    return reqs


# ─── PK & CR ──────────────────────────────────────────────────
# Exact 0-indexed rows:
#  0  PREPARED
#  1  Title
#  2  blank
#  3  Production Lot:
#  4  Month / Year:
#  5  blank
#  6  "A. MATERIAL — Input Quantities"
#  7  Items | GI Qty | GR Qty   (column header)
#  8  HRC Input Quantity
#  9  blank
# 10  "Material Cost"
# 11  Items | Amount | THB/MT   (column header)
# 12  Hot Rolled Coil used
# 13  % Yield Loss
# 14  blank
# 15  "B. PICKLING — Conversion Cost"
# 16  Items | Amount | THB/MT
# 17  Depreciation
# 18  " Labor" (header)
# 19  Direct Labor
# 20  Indirect Labor
# 21  " Material" (header)
# 22  Chemicals / Supplies
# 23  " Fuel & Power" (header)
# 24  Electricity
# 25  " Spare Parts & Supplies" (header)
# 26  Spare Parts
# 27  Repair & Maintenance
# 28  Other  (if oth_pk ≠ 0)
# 29  Pickling Conversion Cost  (total)
# 30  blank
# 31  "C. COLD ROLLING — Conversion Cost"
# 32  Items | Amount | THB/MT
# 33  Depreciation
# 34  " Labor"
# 35  Direct Labor
# 36  Indirect Labor
# 37  " Fuel & Power"
# 38  Electricity
# 39  " Spare Parts & Supplies"
# 40  Spare Parts
# 41  Repair & Maintenance
# 42  Cold Rolling Conversion Cost  (total)
# 43  blank
# 44  "D. PK & CR — COST SUMMARY"
# 45  Items | Amount | THB/MT
# 46  HRC Material Cost
# 47  Pickling Conversion
# 48  Cold Rolling Conversion
# 49  Less: Scrap Recovery
# 50  TOTAL CRC COST  (total)

PK_COLS = 8  # A B | Jan(C D) Feb(E F) Mar(G H)

def fmt_section(sid, row):
    return row_style(sid, row, 0, row+1, PK_COLS,
                     bg=NAVY, fg=WHITE, bold=True, size=10)

def fmt_col_hdr(sid, row):
    return row_style(sid, row, 0, row+1, PK_COLS,
                     bg=TBLUE, fg=c(31,63,100), bold=True, size=9, align="CENTER")

def fmt_sub_hdr(sid, row):
    return row_style(sid, row, 1, row+1, PK_COLS,
                     fg=DKGREY, bold=True, italic=True, size=9)

def fmt_total(sid, row):
    reqs = [row_style(sid, row, 0, row+1, PK_COLS, bg=LYELLOW, bold=True),
            border_top(sid, row, 0, PK_COLS),
            border_bottom(sid, row, 0, PK_COLS)]
    return reqs

def fmt_pk_cr(sid):
    reqs = []
    N_MONTHS = 3   # Jan Feb Mar

    reqs += [dims(sid, "COLUMNS", 0, 1, 16),
             dims(sid, "COLUMNS", 1, 2, 225)]
    for i in range(N_MONTHS):
        reqs.append(dims(sid, "COLUMNS", 2+i*2, 3+i*2, 120))  # Amount
        reqs.append(dims(sid, "COLUMNS", 3+i*2, 4+i*2,  95))  # THB/MT
    reqs += [dims(sid, "ROWS", 0,  1, 14),
             dims(sid, "ROWS", 1,  2, 28),
             dims(sid, "ROWS", 2, 55, 19)]

    reqs.append(row_style(sid, 0, 0, 55, PK_COLS, bg=WHITE, fg=BLACK, size=10))

    # PREPARED
    reqs.append(row_style(sid, 0, 0, 1, PK_COLS, fg=GREY, italic=True, size=8))
    # Title
    reqs.append(row_style(sid, 1, 0, 2, PK_COLS, bg=NAVY, fg=WHITE, bold=True, size=12))
    # Info rows (row 3=Production Lot, row 4=Month/Year)
    reqs.append(row_style(sid, 3, 1, 4, 2, bold=True))
    reqs.append(row_style(sid, 4, 1, 5, 2, bold=True))

    # Section A — month header row (row 7) with NAVY + merge each pair; data row (row 8)
    reqs.append(fmt_section(sid, 6))
    reqs.append(row_style(sid, 7, 0, 8, PK_COLS, bg=TBLUE, fg=c(31,63,100), bold=True, size=9, align="CENTER"))
    for i in range(N_MONTHS):
        reqs.append(merge_cells(sid, 7, 2+i*2, 8, 4+i*2))  # merge month name pair
    reqs.append(row_style(sid, 8, 0, 9, PK_COLS, bg=LORANGE))

    # Material Cost (rows 10-14)
    reqs.append(row_style(sid, 10, 1, 11, 2, bold=True, size=10))
    reqs.append(row_style(sid, 11, 0, 12, PK_COLS, bg=TBLUE, fg=c(31,63,100), bold=True, size=9, align="CENTER"))
    reqs.append(row_style(sid, 12, 0, 13, PK_COLS, bg=LORANGE, bold=True))
    reqs.append(row_style(sid, 13, 1, 14, 2, fg=DKGREY, italic=True))  # yield%

    # Section B (rows 15-30)
    reqs.append(fmt_section(sid, 15))
    reqs.append(row_style(sid, 16, 0, 17, PK_COLS, bg=TBLUE, fg=c(31,63,100), bold=True, size=9, align="CENTER"))
    for r in [18, 21, 23, 25]:
        reqs.append(fmt_sub_hdr(sid, r))
    for i, r in enumerate(range(17, 30)):
        if r not in (18, 21, 23, 25):
            bg_ = LBLUE if i % 2 == 0 else WHITE
            reqs.append(row_style(sid, r, 0, r+1, PK_COLS, bg=bg_))
    reqs += fmt_total(sid, 30)

    # Section C (rows 32-44)
    reqs.append(fmt_section(sid, 32))
    reqs.append(row_style(sid, 33, 0, 34, PK_COLS, bg=TBLUE, fg=c(31,63,100), bold=True, size=9, align="CENTER"))
    for r in [35, 38, 40]:
        reqs.append(fmt_sub_hdr(sid, r))
    for i, r in enumerate(range(34, 44)):
        if r not in (35, 38, 40):
            bg_ = LBLUE if i % 2 == 0 else WHITE
            reqs.append(row_style(sid, r, 0, r+1, PK_COLS, bg=bg_))
    reqs += fmt_total(sid, 44)

    # Section D summary (rows 46-52)
    reqs.append(fmt_section(sid, 46))
    reqs.append(row_style(sid, 47, 0, 48, PK_COLS, bg=TBLUE, fg=c(31,63,100), bold=True, size=9, align="CENTER"))
    for i, r in enumerate(range(48, 52)):
        bg_ = LORANGE if r == 48 else (LGREY if i % 2 == 0 else WHITE)
        reqs.append(row_style(sid, r, 0, r+1, PK_COLS, bg=bg_))
    reqs += fmt_total(sid, 52)

    # Number formats for all 3 month amount/THB-MT columns
    for i in range(N_MONTHS):
        ac, tc = 2+i*2, 3+i*2
        reqs.append(num(sid, 8, ac, 55, ac+1, "#,##0.00"))
        reqs.append(num(sid, 8, tc, 55, tc+1, "#,##0.00"))
    reqs.append(num(sid, 13, 3, 14, PK_COLS, "0.00%"))  # yield row

    reqs.append(row_style(sid, 8, 2, 55, PK_COLS, align="RIGHT"))
    reqs.append(row_style(sid, 4, 1, 55, 2, align="LEFT"))
    reqs.append(freeze(sid, rows=2, cols=2))

    return reqs


# ─── GI LINE ──────────────────────────────────────────────────
# Exact 0-indexed rows:
#  0  PREPARED
#  1  Title
#  2  blank
#  3  Production Lot:
#  4  Month / Year:
#  5  blank
#  6  "A. MATERIAL — Input Quantities"
#  7  Items | GI Qty | GR Qty
#  8  GI Line Input Quantity
#  9  blank
# 10  "Material Cost"
# 11  Items | Amount | THB/MT
# 12  GI Galvanized Coil GR (output MT)
# 13  CRC Used (at MAP)
# 14  Zinc Ingot Used
# 15  ZAM Alloy Used
# 16  blank
# 17  "Scrap Recovery"
# 18  Zinc Dross
# 19  Zinc Slag
# 20  Total Scrap Recovery
# 21  % Yield Loss
# 22  blank
# 23  "B. GALVANIZING — Conversion Cost"
# 24  Items | Amount | THB/MT
# 25  Depreciation
# 26  " Labor"
# 27  Direct Labor
# 28  Indirect Labor
# 29  Mfg Supplies
# 30  " Fuel & Power"
# 31  Electricity
# 32  " Spare Parts & Supplies"
# 33  Spare Parts
# 34  R&M
# 35  Other  (if oth≠0)
# 36  Galvanizing Conversion Cost  (total)
# 37  blank
# 38  "C. GI LINE — COST SUMMARY"
# 39  Items | Amount | THB/MT
# 40  CRC Cost
# 41  Zinc + ZAM Alloy
# 42  Galvanizing Conversion
# 43  Less: Scrap Recovery
# 44  TOTAL GI COST

GI_COLS = 8  # A B | Jan(C D) Feb(E F) Mar(G H)

def fmt_gi_line(sid):
    reqs = []
    N_MONTHS = 3

    reqs += [dims(sid, "COLUMNS", 0, 1, 16),
             dims(sid, "COLUMNS", 1, 2, 225)]
    for i in range(N_MONTHS):
        reqs.append(dims(sid, "COLUMNS", 2+i*2, 3+i*2, 120))
        reqs.append(dims(sid, "COLUMNS", 3+i*2, 4+i*2,  95))
    reqs += [dims(sid, "ROWS", 0,  1, 14),
             dims(sid, "ROWS", 1,  2, 28),
             dims(sid, "ROWS", 2, 55, 19)]

    reqs.append(row_style(sid, 0, 0, 55, GI_COLS, bg=WHITE, fg=BLACK, size=10))

    reqs.append(row_style(sid, 0, 0, 1, GI_COLS, fg=GREY, italic=True, size=8))
    reqs.append(row_style(sid, 1, 0, 2, GI_COLS, bg=NAVY, fg=WHITE, bold=True, size=12))
    reqs.append(row_style(sid, 3, 1, 4, 2, bold=True))
    reqs.append(row_style(sid, 4, 1, 5, 2, bold=True))

    # Section A
    reqs.append(fmt_section(sid, 6))
    reqs.append(row_style(sid, 7, 0, 8, GI_COLS, bg=TBLUE, fg=c(31,63,100), bold=True, size=9, align="CENTER"))
    for i in range(N_MONTHS):
        reqs.append(merge_cells(sid, 7, 2+i*2, 8, 4+i*2))
    reqs.append(row_style(sid, 8, 0, 9, GI_COLS, bg=LGREEN))

    # Material Cost (rows 10-16)
    reqs.append(row_style(sid, 10, 1, 11, 2, bold=True, size=10))
    reqs.append(row_style(sid, 11, 0, 12, GI_COLS, bg=TBLUE, fg=c(31,63,100), bold=True, size=9, align="CENTER"))
    reqs.append(row_style(sid, 12, 0, 13, GI_COLS, bg=LGREEN, bold=True))   # output MT
    reqs.append(row_style(sid, 13, 0, 14, GI_COLS, bg=LORANGE, bold=True))  # CRC used
    reqs.append(row_style(sid, 14, 0, 15, GI_COLS, bg=LORANGE))             # Zinc
    reqs.append(row_style(sid, 15, 0, 16, GI_COLS, bg=LORANGE))             # ZAM

    # Scrap Recovery (rows 17-22)
    reqs.append(row_style(sid, 17, 1, 18, 2, bold=True))
    reqs.append(row_style(sid, 18, 0, 19, GI_COLS, bg=LGREY))
    reqs.append(row_style(sid, 19, 0, 20, GI_COLS, bg=LGREY))
    reqs.append(row_style(sid, 20, 0, 21, GI_COLS, bg=LGREY, bold=True))
    reqs.append(row_style(sid, 21, 1, 22, 2, fg=DKGREY, italic=True))

    # Section B: Galvanizing Conversion (rows 23-37)
    reqs.append(fmt_section(sid, 23))
    reqs.append(row_style(sid, 24, 0, 25, GI_COLS, bg=TBLUE, fg=c(31,63,100), bold=True, size=9, align="CENTER"))
    for r in [26, 30, 32]:
        reqs.append(fmt_sub_hdr(sid, r))
    for i, r in enumerate(range(25, 37)):
        if r not in (26, 30, 32):
            bg_ = LGREEN if i % 2 == 0 else WHITE
            reqs.append(row_style(sid, r, 0, r+1, GI_COLS, bg=bg_))
    reqs += fmt_total(sid, 37)

    # Section C: Summary (rows 39-45)
    reqs.append(fmt_section(sid, 39))
    reqs.append(row_style(sid, 40, 0, 41, GI_COLS, bg=TBLUE, fg=c(31,63,100), bold=True, size=9, align="CENTER"))
    for i, r in enumerate(range(41, 45)):
        bg_ = LORANGE if r in (41, 42) else (LGREY if i % 2 == 0 else WHITE)
        reqs.append(row_style(sid, r, 0, r+1, GI_COLS, bg=bg_))
    reqs += fmt_total(sid, 45)

    # Number formats
    for i in range(N_MONTHS):
        ac, tc = 2+i*2, 3+i*2
        reqs.append(num(sid, 8, ac, 55, ac+1, "#,##0.00"))
        reqs.append(num(sid, 8, tc, 55, tc+1, "#,##0.00"))
    reqs.append(num(sid, 21, 3, 22, GI_COLS, "0.00%"))

    reqs.append(row_style(sid, 8, 2, 55, GI_COLS, align="RIGHT"))
    reqs.append(row_style(sid, 4, 1, 55, 2, align="LEFT"))
    reqs.append(freeze(sid, rows=2, cols=2))

    return reqs


# ─── MONITORING ──────────────────────────────────────────────
# 0  PREPARED
# 1  header: Metric | Unit | Jan..Dec
# 2  blank
# 3  "PICKLING & COLD ROLLING"
# 4  HRC Input
# 5  CRC Grade A
# 6  CRC Grade B
# 7  Scrap PK
# 8  % Yield Loss PK
# 9  Electricity — Pickling
# 10 Electricity — Cold Roll
# 11 HCl Consumption
# 12 Rolling Oil
# 13 blank
# 14 "GALVANIZING LINE"  (actually row 13 in 0-indexed from earlier read... adjust)
# ... (section header + rows)
# Cols: A(0) B(1)Metric C(2)Unit D(3)Jan...O(14)Dec

MON_COLS = 15

def fmt_monitoring(sid):
    reqs = []

    reqs += [dims(sid, "COLUMNS", 0, 1, 14),
             dims(sid, "COLUMNS", 1, 2, 210),
             dims(sid, "COLUMNS", 2, 3, 48),
             ]
    for c_ in range(3, 15):
        reqs.append(dims(sid, "COLUMNS", c_, c_+1, 72))

    reqs += [dims(sid, "ROWS", 0,  1, 14),
             dims(sid, "ROWS", 1,  2, 22),
             dims(sid, "ROWS", 2, 60, 18)]

    reqs.append(row_style(sid, 0, 0, 60, MON_COLS, bg=WHITE, fg=BLACK, size=10))
    reqs.append(row_style(sid, 0, 0, 1,  MON_COLS, fg=GREY, italic=True, size=8))

    # Header row
    reqs.append(row_style(sid, 1, 0, 2, MON_COLS, bg=NAVY, fg=WHITE))
    reqs.append(row_style(sid, 1, 1, 2, MON_COLS,
                          bg=NAVY, fg=WHITE, bold=True, size=10, align="LEFT"))
    reqs.append(row_style(sid, 1, 2, 2, MON_COLS,
                          bg=NAVY, fg=WHITE, bold=True, size=10, align="CENTER"))

    # Section headers (approx — row 3, 14, 27 from read earlier)
    for r in [2, 13, 26]:
        reqs.append(row_style(sid, r, 0, r+1, MON_COLS,
                              bg=BLUE, fg=WHITE, bold=True, size=10))

    # Yield rows
    for r in [8, 18]:
        reqs.append(row_style(sid, r, 0, r+1, MON_COLS,
                              bg=TBLUE, italic=True))
        reqs.append(num_pct(sid, r, 3, r+1, MON_COLS))

    # Alternating data rows
    for i in range(60):
        if i not in (0, 1, 2, 8, 13, 18, 26):
            bg_ = LGREY if i % 2 == 0 else WHITE
            reqs.append(row_style(sid, i, 0, i+1, MON_COLS, bg=bg_))

    reqs.append(row_style(sid, 4, 1, 60, 2, align="LEFT"))
    reqs.append(freeze(sid, rows=2, cols=2))

    return reqs


# ─── SUPPORT ─────────────────────────────────────────────────
SUP_COLS = 6   # A B(label) C D E F

def fmt_support(sid):
    reqs = []

    reqs += [dims(sid, "COLUMNS", 0, 1, 14),
             dims(sid, "COLUMNS", 1, 2, 260),
             dims(sid, "COLUMNS", 2, 3, 220),
             dims(sid, "COLUMNS", 3, 4, 160),
             dims(sid, "COLUMNS", 4, 5, 300),
             dims(sid, "COLUMNS", 5, 6, 280)]
    reqs.append(dims(sid, "ROWS", 0, 1, 14))
    reqs.append(dims(sid, "ROWS", 1, 2, 28))
    reqs.append(dims(sid, "ROWS", 2, 80, 18))

    reqs.append(row_style(sid, 0, 0, 80, SUP_COLS, bg=WHITE, fg=BLACK, size=10))
    reqs.append(row_style(sid, 0, 0, 1,  SUP_COLS, fg=GREY, italic=True, size=8))
    reqs.append(row_style(sid, 1, 0, 2,  SUP_COLS, bg=NAVY, fg=WHITE, bold=True, size=12))

    # Section header rows — navy blue bold (detect by looking at col B pattern)
    # Sections start at rows: 3, file_hdr=4, mapping_pk starts after file block, etc.
    # Since we can't know exact rows without reading the sheet, style all rows with
    # label starting with a digit as section headers via a broad pattern approach.
    # Instead, just style odd/even alternating for readability + bold header rows at known positions.
    # We'll use TBLUE for rows where the row looks like a section header (uppercase text).
    # Simplest: style every 3rd row lightly, keep it clean.

    # Alternating light background for readability
    for i in range(3, 80):
        bg_ = LGREY if i % 2 == 0 else WHITE
        reqs.append(row_style(sid, i, 0, i+1, SUP_COLS, bg=bg_))

    # Wrap text for long cells
    reqs.append(row_style(sid, 3, 0, 80, SUP_COLS, wrap="WRAP"))

    # Number/right-align: none — all text
    reqs.append(row_style(sid, 3, 1, 80, 2, align="LEFT", size=10))
    reqs.append(freeze(sid, rows=2, cols=2))

    return reqs


# ─── COMPONENTS ──────────────────────────────────────────────
# Tab at gid=694142505 — Production Components Reference
# Sections:
#   Row 0   PREPARED
#   Row 1   Title
#   Row 2   blank
#   Row 3   Section A header: "A. PICKLING & COLD ROLLING — Components"
#   Row 4   Column headers
#   Rows 5–16   PK & CR items (12)
#   Row 17  blank
#   Row 18  Section B header: "B. GALVANIZING LINE — Components"
# Components tab v2 — Excel format, mirrors PK & CR + GI Line with cross-refs
#
# Column layout (8 cols A–H):
#   A(0) spacer | B(1) Items | C(2) Jan Amt | D(3) Jan THB/MT
#   E(4) Feb Amt | F(5) Feb THB/MT | G(6) Mar Amt | H(7) Mar THB/MT
#
# Row layout (0-indexed):
#   0     PREPARED
#   1     Title
#   2–6   blank
#   7     A. PICKLING & COLD ROLLING  (NAVY)
#   8–9   col hdr + subhdr
#  10     Material sub-hdr
#  11–12  HRC mat, Yield Loss  (xref)
#  13     blank
#  14     B. PICKLING Conversion  (NAVY)
#  15     col subhdr
#  16–32  PK items, chemicals INPUT, totals
#  33     blank
#  34     PK Conv Total  (TOTAL)  — wait, sheet row 34 = 0-idx 33
#  35     blank
#  35     C. COLD ROLLING Conversion  (NAVY)
#  ...
#  59     TOTAL CRC COST  (TOTAL)
#  60–66  blank
#  67     B. GALVANIZING LINE  (ACCENT)
#  68–81  GI material + scrap
#  82     B. GALVANIZING Conversion  (ACCENT)
#  ...
#  102    blank
#  103–104 GI Conv Total, blank
#  104    C. GI LINE SUMMARY  (ACCENT)
#  110    TOTAL GI COST  (TOTAL)
#  111    blank

COMP_COLS = 8
_COMP_N   = 112   # total rows (0-indexed 0..111)

# 0-indexed row sets for styling
_SEC_NAVY   = {7, 14, 35, 53}
_SEC_ACCENT = {67, 82, 104}
_COL_HDRS   = {8, 9, 15, 36, 54, 68, 69, 83, 105}
_SUB_HDRS   = {10, 17, 20, 27, 29, 38, 41, 43, 47, 70, 76, 85, 88, 96, 98}
_TOTAL_ROWS = {33, 51, 59, 102, 110}
_INPUT_ROWS = {21, 22, 23, 24, 25, 44, 45, 46, 89, 90, 91, 92, 93, 94}
_GL_CHECK   = {26, 95}
_MAT_ROWS   = {11, 12, 71, 72, 73, 74}
_BLANK_ROWS = {2,3,4,5,6, 13, 32, 34, 60,61,62,63,64,65,66, 75, 81, 101, 103, 111}


def fmt_components(sid):
    reqs = []
    N = _COMP_N
    CC = COMP_COLS

    # ── Column widths (A–H) ────────────────────────────────────
    col_widths = [16, 225, 120, 95, 120, 95, 120, 95]
    for i, w in enumerate(col_widths):
        reqs.append(dims(sid, "COLUMNS", i, i+1, w))

    # ── Row heights ────────────────────────────────────────────
    reqs.append(dims(sid, "ROWS", 0,  1, 14))   # PREPARED: thin
    reqs.append(dims(sid, "ROWS", 1,  2, 28))   # Title
    reqs.append(dims(sid, "ROWS", 2, N, 19))    # all other rows

    # ── Base reset ─────────────────────────────────────────────
    reqs.append(row_style(sid, 0, 0, N, CC, bg=WHITE, fg=BLACK, size=10))

    # ── Row 0: PREPARED ────────────────────────────────────────
    reqs.append(row_style(sid, 0, 0, 1, CC, fg=GREY, italic=True, size=8))

    # ── Row 1: Title ───────────────────────────────────────────
    reqs.append(row_style(sid, 1, 0, 2, CC,
                          bg=NAVY, fg=WHITE, bold=True, size=12, align="LEFT"))

    # ── Section headers ────────────────────────────────────────
    for r in _SEC_NAVY:
        reqs.append(row_style(sid, r, 0, r+1, CC, bg=NAVY,   fg=WHITE, bold=True, size=10))
    for r in _SEC_ACCENT:
        reqs.append(row_style(sid, r, 0, r+1, CC, bg=ACCENT, fg=WHITE, bold=True, size=10))

    # ── Column header / sub-header rows ───────────────────────
    for r in _COL_HDRS:
        reqs.append(row_style(sid, r, 0, r+1, CC,
                              bg=TBLUE, fg=c(31,63,100), bold=True, size=9, align="CENTER"))
        reqs.append(row_style(sid, r, 1, r+1, 2,   # Items col: left-aligned
                              bg=TBLUE, fg=c(31,63,100), bold=True, size=9, align="LEFT"))

    # ── Sub-header rows (label only) ──────────────────────────
    for r in _SUB_HDRS:
        reqs.append(row_style(sid, r, 0, r+1, CC,
                              bg=LGREY, fg=c(80,80,80), bold=False, italic=True, size=9))

    # ── Total rows ─────────────────────────────────────────────
    for r in _TOTAL_ROWS:
        reqs.append(row_style(sid, r, 0, r+1, CC, bg=LYELLOW, bold=True))
        reqs.append(border_top(sid, r, 1, CC))

    # ── INPUT rows (blank amount cells) ───────────────────────
    for r in _INPUT_ROWS:
        reqs.append(row_style(sid, r, 0, r+1, CC, bg=WHITE))
        reqs.append(row_style(sid, r, 2, r+1, CC, bg=c(255,255,204)))  # light yellow input

    # ── GL check rows (lumped GL total from source) ────────────
    for r in _GL_CHECK:
        reqs.append(row_style(sid, r, 0, r+1, CC,
                              bg=LGREY, fg=c(100,100,100), italic=True, size=9))

    # ── Material reference rows ────────────────────────────────
    for r in _MAT_ROWS:
        reqs.append(row_style(sid, r, 0, r+1, CC, bg=LORANGE))
        reqs.append(row_style(sid, r, 1, r+1, 2, bg=LORANGE, bold=True))

    # ── Alternating rows for remaining data rows ───────────────
    _special = (_SEC_NAVY | _SEC_ACCENT | _COL_HDRS | _SUB_HDRS |
                _TOTAL_ROWS | _INPUT_ROWS | _GL_CHECK | _MAT_ROWS |
                _BLANK_ROWS | {0, 1})
    alt_idx = 0
    for r in range(2, N):
        if r not in _special:
            bg_ = LBLUE if alt_idx % 2 == 0 else WHITE
            reqs.append(row_style(sid, r, 0, r+1, CC, bg=bg_))
            alt_idx += 1

    # ── Column-level alignment ─────────────────────────────────
    # B (items label): left
    reqs.append(row_style(sid, 1, 1, N, 2, align="LEFT"))
    # C,E,G (amount cols): right, number format
    for ci in (2, 4, 6):
        reqs.append(row_style(sid, 2, ci, N, ci+1, align="RIGHT"))
        reqs.append(num(sid, 2, ci, N, ci+1, "#,##0"))
    # D,F,H (THB/MT cols): right, decimal
    for ci in (3, 5, 7):
        reqs.append(row_style(sid, 2, ci, N, ci+1, align="RIGHT"))
        reqs.append(num(sid, 2, ci, N, ci+1, "#,##0.00"))

    # ── Freeze: 2 rows + 2 cols ───────────────────────────────
    reqs.append(freeze(sid, rows=2, cols=2))

    return reqs


# ─── MAIN ────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("GI Template — Apply Professional Formatting")
    print("=" * 60)

    creds   = get_credentials()
    service = build("sheets", "v4", credentials=creds)

    meta   = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    sheets = {s["properties"]["title"]: s["properties"]["sheetId"]
              for s in meta["sheets"]}
    print("Tabs:", list(sheets.keys()))

    all_reqs = []
    tab_map = {
        "Annual Total": fmt_annual_total,
        "Summary":      fmt_summary,
        "PK & CR":      fmt_pk_cr,
        "GI Line":      fmt_gi_line,
        "Monitoring":   fmt_monitoring,
        "Support":      fmt_support,
        "Components":   fmt_components,
    }
    for title, fn in tab_map.items():
        if title in sheets:
            print(f"  Formatting {title}...")
            all_reqs += fn(sheets[title])

    print(f"\nSending {len(all_reqs)} formatting requests...")
    # Google API limit: 50k requests per batchUpdate; split into chunks
    CHUNK = 500
    for i in range(0, len(all_reqs), CHUNK):
        service.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={"requests": all_reqs[i:i+CHUNK]}
        ).execute()
        print(f"  Sent {min(i+CHUNK, len(all_reqs))}/{len(all_reqs)}")

    print("\nDONE")
    print(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}")
