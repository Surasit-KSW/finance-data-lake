"""
fix_master_formulas.py
======================
แก้ไข CO Close — Master sheet ใน Google Sheets ให้ดึง status จาก
sheet AMC / GA / STC อัตโนมัติ ด้วย INDEX/MATCH formula

ก่อน: ต้อง update status 2 ที่ (Master + company sheet) → Double work
หลัง: update ที่ company sheet เท่านั้น → Master อัพเดทตาม

Usage:
  python scripts/fix_master_formulas.py

Sheet ID: 196cPMmb_CPXif8NWPEVU6lG41rp72EQULeYE2LfOwwQ
"""

import sys
from pathlib import Path

# Add workspace root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import gspread
from utils.auth import get_credentials

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SPREADSHEET_ID  = "196cPMmb_CPXif8NWPEVU6lG41rp72EQULeYE2LfOwwQ"
MASTER_SHEET    = "CO Close \u2014 Master"   # em-dash

# Column indices in CO Close Master (1-based)
# A=1 No., B=2 Group, C=3 Step, D=4 Task EN, E=5 Task TH, F=6 T-Code,
# G=7 Owner, H=8 AMC-1100, I=9 AMC-1200, J=10 AMC-1300,
# K=11 GA-2100,  L=12 GA-2200,  M=13 STC-3100,  N=14 Remark
MASTER_STEP_COL = 3   # C = Step code ("010", "020", ...)
MASTER_NO_COL   = 1   # A = row number (present on data rows)

# Column indices in company sheets (1-based)
# A=1 No., B=2 Group, C=3 Step, D=4 Task, E=5 T-Code, F=6 Owner
# G=7 first plant, H=8 second plant, I=9 third plant (AMC only)
COMPANY_STEP_COL = 3  # C

# Mapping: (master_col_index) -> (source_sheet_name, source_col_letter)
# Master: plant status at I-N (9-14)
# Company sheets: plant col starts at H (8) after How-to col E added
FORMULA_MAP = {
    9:  ("AMC", "H"),   # AMC-1100  Master col I → AMC sheet col H
    10: ("AMC", "I"),   # AMC-1200  Master col J → AMC sheet col I
    11: ("AMC", "J"),   # AMC-1300  Master col K → AMC sheet col J
    12: ("GA",  "H"),   # GA-2100   Master col L → GA  sheet col H
    13: ("GA",  "I"),   # GA-2200   Master col M → GA  sheet col I
    14: ("STC", "H"),   # STC-3100  Master col N → STC sheet col H
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def col_letter(n: int) -> str:
    """1-based column index → letter (A, B, ..., Z, AA, ...)"""
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def make_formula(row: int, src_sheet: str, src_col: str) -> str:
    """
    สร้าง INDEX/MATCH formula ที่ดึง status จาก company sheet
    Match by step code (col C ใน Master, col C ใน company sheet)
    """
    step_ref = f"$C{row}"   # step code ใน Master (fixed col C, variable row)
    return (
        f"=IFERROR("
        f"INDEX('{src_sheet}'!${src_col}:${src_col},"
        f"MATCH({step_ref},'{src_sheet}'!$C:$C,0)),"
        f"\"N/A\")"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Connecting to Google Sheets...")
    creds  = get_credentials()
    client = gspread.authorize(creds)

    ss     = client.open_by_key(SPREADSHEET_ID)
    ws     = ss.worksheet(MASTER_SHEET)

    print(f"Opened: {ss.title} / {ws.title}")

    # Read all values to find data rows (rows where col A has a number)
    all_values = ws.get_all_values()
    total_rows = len(all_values)
    print(f"Total rows in sheet: {total_rows}")

    # Collect batch update cells
    updates = []   # list of {"range": "H4", "values": [[formula]]}

    data_row_count = 0
    for i, row_vals in enumerate(all_values):
        sheet_row = i + 1   # 1-based

        # Data rows: col A (index 0) contains a digit
        col_a = row_vals[0].strip() if row_vals else ""
        if not col_a.isdigit():
            continue   # header, group header, or empty row

        data_row_count += 1

        # Build formula for each plant column
        for master_col, (src_sheet, src_col) in FORMULA_MAP.items():
            cell_addr = f"{col_letter(master_col)}{sheet_row}"
            formula   = make_formula(sheet_row, src_sheet, src_col)
            updates.append({
                "range":  cell_addr,
                "values": [[formula]]
            })

    print(f"Data rows found: {data_row_count}")
    print(f"Cells to update: {len(updates)}")

    if not updates:
        print("Nothing to update. Exiting.")
        return

    # Batch update in chunks of 500 (Sheets API limit)
    chunk_size = 500
    for start in range(0, len(updates), chunk_size):
        chunk = updates[start : start + chunk_size]
        ws.batch_update(
            [{"range": u["range"], "values": u["values"]} for u in chunk],
            value_input_option="USER_ENTERED"   # interpret as formula
        )
        print(f"  Updated cells {start+1} - {start+len(chunk)}")

    print("\nDone! CO Close Master now pulls status from AMC / GA / STC sheets.")
    print("Update status ที่ company sheet เท่านั้น -- Master จะ sync อัตโนมัติ")


if __name__ == "__main__":
    main()
