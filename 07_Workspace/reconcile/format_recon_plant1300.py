"""
format_recon_plant1300.py
=========================
Standard formatting for Plant_1300_Cost_Recon_MM_YYYY sheets.

Reads each tab's content to detect row types, then applies:
  - Navy title row (row 0)
  - Section separators (rows starting with "─")
  - Column headers (blue + white bold)
  - Total rows (yellow + bold + top border)
  - MATCH rows (light green)
  - DIFF / WARNING rows (light orange)
  - Alternating rows for detail tabs
  - Frozen headers + column widths + number formats

Usage:
  python scripts/format_recon_plant1300.py --month 3
  python scripts/format_recon_plant1300.py --sheet-id 1nekT0yTy...
"""

import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.auth import get_credentials, get_gspread_client
from googleapiclient.discovery import build

YEAR = 2026
MONTH_NAMES = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
               7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}

# ─── Colour palette (matches format_gi_template.py) ──────────────────────────
def c(r, g, b): return {"red": r/255, "green": g/255, "blue": b/255}

NAVY    = c(31,  56,  98)   # title rows
BLUE    = c(47,  85, 151)   # column headers
ACCENT  = c(68, 114, 196)   # section separators
TBLUE   = c(189, 215, 238)  # light section / sub-header
LBLUE   = c(221, 235, 247)  # data light blue
LGREEN  = c(198, 224, 180)  # MATCH
LYELLOW = c(255, 242, 204)  # total / neutral info
LORANGE = c(252, 228, 214)  # DIFF / WARNING
LGREY   = c(242, 242, 242)  # prepared-by / alternate
LGREY2  = c(248, 248, 248)  # alternate row 2 (near-white)
WHITE   = c(255, 255, 255)
BLACK   = c(0,   0,   0)
GREY60  = c(100, 100, 100)
GREY80  = c(80,  80,  80)

# ─── API helpers ─────────────────────────────────────────────────────────────
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

def row_h(sid, r, px):
    return {"updateDimensionProperties": {
        "range": {"sheetId": sid, "dimension": "ROWS",
                  "startIndex": r, "endIndex": r+1},
        "properties": {"pixelSize": px}, "fields": "pixelSize"}}

def cell_fmt(sid, r1, c1, r2, c2,
             bg=None, fg=BLACK, bold=False, italic=False,
             size=10, halign=None, valign="MIDDLE",
             wrap=None, num_fmt=None):
    tf = {"fontSize": size, "bold": bold, "italic": italic, "foregroundColor": fg}
    fmt = {"textFormat": tf, "verticalAlignment": valign}
    if bg:      fmt["backgroundColor"] = bg
    if halign:  fmt["horizontalAlignment"] = halign
    if wrap:    fmt["wrapStrategy"] = wrap
    if num_fmt: fmt["numberFormat"] = num_fmt
    fields = ["textFormat", "verticalAlignment"]
    if bg:      fields.append("backgroundColor")
    if halign:  fields.append("horizontalAlignment")
    if wrap:    fields.append("wrapStrategy")
    if num_fmt: fields.append("numberFormat")
    return repeat(sid, r1, c1, r2, c2, fmt, ",".join(fields))

def border_top(sid, row, c1, c2, style="SOLID_MEDIUM"):
    b = {"style": style, "color": GREY60}
    return repeat(sid, row, c1, row+1, c2,
                  {"borders": {"top": b}}, "borders")

def border_bottom(sid, row, c1, c2, style="SOLID"):
    b = {"style": style, "color": GREY60}
    return repeat(sid, row, c1, row+1, c2,
                  {"borders": {"bottom": b}}, "borders")

def merge(sid, r1, c1, r2, c2):
    return {"mergeCells": {"range": rng(sid, r1, c1, r2, c2),
                           "mergeType": "MERGE_ALL"}}

def num(sid, r1, c1, r2, c2, pattern):
    return repeat(sid, r1, c1, r2, c2,
                  {"numberFormat": {"type": "NUMBER", "pattern": pattern}},
                  "numberFormat")


# ─── Row type detector ───────────────────────────────────────────────────────
def classify_row(row_vals):
    """Return row type string based on cell content."""
    flat = " ".join(str(v) for v in row_vals if v is not None and str(v).strip())
    if not flat: return "blank"

    first = str(row_vals[0]).strip() if row_vals[0] else ""
    second = str(row_vals[1]).strip() if len(row_vals) > 1 and row_vals[1] else ""
    text = first or second

    # Detect by content patterns
    if text.startswith("─") or text.startswith("─" * 3):
        return "section"
    if any(k in flat for k in ("Prepared by:", "Prepared by :")):
        return "subtitle"
    if any(k in flat for k in ("[!]  WARNINGS", "[!] WARNINGS")):
        return "warning_hdr"
    if flat.startswith("[!]"):
        return "warning"
    if any(k in flat for k in ("CKMLCP", "Material Ledger", "CKMLCP / MATERIAL")):
        return "context_hdr" if text.startswith("─") else "context"
    if any(k in flat for k in ("══ ", " ══", "GRAND TOTAL", "═══")):
        return "grand_total"
    if any(k in flat for k in ("── GL Overhead Total", "── KSB1", "── TB Total",
                                "── D101", "── D102", "── GL CC", "── MB51",
                                "── CRC TOTAL", "── GI TOTAL", "── KSB1 Grand")):
        return "subtotal"
    if text in ("TOTAL", "GRAND TOTAL") or flat.startswith("TOTAL "):
        return "grand_total"
    if "MATCH" in flat and "DIFF" not in flat:
        return "match"
    if "DIFF" in flat or "UNBALANCED" in flat:
        return "diff"
    if "BALANCED" in flat:
        return "match"
    if "SKIP" in flat:
        return "skip"
    # Column header rows: first cell is a known header keyword
    header_kws = ("Category", "Layer", "Source", "Metric", "Items", "GL Account",
                  "Cost Element", "CC Code", "Item", "Check", "Line", "Plant",
                  "CC", "Material", "Posting Date")
    if any(text.startswith(k) for k in header_kws):
        return "col_header"
    return "data"


# ─── Summary tab formatter ────────────────────────────────────────────────────
def fmt_summary(service, sid, ws, n_data_cols=6):
    """Format a summary/reconciliation tab by reading its content."""
    reqs = []

    # Read all values
    values = ws.get_all_values()
    n_rows = len(values)
    if n_rows == 0:
        return reqs

    # Column widths: A=20 B=260 C=150 D=130 E=120 F=180
    col_widths = [20, 260, 150, 130, 120, 180]
    for ci, px in enumerate(col_widths):
        reqs.append(dims(sid, "COLUMNS", ci, ci+1, px))

    # Row 0: title
    reqs += [
        row_h(sid, 0, 34),
        cell_fmt(sid, 0, 0, 1, n_data_cols, bg=NAVY, fg=WHITE, bold=True, size=12,
                 valign="MIDDLE", halign="LEFT"),
        merge(sid, 0, 0, 1, n_data_cols),
    ]

    # Classify and format each row
    for ri, row_vals in enumerate(values):
        if ri == 0:
            continue  # already done

        rtype = classify_row(row_vals)

        if rtype == "subtitle":
            reqs += [
                row_h(sid, ri, 20),
                cell_fmt(sid, ri, 0, ri+1, n_data_cols,
                         bg=LGREY, fg=GREY80, italic=True, size=9),
            ]

        elif rtype == "blank":
            reqs.append(row_h(sid, ri, 8))

        elif rtype == "section":
            reqs += [
                row_h(sid, ri, 22),
                cell_fmt(sid, ri, 0, ri+1, n_data_cols,
                         bg=ACCENT, fg=WHITE, bold=True, size=10),
            ]

        elif rtype == "context_hdr":
            reqs += [
                row_h(sid, ri, 22),
                cell_fmt(sid, ri, 0, ri+1, n_data_cols,
                         bg=BLUE, fg=WHITE, bold=True, size=10),
            ]

        elif rtype == "context":
            reqs += [
                row_h(sid, ri, 20),
                cell_fmt(sid, ri, 0, ri+1, n_data_cols,
                         bg=LBLUE, fg=GREY80, size=9, italic=True),
            ]

        elif rtype == "col_header":
            reqs += [
                row_h(sid, ri, 24),
                cell_fmt(sid, ri, 0, ri+1, n_data_cols,
                         bg=BLUE, fg=WHITE, bold=True, size=10),
                border_bottom(sid, ri, 0, n_data_cols),
            ]

        elif rtype == "grand_total":
            reqs += [
                row_h(sid, ri, 26),
                cell_fmt(sid, ri, 0, ri+1, n_data_cols,
                         bg=LYELLOW, fg=BLACK, bold=True, size=10),
                border_top(sid, ri, 0, n_data_cols),
            ]

        elif rtype == "subtotal":
            reqs += [
                row_h(sid, ri, 22),
                cell_fmt(sid, ri, 0, ri+1, n_data_cols,
                         bg=TBLUE, fg=BLACK, bold=True, size=10),
                border_top(sid, ri, 0, n_data_cols, style="SOLID"),
            ]

        elif rtype == "warning_hdr":
            reqs += [
                row_h(sid, ri, 24),
                cell_fmt(sid, ri, 0, ri+1, n_data_cols,
                         bg=LORANGE, fg=BLACK, bold=True, size=10),
            ]

        elif rtype == "warning":
            reqs += [
                row_h(sid, ri, 20),
                cell_fmt(sid, ri, 0, ri+1, n_data_cols,
                         bg=LORANGE, fg=GREY80, size=9, italic=True),
            ]

        elif rtype == "match":
            reqs.append(cell_fmt(sid, ri, 0, ri+1, n_data_cols,
                                  bg=LGREEN, fg=BLACK, size=10))

        elif rtype == "diff":
            reqs.append(cell_fmt(sid, ri, 0, ri+1, n_data_cols,
                                  bg=LORANGE, fg=BLACK, bold=True, size=10))

        elif rtype == "skip":
            reqs.append(cell_fmt(sid, ri, 0, ri+1, n_data_cols,
                                  bg=LGREY, fg=GREY80, italic=True, size=10))

        else:  # data
            bg = WHITE if ri % 2 == 0 else LGREY2
            reqs.append(cell_fmt(sid, ri, 0, ri+1, n_data_cols,
                                  bg=bg, fg=BLACK, size=10))

    # Freeze row 2 (title + subtitle stay visible)
    reqs.append(freeze(sid, rows=2))
    return reqs


# ─── Detail tab formatter ─────────────────────────────────────────────────────
def fmt_detail(service, sid, ws, col_widths, amount_cols=None):
    """Format a raw-data detail tab."""
    reqs = []
    values = ws.get_all_values()
    n_rows = len(values)
    n_cols = len(col_widths)

    # Column widths
    for ci, px in enumerate(col_widths):
        reqs.append(dims(sid, "COLUMNS", ci, ci+1, px))

    # Row 0: title (navy)
    reqs += [
        row_h(sid, 0, 32),
        cell_fmt(sid, 0, 0, 1, n_cols, bg=NAVY, fg=WHITE, bold=True, size=11,
                 halign="LEFT"),
        merge(sid, 0, 0, 1, n_cols),
    ]

    # Row 1: column headers (blue)
    reqs += [
        row_h(sid, 1, 24),
        cell_fmt(sid, 1, 0, 2, n_cols, bg=BLUE, fg=WHITE, bold=True, size=10),
        border_bottom(sid, 1, 0, n_cols),
    ]

    # Data rows: alternating
    for ri in range(2, min(n_rows, 5002)):
        bg = WHITE if ri % 2 == 0 else LGREY2
        reqs.append(cell_fmt(sid, ri, 0, ri+1, n_cols, bg=bg, size=9))

    # Amount columns: right-align + number format
    if amount_cols:
        for ci in amount_cols:
            reqs.append(cell_fmt(sid, 2, ci, n_rows, ci+1,
                                  halign="RIGHT", size=9))
            reqs.append(num(sid, 2, ci, n_rows, ci+1, "#,##0.00"))

    # Freeze row 2
    reqs.append(freeze(sid, rows=2))
    return reqs


# ─── Sources tab formatter ────────────────────────────────────────────────────
def fmt_sources(service, sid, ws):
    """Format Sources tab — wider B column, section headers."""
    reqs = []
    values = ws.get_all_values()
    n_rows = len(values)

    col_widths = [240, 200, 200, 320]
    for ci, px in enumerate(col_widths):
        reqs.append(dims(sid, "COLUMNS", ci, ci+1, px))

    # Row 0: title
    reqs += [
        row_h(sid, 0, 34),
        cell_fmt(sid, 0, 0, 1, 4, bg=NAVY, fg=WHITE, bold=True, size=12),
        merge(sid, 0, 0, 1, 4),
    ]

    for ri, row_vals in enumerate(values):
        if ri == 0: continue
        rtype = classify_row(row_vals)
        if rtype == "subtitle":
            reqs += [row_h(sid, ri, 20),
                     cell_fmt(sid, ri, 0, ri+1, 4, bg=LGREY, fg=GREY80, italic=True, size=9)]
        elif rtype == "blank":
            reqs.append(row_h(sid, ri, 8))
        elif rtype == "section":
            reqs += [row_h(sid, ri, 22),
                     cell_fmt(sid, ri, 0, ri+1, 4, bg=ACCENT, fg=WHITE, bold=True, size=10)]
        elif rtype == "col_header":
            reqs += [row_h(sid, ri, 24),
                     cell_fmt(sid, ri, 0, ri+1, 4, bg=BLUE, fg=WHITE, bold=True, size=10),
                     border_bottom(sid, ri, 0, 4)]
        else:
            bg = WHITE if ri % 2 == 0 else LGREY2
            reqs.append(cell_fmt(sid, ri, 0, ri+1, 4, bg=bg, size=9,
                                  wrap="WRAP"))

    reqs.append(freeze(sid, rows=2))
    return reqs


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Format Plant 1300 Cost Recon sheet")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--month", type=int, help="Month number (1–4)")
    grp.add_argument("--sheet-id", help="Google Sheet ID directly")
    args = parser.parse_args()

    if args.month:
        mn = MONTH_NAMES[args.month]
        sheet_name = f"Plant_1300_Cost_Recon_{mn}_{YEAR}"
        gc = get_gspread_client()
        sh = gc.open(sheet_name)
        sheet_id = sh.id
        print(f"Sheet: {sheet_name} ({sheet_id})")
    else:
        sheet_id = args.sheet_id
        gc = get_gspread_client()
        sh = gc.open_by_key(sheet_id)
        print(f"Sheet: {sh.title} ({sheet_id})")

    creds = get_credentials()
    service = build("sheets", "v4", credentials=creds)

    # Get all worksheets
    tabs = {ws.title: ws for ws in sh.worksheets()}
    tab_ids = {ws.title: ws.id for ws in sh.worksheets()}
    print(f"Tabs: {list(tabs.keys())}")

    all_reqs = []

    # ── Summary tabs ─────────────────────────────────────────────────────────
    SUMMARY_TABS = ["Overview", "Cost_BuildUp", "GL_vs_TB",
                    "GL_vs_KSB1", "KSB1_vs_PRD", "MB51_vs_PRD"]
    for tname in SUMMARY_TABS:
        if tname not in tabs:
            print(f"  Skip (not found): {tname}")
            continue
        print(f"  Formatting {tname}...")
        sid = tab_ids[tname]
        ws  = tabs[tname]
        all_reqs += fmt_summary(service, sid, ws, n_data_cols=6)

    # ── Sources tab ───────────────────────────────────────────────────────────
    if "Sources" in tabs:
        print("  Formatting Sources...")
        all_reqs += fmt_sources(service, tab_ids["Sources"], tabs["Sources"])

    # ── Detail tabs ───────────────────────────────────────────────────────────
    # GL_Detail: CC | GL Acct | Name | DocType | Date | Amount | Status
    if "GL_Detail" in tabs:
        print("  Formatting GL_Detail...")
        all_reqs += fmt_detail(service, tab_ids["GL_Detail"], tabs["GL_Detail"],
                               col_widths=[90, 80, 230, 65, 90, 120, 75],
                               amount_cols=[5])

    # KSB1_Detail: CC | CostElem | Name | Amount
    if "KSB1_Detail" in tabs:
        print("  Formatting KSB1_Detail...")
        all_reqs += fmt_detail(service, tab_ids["KSB1_Detail"], tabs["KSB1_Detail"],
                               col_widths=[90, 90, 250, 120],
                               amount_cols=[3])

    # PRD_Detail: Line | OrderType | Material | Desc | WC | GI_Mat | Scrap | GrB | GrC | GR_QTY | GR_THB | D101 | D102 | Indirect
    if "PRD_Detail" in tabs:
        print("  Formatting PRD_Detail...")
        all_reqs += fmt_detail(service, tab_ids["PRD_Detail"], tabs["PRD_Detail"],
                               col_widths=[60, 80, 80, 180, 55,
                                           105, 95, 85, 85,
                                           95, 105, 90, 90, 95],
                               amount_cols=[5, 6, 7, 8, 9, 10, 11, 12, 13])

    # MB51_Detail: Plant | Mvt | Date | Material | Desc | Amount
    if "MB51_Detail" in tabs:
        print("  Formatting MB51_Detail...")
        all_reqs += fmt_detail(service, tab_ids["MB51_Detail"], tabs["MB51_Detail"],
                               col_widths=[55, 50, 90, 90, 200, 120],
                               amount_cols=[5])

    # ── Execute ───────────────────────────────────────────────────────────────
    print(f"\nTotal format requests: {len(all_reqs)}")

    BATCH = 400
    for i in range(0, len(all_reqs), BATCH):
        batch = all_reqs[i:i+BATCH]
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": batch}
        ).execute()
        print(f"  Sent batch {i//BATCH + 1}/{(len(all_reqs)-1)//BATCH + 1} ({len(batch)} reqs)")

    print(f"\nDone!  {sh.url}")


if __name__ == "__main__":
    main()
