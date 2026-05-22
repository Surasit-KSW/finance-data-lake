"""
setup_gi_components.py  v2
Populate the Components tab in Plant_GI_Costing_Template_2026.
Mirrors the PK & CR and GI Line tabs with cross-reference formulas.
Items not tracked in source tabs are blank INPUT cells.

Sheet  : 1Q-JFK0zPNWaHs77Nu-VLDaNkem0-netkF1CcLt4i76U
Tab    : "Components"  (created if not exists)

Column layout (A–H, 8 cols):
  A = spacer | B = Items | C = Jan Amt | D = Jan THB/MT
  E = Feb Amt | F = Feb THB/MT | G = Mar Amt | H = Mar THB/MT

Source tab row references (1-indexed sheet rows):
  PK & CR   GR_ROW = 9  (D9/F9/H9 = Jan/Feb/Mar CRC output qty, kg)
  GI Line   GR_ROW = 9  (D9/F9/H9 = Jan/Feb/Mar GI output qty, kg)

Usage:
  python scripts/setup_gi_components.py            # write to sheet
  python scripts/setup_gi_components.py --dry-run  # preview rows only

Prepared by: Claude Code
"""

import argparse, sys, os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SHEET_ID = "1Q-JFK0zPNWaHs77Nu-VLDaNkem0-netkF1CcLt4i76U"
TAB_NAME = "Components"
NOW      = datetime.now().strftime("%d/%m/%Y %H:%M")
PREPARED = f"Prepared by: Claude Code | {NOW}"

# ── Column helpers ────────────────────────────────────────────────
def col_letter(n):
    """1-based column index → letter.  1=A, 2=B, ..., 26=Z, 27=AA …"""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s

MONTHS = 3
MNAMES = ["January", "February", "March"]

def amt_col(m): return col_letter(3 + m * 2)   # m=0→C, 1→E, 2→G
def thb_col(m): return col_letter(4 + m * 2)   # m=0→D, 1→F, 2→H

# ── Source row references (1-indexed sheet rows) ──────────────────
PK_GR = 9   # 'PK & CR' CRC output qty row
GI_GR = 9   # 'GI Line' GI output qty row

# PK & CR tab rows
PK = dict(
    hrc_mat=13,
    yield_loss=14,
    dep=18, dl=20, il=21, chem=23, elec=25, sp=27, rm=28, pk_total=29,
    dep_cr=33, dl_cr=35, il_cr=36, elec_cr=38, sp_cr=40, rm_cr=41, cr_total=42,
    hrc_sum=46, pk_conv=47, cr_conv=48, scrap=49, total=50,
)

# GI Line tab rows
GI = dict(
    gi_out_mt=13, crc_used=14, zinc=15, zam=16,
    dross=19, slag=20, scrap_total=21, yield_loss=22,
    dep=26, dl=28, il=29, mfg=30, elec=32, sp=34, rm=35, gi_conv=36,
    crc_cost=40, zinc_zam=41, gi_conv_sum=42, scrap_sum=43, total=44,
)


# ── Row builders ──────────────────────────────────────────────────
def pk_xref(label, src_row):
    """Pull amount + THB/MT directly from 'PK & CR' source row."""
    vals = []
    for m in range(MONTHS):
        vals += [f"='PK & CR'!{amt_col(m)}{src_row}",
                 f"='PK & CR'!{thb_col(m)}{src_row}"]
    return ["", label] + vals


def gi_xref(label, src_row):
    """Pull amount + THB/MT directly from 'GI Line' source row."""
    vals = []
    for m in range(MONTHS):
        vals += [f"='GI Line'!{amt_col(m)}{src_row}",
                 f"='GI Line'!{thb_col(m)}{src_row}"]
    return ["", label] + vals


def pk_inp(label, dest_row):
    """Blank INPUT cell; THB/MT computed using PK & CR GR qty."""
    return ["", label] + [
        v for m in range(MONTHS)
        for v in ["",
                  f"=IFERROR({amt_col(m)}{dest_row}/('PK & CR'!{thb_col(m)}{PK_GR}/1000),\"\")"]
    ]


def gi_inp(label, dest_row):
    """Blank INPUT cell; THB/MT computed using GI Line GR qty."""
    return ["", label] + [
        v for m in range(MONTHS)
        for v in ["",
                  f"=IFERROR({amt_col(m)}{dest_row}/('GI Line'!{thb_col(m)}{GI_GR}/1000),\"\")"]
    ]


def col_hdr():
    return ["", "Items"] + [v for m in range(MONTHS) for v in [MNAMES[m], ""]]


def col_subhdr():
    return ["", ""] + ["Amount (THB)", "THB/MT"] * MONTHS


def sec(label): return ["", label]
def sub(label): return ["", label]
def blank():    return ["", ""]


# ── Main row builder ──────────────────────────────────────────────
def build_rows():
    """
    Build all rows for the Components tab.
    Row numbers are 1-indexed (sheet rows).  Tracked via len(rows)+1.

    Row layout summary:
      1     PREPARED
      2     Title
      3–7   blank
      8     A. PICKLING & COLD ROLLING  (NAVY)
      9     col hdr
      10    col subhdr
      11    Material sub-hdr
      12    HRC Material Cost (xref pk13)
      13    % Yield Loss (xref pk14)
      14    blank
      15    B. PICKLING Conversion (NAVY)
      16    col subhdr
      17    Depreciation (xref pk18)
      18    Labor sub-hdr
      19    Direct Labor (xref pk20)
      20    Indirect Labor (xref pk21)
      21    Chemicals sub-hdr
      22–26 HCl22/35/18, Inhibitor, Waste HCl (INPUT)
      27    Chemicals Total GL138711 (xref pk23)
      28    Fuel sub-hdr
      29    Electricity (xref pk25)
      30    Spare Parts sub-hdr
      31    Spare Parts (xref pk27)
      32    R&M (xref pk28)
      33    blank
      34    Pickling Conversion Cost (xref pk29)  TOTAL
      35    blank
      36    C. COLD ROLLING Conversion (NAVY)
      37    col subhdr
      38    Depreciation CR (xref pk33)
      39    Labor sub-hdr
      40    DL CR (xref pk35)
      41    IL CR (xref pk36)
      42    Fuel sub-hdr
      43    Electricity CR (xref pk38)
      44    Rolling Consumables sub-hdr
      45–47 Rolling Oil, Working Roll, Supporting Roll (INPUT)
      48    Spare Parts sub-hdr
      49    Spare Parts CR (xref pk40)
      50    R&M CR (xref pk41)
      51    blank
      52    Cold Rolling Conversion Cost (xref pk42)  TOTAL
      53    blank
      54    D. PK&CR SUMMARY (NAVY)
      55    col subhdr
      56    HRC Material (xref pk46)
      57    Pickling Conv (xref pk47)
      58    CR Conv (xref pk48)
      59    Scrap (xref pk49)
      60    TOTAL CRC COST (xref pk50)  TOTAL
      61–67 blank
      68    B. GALVANIZING LINE  (ACCENT)
      69    col hdr
      70    col subhdr
      71    Material sub-hdr
      72    GI Output MT (xref gi13)
      73    CRC Used (xref gi14)
      74    Zinc Ingot (xref gi15)
      75    ZAM Alloy (xref gi16)
      76    blank
      77    Scrap Recovery sub-hdr
      78    Zinc Dross (xref gi19)
      79    Zinc Slag (xref gi20)
      80    Total Scrap Recovery (xref gi21)
      81    % Yield Loss (xref gi22)
      82    blank
      83    B. GALVANIZING Conversion (ACCENT)
      84    col subhdr
      85    Depreciation GI (xref gi26)
      86    Labor sub-hdr
      87    DL GI (xref gi28)
      88    IL GI (xref gi29)
      89    Mfg Supplies sub-hdr
      90–95 LNG, N2, H2, Passivation, NaOH, Defoamer (INPUT)
      96    Mfg Supplies Total GL13872 (xref gi30)
      97    Fuel sub-hdr
      98    Electricity GI (xref gi32)
      99    Spare Parts sub-hdr
      100   Spare Parts GI (xref gi34)
      101   R&M GI (xref gi35)
      102   blank
      103   Galvanizing Conversion Cost (xref gi36)  TOTAL
      104   blank
      105   C. GI LINE SUMMARY (ACCENT)
      106   col subhdr
      107   CRC Cost (xref gi40)
      108   Zinc+ZAM (xref gi41)
      109   GI Conv (xref gi42)
      110   Scrap (xref gi43)
      111   TOTAL GI COST (xref gi44)  TOTAL
      112   blank
    """
    rows = []

    def cur():
        return len(rows) + 1   # 1-indexed sheet row of the NEXT row

    # ── Header ────────────────────────────────────────────────
    rows.append([PREPARED])                                         # 1
    rows.append(["", "ASIA METAL PLC — Production Components / ส่วนประกอบการผลิต"])  # 2
    for _ in range(5):
        rows.append(blank())                                        # 3–7

    # ═════════════════════════════════════════════════════════
    # PICKLING & COLD ROLLING
    # ═════════════════════════════════════════════════════════
    rows.append(sec("A. PICKLING & COLD ROLLING"))                  # 8
    rows.append(col_hdr())                                          # 9
    rows.append(col_subhdr())                                       # 10

    rows.append(sub(" Material"))                                   # 11
    rows.append(pk_xref(" HRC Material Cost",    PK["hrc_mat"]))   # 12
    rows.append(pk_xref(" % Yield Loss",         PK["yield_loss"])) # 13
    rows.append(blank())                                            # 14

    # ── B. Pickling ───────────────────────────────────────────
    rows.append(sec("B. PICKLING — Conversion Cost"))               # 15
    rows.append(col_subhdr())                                       # 16

    rows.append(pk_xref("  Depreciation",        PK["dep"]))       # 17

    rows.append(sub(" Labor"))                                      # 18
    rows.append(pk_xref("  Direct Labor",         PK["dl"]))       # 19
    rows.append(pk_xref("  Indirect Labor",       PK["il"]))       # 20

    rows.append(sub(" Chemicals & Supplies"))                       # 21
    rows.append(pk_inp("  HCl 22%",               cur()))          # 22
    rows.append(pk_inp("  HCl 35%",               cur()))          # 23
    rows.append(pk_inp("  HCl 18%",               cur()))          # 24
    rows.append(pk_inp("  Inhibitor",             cur()))          # 25
    rows.append(pk_inp("  Waste HCl (Recovery)",  cur()))          # 26
    rows.append(pk_xref("  Chemicals Total (GL 138711)",
                        PK["chem"]))                                # 27

    rows.append(sub(" Fuel & Power"))                               # 28
    rows.append(pk_xref("  Electricity",          PK["elec"]))     # 29

    rows.append(sub(" Spare Parts & Supplies"))                     # 30
    rows.append(pk_xref("  Spare Parts",          PK["sp"]))       # 31
    rows.append(pk_xref("  Repair & Maintenance", PK["rm"]))       # 32
    rows.append(blank())                                            # 33

    rows.append(pk_xref("Pickling Conversion Cost", PK["pk_total"])) # 34
    rows.append(blank())                                            # 35

    # ── C. Cold Rolling ───────────────────────────────────────
    rows.append(sec("C. COLD ROLLING — Conversion Cost"))           # 36
    rows.append(col_subhdr())                                       # 37

    rows.append(pk_xref("  Depreciation",         PK["dep_cr"]))   # 38

    rows.append(sub(" Labor"))                                      # 39
    rows.append(pk_xref("  Direct Labor",          PK["dl_cr"]))   # 40
    rows.append(pk_xref("  Indirect Labor",        PK["il_cr"]))   # 41

    rows.append(sub(" Fuel & Power"))                               # 42
    rows.append(pk_xref("  Electricity",           PK["elec_cr"])) # 43

    rows.append(sub(" Rolling Consumables"))                        # 44
    rows.append(pk_inp("  Rolling Oil",            cur()))          # 45
    rows.append(pk_inp("  Working Roll (GL 5912030)", cur()))       # 46
    rows.append(pk_inp("  Supporting Roll (GL 5912030)", cur()))    # 47

    rows.append(sub(" Spare Parts & Supplies"))                     # 48
    rows.append(pk_xref("  Spare Parts",           PK["sp_cr"]))   # 49
    rows.append(pk_xref("  Repair & Maintenance",  PK["rm_cr"]))   # 50
    rows.append(blank())                                            # 51

    rows.append(pk_xref("Cold Rolling Conversion Cost", PK["cr_total"])) # 52
    rows.append(blank())                                            # 53

    # ── D. PK & CR Summary ────────────────────────────────────
    rows.append(sec("D. PK & CR — COST SUMMARY"))                  # 54
    rows.append(col_subhdr())                                       # 55

    rows.append(pk_xref(" HRC Material Cost",      PK["hrc_sum"])) # 56
    rows.append(pk_xref(" Pickling Conversion",    PK["pk_conv"])) # 57
    rows.append(pk_xref(" Cold Rolling Conversion",PK["cr_conv"])) # 58
    rows.append(pk_xref(" Less: Scrap Recovery",   PK["scrap"]))   # 59
    rows.append(pk_xref("TOTAL CRC COST",          PK["total"]))   # 60

    for _ in range(7):
        rows.append(blank())                                        # 61–67

    # ═════════════════════════════════════════════════════════
    # GALVANIZING LINE
    # ═════════════════════════════════════════════════════════
    rows.append(sec("B. GALVANIZING LINE"))                         # 68
    rows.append(col_hdr())                                          # 69
    rows.append(col_subhdr())                                       # 70

    rows.append(sub(" Material"))                                   # 71
    rows.append(gi_xref(" GI Output (MT)",         GI["gi_out_mt"])) # 72
    rows.append(gi_xref(" CRC Used",               GI["crc_used"])) # 73
    rows.append(gi_xref(" Zinc Ingot",             GI["zinc"]))    # 74
    rows.append(gi_xref(" ZAM Alloy",              GI["zam"]))     # 75
    rows.append(blank())                                            # 76

    rows.append(sub(" Scrap Recovery"))                             # 77
    rows.append(gi_xref("  Zinc Dross",            GI["dross"]))   # 78
    rows.append(gi_xref("  Zinc Slag",             GI["slag"]))    # 79
    rows.append(gi_xref("  Total Scrap Recovery",  GI["scrap_total"])) # 80
    rows.append(gi_xref("  % Yield Loss",          GI["yield_loss"])) # 81
    rows.append(blank())                                            # 82

    # ── B. Galvanizing Conversion ─────────────────────────────
    rows.append(sec("B. GALVANIZING — Conversion Cost"))            # 83
    rows.append(col_subhdr())                                       # 84

    rows.append(gi_xref("  Depreciation",          GI["dep"]))     # 85

    rows.append(sub(" Labor"))                                      # 86
    rows.append(gi_xref("  Direct Labor",           GI["dl"]))     # 87
    rows.append(gi_xref("  Indirect Labor",         GI["il"]))     # 88

    rows.append(sub(" Manufacturing Supplies (Gas & Chemicals)"))   # 89
    rows.append(gi_inp("  LNG",                    cur()))          # 90
    rows.append(gi_inp("  Nitrogen (N2)",          cur()))          # 91
    rows.append(gi_inp("  Hydrogen (H2)",          cur()))          # 92
    rows.append(gi_inp("  Passivation",            cur()))          # 93
    rows.append(gi_inp("  NaOH 50%",               cur()))          # 94
    rows.append(gi_inp("  Defoamer",               cur()))          # 95
    rows.append(gi_xref("  Mfg Supplies Total (GL 13872)",
                        GI["mfg"]))                                 # 96

    rows.append(sub(" Fuel & Power"))                               # 97
    rows.append(gi_xref("  Electricity",            GI["elec"]))   # 98

    rows.append(sub(" Spare Parts & Supplies"))                     # 99
    rows.append(gi_xref("  Spare Parts",            GI["sp"]))     # 100
    rows.append(gi_xref("  Repair & Maintenance",   GI["rm"]))     # 101
    rows.append(blank())                                            # 102

    rows.append(gi_xref("Galvanizing Conversion Cost", GI["gi_conv"])) # 103
    rows.append(blank())                                            # 104

    # ── C. GI Summary ─────────────────────────────────────────
    rows.append(sec("C. GI LINE — COST SUMMARY"))                   # 105
    rows.append(col_subhdr())                                       # 106

    rows.append(gi_xref(" CRC Cost (from PK & CR)", GI["crc_cost"])) # 107
    rows.append(gi_xref(" Zinc + ZAM Alloy",        GI["zinc_zam"])) # 108
    rows.append(gi_xref(" Galvanizing Conversion",  GI["gi_conv_sum"])) # 109
    rows.append(gi_xref(" Less: Scrap Recovery",    GI["scrap_sum"])) # 110
    rows.append(gi_xref("TOTAL GI COST",            GI["total"]))  # 111
    rows.append(blank())                                            # 112

    return rows


# ── Main ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Populate GI Components tab (v2 — Excel format with cross-references)"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print rows only — do not write to Google Sheet")
    args = parser.parse_args()

    rows = build_rows()

    if args.dry_run:
        print(f"DRY RUN — {len(rows)} rows, {8} columns")
        print()
        for i, r in enumerate(rows):
            label = r[1] if len(r) > 1 else ""
            c_val = r[2] if len(r) > 2 else ""
            print(f"  [{i+1:03d}] {str(label)[:45]:<45}  {str(c_val)[:35]}")
        return

    from utils.auth import get_gspread_client
    import gspread

    print("=" * 60)
    print("GI Components Tab v2 — Populate")
    print("=" * 60)
    print(f"Sheet : {SHEET_ID}")
    print(f"Tab   : '{TAB_NAME}' (create if not exists)")
    print(f"Rows  : {len(rows)}")
    print()

    gc = get_gspread_client()
    sh = gc.open_by_key(SHEET_ID)

    try:
        ws = sh.worksheet(TAB_NAME)
        print(f"  Found existing tab '{TAB_NAME}' — clearing...")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=TAB_NAME, rows=120, cols=9)
        print(f"  Created new tab '{TAB_NAME}'")

    ws.clear()
    ws.update(values=rows, range_name="A1", value_input_option="USER_ENTERED")

    gid = ws._properties["sheetId"]
    print("DONE")
    print(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid={gid}")


if __name__ == "__main__":
    main()
