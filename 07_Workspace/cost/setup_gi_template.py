"""
setup_gi_template.py
Design GI Cost Report Template with formulas
Target Sheet: 1Rg7NfAm5XMiWBHmG3X4aQx5eLfBhZOzb

Architecture:
  [SAP data] → values → [Annual Total] ← formulas ← [Summary]
  [PK & CR] and [GI Line]: values for amounts, formula strings for THB/MT cells
  [Monitoring]: formula strings for Yield% cells, manual input for physical quantities

Run monthly: script range-updates only the new month's columns in Annual Total.
Summary auto-updates via formulas.

Prepared by: Claude Code
"""

import pandas as pd
import numpy as np
import sys, os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.auth import get_gspread_client
import gspread

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
DATA_DIR = str(Path(__file__).resolve().parent.parent.parent / '01_Bronze_Raw' / 'PRD_GI')
TEMPLATE_ID  = "1Rg7NfAm5XMiWBHmG3X4aQx5eLfBhZOzb"
MONTHS       = [1, 2, 3]          # months to populate on this run
MNAMES       = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
NOW          = datetime.now().strftime("%d/%m/%Y %H:%M")
PREPARED     = f"Prepared by: Claude Code | {NOW}"
I_IDX        = [43,46,49,52,55,58,61,64,67,70,73]

# ─────────────────────────────────────────────────────────────
# COLUMN HELPERS
# ─────────────────────────────────────────────────────────────
def col_letter(n):
    """1-based column number → letter(s).  1=A, 26=Z, 27=AA …"""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s

# Annual Total layout:
#   Col A = blank  |  Col B = Item label
#   Jan Amount = C(3), Jan MT = D(4)
#   Feb Amount = E(5), Feb MT = F(6)  … pattern: amt=3+(m-1)*2, mt=4+(m-1)*2
#   YE Amount  = AA(27), YE MT = AB(28)
def at_amt(m):  return col_letter(3 + (m - 1) * 2)   # e.g. Jan→C, Feb→E
def at_mt(m):   return col_letter(4 + (m - 1) * 2)   # e.g. Jan→D, Feb→F
AT_YE_AMT = col_letter(27)  # AA
AT_YE_MT  = col_letter(28)  # AB

# Summary column layout:
#   Col A = blank | Col B = Metric | C=Jan D=Feb … N=Dec | O=YTD
def sum_col(m):  return col_letter(m + 2)   # Jan(1)→C, Dec(12)→N
SUM_YTD = col_letter(15)  # O

# ─────────────────────────────────────────────────────────────
# SAP DATA HELPERS  (standalone, no shared module dependency)
# ─────────────────────────────────────────────────────────────
def to_f(v):
    if pd.isna(v): return 0.0
    s = str(v).replace(",", "").strip()
    if s.endswith("-"): return -float(s[:-1])
    try: return float(s)
    except: return 0.0

def r2(v): return round(float(v), 2)
def per_mt(cost, qty_kg): return r2(cost / (qty_kg / 1000)) if qty_kg else 0.0

_prd_cache = {}
def load_prd(plant, month):
    key = (plant, month)
    if key in _prd_cache:
        return _prd_cache[key]
    path = os.path.join(DATA_DIR, f"PRD_{plant}_{month:02d}.2026.XLSX")
    df  = pd.read_excel(path, header=0)
    raw = pd.read_excel(path, header=None)
    df.columns = [str(c) for c in df.columns]
    for c in ["Actual GI Amount","Actual ByProduct Scrap Amount",
              "Actual ByProduct Grade B Amount","Actual ByProduct Grade C Amount",
              "Actual GR Amount","Actual D101 Amount","Actual D102 Amount"]:
        df[c] = df[c].apply(to_f)
    df["GR_QTY"] = pd.to_numeric(df["Actual GR QTY"], errors="coerce").fillna(0)
    df["GI_QTY"] = pd.to_numeric(df["Actual GI QTY"], errors="coerce").fillna(0)
    for idx in I_IDX:
        df[f"_I{idx}"] = raw.iloc[1:, idx].apply(to_f).values
    df["_I_total"] = sum(df[f"_I{i}"] for i in I_IDX)
    df["_scrap"]   = (df["Actual ByProduct Scrap Amount"]
                    + df["Actual ByProduct Grade B Amount"]
                    + df["Actual ByProduct Grade C Amount"])
    ot = df["Order Type Name"].fillna("")
    df["_cat"] = np.where(ot.str.contains("Pickling|Cold Roll", case=False), "PK_CR",
                np.where(ot.str.contains("Galvaniz",            case=False), "GI", "Other"))
    _prd_cache[key] = df
    return df

def prd_agg(month, cat):
    df  = load_prd("1300", month)
    sub = df[df["_cat"] == cat]
    if len(sub) == 0:
        return dict(mat=0, d101=0, d102=0, i_tot=0, scrap=0, gr_qty=0, gi_qty=0)
    return dict(
        mat    = r2(sub["Actual GI Amount"].sum()),
        d101   = r2(sub["Actual D101 Amount"].sum()),
        d102   = r2(sub["Actual D102 Amount"].sum()),
        i_tot  = r2(sub["_I_total"].sum()),
        scrap  = r2(sub["_scrap"].sum()),
        gr_qty = r2(sub["GR_QTY"].sum()),    # kg
        gi_qty = r2(sub["GI_QTY"].sum()),    # kg (input)
    )

_gl_cache = None
def get_gl():
    global _gl_cache
    if _gl_cache is not None:
        return _gl_cache
    f  = os.path.join(DATA_DIR, "AMC_GL_03.2026.XLSX")
    gl = pd.read_excel(f, header=0)
    gl.columns = [str(c) for c in gl.columns]
    gl["CC_str"] = gl["Cost Center"].astype(str).str.strip()
    gl["GL_str"] = gl["G/L Account"].astype(str)
    gl["month"]  = pd.to_datetime(gl["Posting Date"], errors="coerce").dt.month
    gl["amt"]    = pd.to_numeric(gl["Company Code Currency Value"], errors="coerce").fillna(0)
    _gl_cache = gl
    return gl

def gl_by_account(cc_prefix_list, month):
    """Return dict GL_account → sum for given CC prefixes + month (conversion costs only)."""
    gl = get_gl()
    parts = []
    for pfx in cc_prefix_list:
        mask = (
            gl["CC_str"].str.startswith(pfx) &
            (gl["month"] == month) &
            ~gl["GL_str"].str.startswith("9") &
            ~gl["GL_str"].str.startswith("52") &
            ~gl["GL_str"].str.startswith("54") &
            ~gl["GL_str"].str.startswith("7") &
            (gl["GL_str"] != "5391020")
        )
        parts.append(gl[mask])
    sub = pd.concat(parts)
    result = sub.groupby("G/L Account")["amt"].sum()
    return result.to_dict()

def gl_sum_by_prefix(cc_prefix_list, month):
    d = gl_by_account(cc_prefix_list, month)
    return r2(sum(d.values()))

def gl_coating_material(month):
    """
    Extract coating material costs from GL 5411010 (Consumption - Raw Material).
    Zinc Ingot = materials starting '10INGZM'
    ZAM Alloy  = materials starting '10GMC'
    These postings have no CC — filtered by material number instead.
    """
    gl = get_gl()
    mask = (
        (gl["month"] == month) &
        (gl["GL_str"] == "5411010") &
        gl["Material"].astype(str).str.match(r"^10INGZM|^10GMC")
    )
    sub = gl[mask]
    zinc = r2(sub[sub["Material"].astype(str).str.startswith("10INGZM")]["amt"].sum())
    zam  = r2(sub[sub["Material"].astype(str).str.startswith("10GMC")]["amt"].sum())
    return zinc, zam

def gl_cat_amounts(cc_prefix_list, month):
    """Breakdown by cost category (Depreciation, Labor, etc.)."""
    d = gl_by_account(cc_prefix_list, month)
    cats = dict(depreciation=0, labor_direct=0, labor_indirect=0,
                electricity=0, rm=0, supplies=0, mfg_supplies=0, other=0)
    for gl_acc, amt in d.items():
        a = str(gl_acc)
        if   a.startswith("5811"): cats["depreciation"]   += amt
        elif a.startswith("5511"): cats["labor_direct"]   += amt
        elif a.startswith("5512") or a.startswith("5513"):
                                   cats["labor_indirect"]  += amt
        elif a.startswith("5611"): cats["electricity"]    += amt
        elif a.startswith("5711"): cats["rm"]             += amt
        elif a.startswith("5911"): cats["supplies"]       += amt
        elif a.startswith("5912"): cats["mfg_supplies"]   += amt
        else:                      cats["other"]           += amt
    return {k: r2(v) for k, v in cats.items()}

# ─────────────────────────────────────────────────────────────
# SHEET HELPER
# ─────────────────────────────────────────────────────────────
def write_tab(ws, rows):
    """Clear entire tab and write rows from A1. Uses USER_ENTERED for formulas."""
    ws.clear()
    ws.update(values=[[PREPARED]] + rows, range_name="A1",
              value_input_option="USER_ENTERED")

def range_update(ws, range_name, values):
    """Write to a specific range without clearing the rest (for Annual Total month updates)."""
    ws.update(values=values, range_name=range_name,
              value_input_option="USER_ENTERED")

# ─────────────────────────────────────────────────────────────
# YTD FORMULA BUILDERS  (for Annual Total)
# ─────────────────────────────────────────────────────────────
def ytd_sum_amt(row):
    """Sum all 12 month Amount columns."""
    cols = ",".join(f"{at_amt(m)}{row}" for m in range(1, 13))
    return f"=SUM({cols})"

def ytd_sum_mt(row):
    """Sum all 12 month MT (volume) columns — for production volume rows."""
    cols = ",".join(f"{at_mt(m)}{row}" for m in range(1, 13))
    return f"=IFERROR(SUM({cols}),\"\")"

def ytd_rate(amt_row, vol_row):
    """YTD THB/MT = YE Amount / YE Volume MT."""
    return f"=IFERROR({AT_YE_AMT}{amt_row}/{AT_YE_MT}{vol_row},\"\")"

def ytd_yield(output_row, input_row):
    """YTD Yield Loss % = 1 - YE Output MT / YE Input MT."""
    return f"=IFERROR(1-{AT_YE_MT}{output_row}/{AT_YE_MT}{input_row},\"\")"

# ─────────────────────────────────────────────────────────────
# BUILD: ANNUAL TOTAL  (master data store)
# ─────────────────────────────────────────────────────────────
#
# Row layout (fixed, used by Summary formulas — do NOT change row numbers):
#   Row 2  = header
#   Row 3  = sub-header (Amount THB | MT)
#   Row 4  = section: PICKLING & COLD ROLLING
#   Row 5  = HRC Used                   ← AT_ROW["hrc"]
#   Row 6  = CRC Output (GR)            ← AT_ROW["crc_out"]
#   Row 7  = Scrap Actual (PK+CR)       ← AT_ROW["scrap_pk"]
#   Row 8  = % Yield Loss (PK+CR)       ← AT_ROW["yield_pk"]
#   Row 9  = Pickling Conversion        ← AT_ROW["pk_conv"]
#   Row 10 = Cold Rolling Conversion    ← AT_ROW["cr_conv"]
#   Row 11 = Total CRC Cost             ← AT_ROW["total_crc"]
#   Row 12 = section: GALVANIZING
#   Row 13 = CRC Used (GI input)        ← AT_ROW["crc_gi"]
#   Row 14 = Zinc Ingot Used            ← AT_ROW["zinc"]
#   Row 15 = GI Galvanized Output       ← AT_ROW["gi_out"]
#   Row 16 = Scrap (Dross + Slag)       ← AT_ROW["scrap_gi"]
#   Row 17 = GI Conversion Cost         ← AT_ROW["gi_conv"]
#   Row 18 = Total GI Cost              ← AT_ROW["total_gi"]
#
AT_ROW = dict(hrc=5, crc_out=6, scrap_pk=7, yield_pk=8, pk_conv=9, cr_conv=10,
              total_crc=11, crc_gi=13, zinc=14, gi_out=15, scrap_gi=16,
              gi_conv=17, total_gi=18)

def build_annual_total(ws):
    print("  Building Annual Total tab (values for Jan-Mar + YTD formulas)...")

    # ── Header rows ──────────────────────────────────────────────
    month_headers = []
    for m in range(1, 13):
        month_headers += [MNAMES[m], ""]
    month_headers += ["YE'2026", ""]

    sub_headers = []
    for _ in range(13):      # 12 months + YE
        sub_headers += ["Amount (THB)", "MT"]

    rows = [
        ["ASIA METAL PLC — Annual Production Cost Summary 2026"],
        ["", "Items"] + month_headers,
        ["", ""] + sub_headers,
        ["", "PICKLING & COLD ROLLING"],
    ]
    # After header = rows 1..4 (index 0..3 in this list, but +1 for PREPARED stamp = rows 2..5)
    # Actual sheet row numbers = 1 (PREPARED) + 1..N = rows 2..N+1
    # But write_tab prepends PREPARED as row 1, so our row 4 label becomes sheet row 5 etc.
    # Adjust: PREPARED is row 1, our rows[] start at sheet row 2.
    # AT_ROW values above already account for this (hrc=5 means sheet row 5 = rows[3] = 4th element)

    # ── Data rows ────────────────────────────────────────────────
    # Each data row = ["", label, Jan_amt, Jan_mt, Feb_amt, Feb_mt, ..., YE_amt, YE_mt]
    # We'll build a dict: row_number → [amt_or_formula, mt_or_formula] per month + YE
    # Then assemble in order.

    data = {}   # AT_ROW key → {m: (amt, mt), "ye_amt": formula, "ye_mt": formula}

    for m in MONTHS:
        pk  = prd_agg(m, "PK_CR")
        gi  = prd_agg(m, "GI")

        # ── GL-based conversion costs with overhead allocation ──────────────
        # Direct costs by process line
        pk_direct = gl_sum_by_prefix(["138711"], m)   # Pickling Line 01 + sub-CCs
        cr_direct = gl_sum_by_prefix(["138712"], m)   # Cold Rolling Mill + sub-CCs
        gi_direct = gl_sum_by_prefix(["13872"],  m)   # Galvanizing Line + sub-CCs

        # Overhead parent CCs (1387000 = GI Production, 1387100 = PK+CR overhead)
        # Allocate to PK+CR vs GI by output volume (same logic as populate script)
        oh_gl    = gl_sum_by_prefix(["138700", "138710"], m)
        tot_qty  = pk["gr_qty"] + gi["gr_qty"]
        pk_oh    = r2(oh_gl * pk["gr_qty"] / tot_qty) if tot_qty else 0
        gi_oh    = r2(oh_gl * gi["gr_qty"] / tot_qty) if tot_qty else 0

        # Split PK+CR overhead proportionally between Pickling and Cold Rolling
        pk_cr_direct = r2(pk_direct + cr_direct)
        pk_ratio     = pk_direct / pk_cr_direct if pk_cr_direct else 0.5
        pk_conv_gl   = r2((pk_cr_direct + pk_oh) * pk_ratio)
        cr_conv_gl   = r2((pk_cr_direct + pk_oh) - pk_conv_gl)
        gi_gl_conv   = r2(gi_direct + gi_oh)

        # PK+CR values
        hrc_amt   = pk["mat"]
        hrc_mt    = r2(pk["gi_qty"] / 1000)   # HRC input MT
        crc_mt    = r2(pk["gr_qty"] / 1000)   # CRC output MT
        scrap_amt = pk["scrap"]
        total_crc_amt = r2(hrc_amt + pk_conv_gl + cr_conv_gl - scrap_amt)

        if "hrc" not in data: data["hrc"] = {}
        if "crc_out" not in data: data["crc_out"] = {}
        if "scrap_pk" not in data: data["scrap_pk"] = {}
        if "pk_conv" not in data: data["pk_conv"] = {}
        if "cr_conv" not in data: data["cr_conv"] = {}
        if "total_crc" not in data: data["total_crc"] = {}

        data["hrc"][m]      = (hrc_amt, hrc_mt)
        data["crc_out"][m]  = (total_crc_amt, crc_mt)
        data["scrap_pk"][m] = (scrap_amt, r2(scrap_amt / crc_mt) if crc_mt else 0)
        data["pk_conv"][m]  = (pk_conv_gl, r2(pk_conv_gl / crc_mt) if crc_mt else 0)
        data["cr_conv"][m]  = (cr_conv_gl, r2(cr_conv_gl / crc_mt) if crc_mt else 0)
        data["total_crc"][m]= (total_crc_amt, r2(total_crc_amt / crc_mt) if crc_mt else 0)

        # GI Line values
        crc_gi_amt  = gi["mat"]                  # CRC used (at MAP)
        crc_gi_mt   = r2(gi["gi_qty"] / 1000)
        gi_out_mt   = r2(gi["gr_qty"] / 1000)
        scrap_gi    = gi["scrap"]
        # Zinc = GI material - CRC_used (approx; or use PRD column directly)
        # From the template data: Zinc = 3,698,872 for Jan; CRC used = 109,968,154
        # gi["mat"] likely = CRC MAP + Zinc combined in PRD GI Amount
        # → need to split; for now store as combined and note in header
        # Better approach: GI "mat" in PRD = CRC MAP value; Zinc comes from a separate column
        # Check PRD col 22 for GI orders = GIC material (CRC+Zinc combined)
        # The template shows these separately - we'll approximate Zinc from the difference
        # For now: store GI mat = total material (CRC+Zinc), Zinc = from GL 591* accounts
        gi_mat_total = gi["mat"]
        # gi_gl_conv already computed above (gi_direct + overhead share)
        total_gi_amt = r2(gi_mat_total + gi_gl_conv - scrap_gi)

        if "crc_gi" not in data: data["crc_gi"] = {}
        if "zinc" not in data: data["zinc"] = {}
        if "gi_out" not in data: data["gi_out"] = {}
        if "scrap_gi" not in data: data["scrap_gi"] = {}
        if "gi_conv" not in data: data["gi_conv"] = {}
        if "total_gi" not in data: data["total_gi"] = {}

        # Separate Zinc + ZAM alloy from CRC-used via GL 5411010 by material number
        # 10INGZM* = Zinc Ingot; 10GMC* = ZAM alloy (no CC — filtered by material prefix)
        zinc_gl, zam_gl  = gl_coating_material(m)
        coating_total    = r2(zinc_gl + zam_gl)
        crc_used_est     = r2(gi_mat_total - coating_total)
        zinc_est         = coating_total   # combined: Zinc Ingot + ZAM Alloy

        data["crc_gi"][m]   = (crc_used_est, crc_gi_mt)
        data["zinc"][m]     = (zinc_est, r2(zinc_est / gi_out_mt) if gi_out_mt else 0)
        data["gi_out"][m]   = (total_gi_amt, gi_out_mt)
        data["scrap_gi"][m] = (scrap_gi, r2(scrap_gi / gi_out_mt) if gi_out_mt else 0)
        data["gi_conv"][m]  = (gi_gl_conv, r2(gi_gl_conv / gi_out_mt) if gi_out_mt else 0)
        data["total_gi"][m] = (total_gi_amt, r2(total_gi_amt / gi_out_mt) if gi_out_mt else 0)

    # ── Assemble row data ─────────────────────────────────────
    def build_data_row(key, label, row_num, is_yield=False, is_vol=False):
        """Build a full row with values for populated months, blanks for rest, YTD formula."""
        row = ["", label]
        for m in range(1, 13):
            if m in MONTHS and key in data and m in data[key]:
                amt, mt = data[key][m]
                row += [amt, mt]
            else:
                row += ["", ""]
        # YTD
        if is_yield:
            row += ["", ytd_yield(AT_ROW["crc_out"], AT_ROW["hrc"])]
        elif is_vol:
            row += [ytd_sum_amt(row_num), ytd_sum_mt(row_num)]
        else:
            row += [ytd_sum_amt(row_num), ytd_rate(row_num, AT_ROW["gi_out"])]
        return row

    # ── % Yield Loss row (formula-based, no SAP values needed) ──
    def yield_row_pk(row_num):
        row = ["", " % Yield Loss"]
        for m in range(1, 13):
            if m in MONTHS:
                row += [f"=IFERROR(1-{at_mt(m)}{AT_ROW['crc_out']}/{at_mt(m)}{AT_ROW['hrc']},\"\")", ""]
            else:
                row += ["", ""]
        row += ["", ytd_yield(AT_ROW["crc_out"], AT_ROW["hrc"])]
        return row

    def yield_row_gi(row_num):
        row = ["", " % Yield Loss (GI)"]
        for m in range(1, 13):
            if m in MONTHS:
                row += [f"=IFERROR(1-{at_mt(m)}{AT_ROW['gi_out']}/{at_mt(m)}{AT_ROW['crc_gi']},\"\")", ""]
            else:
                row += ["", ""]
        row += ["", ytd_yield(AT_ROW["gi_out"], AT_ROW["crc_gi"])]
        return row

    # Assemble in sheet order (matching AT_ROW numbers)
    # rows[] offset: rows[0] = sheet row 2 (after PREPARED), so rows[AT_ROW[key]-2] = that key row
    # Fill rows list to correct positions
    total_rows = 20   # rows 2..20 (indices 0..18)
    grid = [[""] * (2 + 13 * 2) for _ in range(total_rows)]

    grid[0] = ["", "ASIA METAL PLC — Annual Production Cost Summary 2026"]
    grid[1] = ["", "Items"] + [v for m in range(1, 13) for v in [MNAMES[m], ""]] + ["YE'2026", ""]
    grid[2] = ["", ""] + ["Amount (THB)", "MT"] * 13
    grid[3] = ["", " PICKLING & COLD ROLLING"]

    grid[AT_ROW["hrc"]     - 2] = build_data_row("hrc",       " HRC Used",                    AT_ROW["hrc"],       is_vol=True)
    grid[AT_ROW["crc_out"] - 2] = build_data_row("crc_out",   " CRC Output (GR)",             AT_ROW["crc_out"],   is_vol=True)
    grid[AT_ROW["scrap_pk"]- 2] = build_data_row("scrap_pk",  " Scrap Actual",                AT_ROW["scrap_pk"])
    grid[AT_ROW["yield_pk"]- 2] = yield_row_pk(AT_ROW["yield_pk"])
    grid[AT_ROW["pk_conv"] - 2] = build_data_row("pk_conv",   " Pickling Conversion",         AT_ROW["pk_conv"])
    grid[AT_ROW["cr_conv"] - 2] = build_data_row("cr_conv",   " Cold Rolling Conversion",     AT_ROW["cr_conv"])
    grid[AT_ROW["total_crc"]- 2]= build_data_row("total_crc", " Total CRC Cost",              AT_ROW["total_crc"])

    grid[AT_ROW["crc_gi"]  - 2] = build_data_row("crc_gi",    " CRC Used (GI input)",         AT_ROW["crc_gi"],    is_vol=True)
    grid[AT_ROW["zinc"]    - 2] = build_data_row("zinc",      " Zinc + ZAM Alloy (Coating)",  AT_ROW["zinc"])
    grid[AT_ROW["gi_out"]  - 2] = build_data_row("gi_out",    " GI Galvanized Output",        AT_ROW["gi_out"],    is_vol=True)
    grid[AT_ROW["scrap_gi"]- 2] = build_data_row("scrap_gi",  " Scrap (Dross + Slag)",        AT_ROW["scrap_gi"])
    grid[AT_ROW["gi_conv"] - 2] = build_data_row("gi_conv",   " GI Conversion Cost",          AT_ROW["gi_conv"])
    grid[AT_ROW["total_gi"]- 2] = build_data_row("total_gi",  " Total GI Cost",               AT_ROW["total_gi"])

    # Section header for GALVANIZING (row 12 = index 10)
    grid[10] = ["", " GALVANIZING"]

    write_tab(ws, grid)
    print(f"    -> Annual Total: {len(MONTHS)} month(s) populated, YTD formulas set")
    print(f"    -> Key rows: CRC Output={AT_ROW['crc_out']}, GI Output={AT_ROW['gi_out']}")


# ─────────────────────────────────────────────────────────────
# BUILD: SUMMARY  (all formula cells, references Annual Total)
# ─────────────────────────────────────────────────────────────
def sum_formula(at_row, at_col_fn, m, divisor_row=None, divisor_col_fn=None, add_rows=None):
    """
    Build a Summary cell formula for month m (or YTD).
    - Simple reference: =AT!<col><row>
    - With divisor: =IFERROR(AT!<amt_col><row> / AT!<mt_col><divisor_row>, "")
    - add_rows: list of (at_row2) to add in numerator before dividing
    """
    def at_ref(row, col): return f"'Annual Total'!{col}{row}"

    numerator = at_ref(at_row, at_col_fn(m))
    if add_rows:
        for r2 in add_rows:
            numerator += f"+{at_ref(r2, at_col_fn(m))}"
        numerator = f"({numerator})"

    if divisor_row is None:
        return f"={numerator}"
    else:
        denom = at_ref(divisor_row, divisor_col_fn(m))
        return f"=IFERROR({numerator}/{denom},\"\")"

def build_summary(ws):
    print("  Building Summary tab (formula-based)...")

    # Header row: col B = "Metric / Item", cols C..N = Jan..Dec, col O = YTD
    header = ["", "Metric / Item"] + [MNAMES[m] for m in range(1, 13)] + ["YTD Total / Avg"]

    def formula_row(label, at_row, mode="rate", at_row2=None, div_row=None):
        """
        mode:
          "vol"   → reference AT MT column (production volume)
          "rate"  → formula: AT amt / GI output MT  (default divisor = gi_out)
          "amt_ref" → reference AT amount column directly
          custom div_row overrides GI output as denominator
        """
        row = ["", label]
        dv_row = div_row if div_row else AT_ROW["gi_out"]
        add = [at_row2] if at_row2 else None

        for m in range(1, 13):
            if mode == "vol":
                row.append(f"='Annual Total'!{at_mt(m)}{at_row}")
            elif mode == "amt_ref":
                row.append(f"='Annual Total'!{at_amt(m)}{at_row}")
            else:  # "rate"
                num_col = at_amt(m)
                num = f"'Annual Total'!{num_col}{at_row}"
                if add:
                    num = "(" + num + "".join(f"+'Annual Total'!{num_col}{r}" for r in add) + ")"
                denom = f"'Annual Total'!{at_mt(m)}{dv_row}"
                row.append(f"=IFERROR({num}/{denom},\"\")")

        # YTD column
        if mode == "vol":
            row.append(f"='Annual Total'!{AT_YE_MT}{at_row}")
        elif mode == "amt_ref":
            row.append(f"='Annual Total'!{AT_YE_AMT}{at_row}")
        else:
            num_col = AT_YE_AMT
            num = f"'Annual Total'!{num_col}{at_row}"
            if add:
                num = "(" + num + "".join(f"+'Annual Total'!{num_col}{r}" for r in add) + ")"
            denom = f"'Annual Total'!{AT_YE_MT}{dv_row}"
            row.append(f"=IFERROR({num}/{denom},\"\")")

        return row

    # Total Conversion = (PK conv + CR conv + GI conv) / GI Output MT
    def total_conv_row():
        row = ["", " Total Conversion Cost"]
        for m in range(1, 13):
            ac, gc, ic = at_amt(m), at_mt(m), at_mt(m)
            num = (f"('Annual Total'!{at_amt(m)}{AT_ROW['pk_conv']}"
                   f"+'Annual Total'!{at_amt(m)}{AT_ROW['cr_conv']}"
                   f"+'Annual Total'!{at_amt(m)}{AT_ROW['gi_conv']})")
            denom = f"'Annual Total'!{at_mt(m)}{AT_ROW['gi_out']}"
            row.append(f"=IFERROR({num}/{denom},\"\")")
        num = (f"('Annual Total'!{AT_YE_AMT}{AT_ROW['pk_conv']}"
               f"+'Annual Total'!{AT_YE_AMT}{AT_ROW['cr_conv']}"
               f"+'Annual Total'!{AT_YE_AMT}{AT_ROW['gi_conv']})")
        denom = f"'Annual Total'!{AT_YE_MT}{AT_ROW['gi_out']}"
        row.append(f"=IFERROR({num}/{denom},\"\")")
        return row

    def total_mat_row():
        row = ["", " Total Material Cost"]
        for m in range(1, 13):
            num = (f"('Annual Total'!{at_amt(m)}{AT_ROW['hrc']}"
                   f"+'Annual Total'!{at_amt(m)}{AT_ROW['zinc']})")
            denom = f"'Annual Total'!{at_mt(m)}{AT_ROW['gi_out']}"
            row.append(f"=IFERROR({num}/{denom},\"\")")
        num = (f"('Annual Total'!{AT_YE_AMT}{AT_ROW['hrc']}"
               f"+'Annual Total'!{AT_YE_AMT}{AT_ROW['zinc']})")
        denom = f"'Annual Total'!{AT_YE_MT}{AT_ROW['gi_out']}"
        row.append(f"=IFERROR({num}/{denom},\"\")")
        return row

    rows = [
        header,
        ["", ""],
        ["", " PRODUCTION VOLUME (MT)"],
        formula_row(" Pickling & Cold Rolling (CRC Output)", AT_ROW["crc_out"], mode="vol"),
        formula_row(" Galvanizing (GI Output)",              AT_ROW["gi_out"],  mode="vol"),
        ["", ""],
        ["", " CONVERSION COST (THB/MT)"],
        formula_row(" Pickling & Cold Rolling", AT_ROW["pk_conv"], at_row2=AT_ROW["cr_conv"],
                    div_row=AT_ROW["crc_out"]),
        formula_row(" Galvanizing",             AT_ROW["gi_conv"]),
        total_conv_row(),
        ["", ""],
        ["", " MATERIAL COST (THB/MT)"],
        formula_row(" Hot Rolled Coil (HRC) / MT", AT_ROW["hrc"],  div_row=AT_ROW["crc_out"]),
        formula_row(" Zinc + ZAM Alloy / MT",        AT_ROW["zinc"]),
        total_mat_row(),
        ["", ""],
        ["", " FINISHED GOODS COST (THB/MT) — by Coating Grade"],
        ["", " GI/ZAM Z60",  *["" for _ in range(13)]],
        ["", " GI/ZAM Z80",  *["" for _ in range(13)]],
        ["", " GI/ZAM Z120", *["" for _ in range(13)]],
        ["", " GI/ZAM Z180", *["" for _ in range(13)]],
        ["", " GI/ZAM Z275", *["" for _ in range(13)]],
        ["", ""],
        ["", " SG&A (THB/MT)"],
        ["", " SG&A per MT", *["" for _ in range(13)]],
        ["", ""],
        ["", " GRAND TOTAL — FG Cost incl. SG&A (Z120 reference) (THB/MT)"],
        formula_row(" Grand Total (Z120 base)", AT_ROW["total_gi"]),
        ["", ""],
        ["", "Note: Blue cells = auto-calculated from Annual Total. "
             "Grade cost rows require Monitoring tab volume by grade. "
             "Update Annual Total each month via script."],
    ]

    write_tab(ws, rows)
    print(f"    -> Summary: {len(rows)} rows, all formula-based")


# ─────────────────────────────────────────────────────────────
# BUILD: PK & CR  (multi-month: Jan/Feb/Mar side by side)
# ─────────────────────────────────────────────────────────────
def build_pk_cr(ws, months=None):
    if months is None: months = MONTHS
    n = len(months)
    print(f"  Building PK & CR tab (months={[MNAMES[m] for m in months]})...")

    # Column layout: A=spacer B=label | per month: amt_col THB/MT_col
    # month index i (0-based): C,E,G,... for amounts; D,F,H,... for THB/MT
    def amt_col(i): return col_letter(3 + i * 2)
    def thb_col(i): return col_letter(4 + i * 2)
    GR_ROW = 9  # sheet row with input/output qty; GR qty = thb_col(i) at GR_ROW

    def fthb(row, mi):
        """THB/MT = amount / (GR_qty_kg / 1000)."""
        return f"=IFERROR({amt_col(mi)}{row}/({thb_col(mi)}{GR_ROW}/1000),\"\")"

    pks    = [prd_agg(m, "PK_CR")           for m in months]
    gl_pks = [gl_cat_amounts(["138711"], m)  for m in months]
    gl_crs = [gl_cat_amounts(["138712"], m)  for m in months]

    hdr    = ["", "Items"] + [v for m in months for v in [MNAMES[m], ""]]
    subhdr = ["", ""]      + ["Amount (THB)", "THB/MT"] * n

    def cost_row(label, amts, row_num):
        return ["", label] + [v for i, a in enumerate(amts) for v in [a, fthb(row_num, i)]]
    def hdr_row(label): return ["", label]
    def blank_row():    return ["", ""]

    rows = [
        ["", "ASIA METAL PLC — Pickling & Cold Rolling Cost Sheet"],
        ["", ""],
        ["", "Production Lot:"],
        ["", "Month / Year:"] + [f"{m:02d}.2026" for m in months],
        ["", ""],
        ["", "A. MATERIAL — Input Quantities"],
        hdr,
        # Row 9: qty data — thb_col(i) = GR output qty for month i
        ["", "HRC Input Quantity (kg)"] + [
            v for pk in pks for v in [r2(pk["gi_qty"]), r2(pk["gr_qty"])]],
        blank_row(),
        ["", "Material Cost"],
        subhdr,
        # Row 13: HRC material cost
        cost_row("Hot Rolled Coil (HRC) used", [pk["mat"] for pk in pks], 13),
        # Row 14: % Yield Loss
        ["", "% Yield Loss"] + [
            v for i in range(n) for v in [
                "",
                f"=IFERROR(1-{thb_col(i)}{GR_ROW}/{amt_col(i)}{GR_ROW},\"\")"]],
        blank_row(),
    ]
    # Row 16: Section B header, Row 17: sub-header, Row 18: cost items start
    rows.append(hdr_row("B. PICKLING — Conversion Cost"))
    rows.append(subhdr)
    pk_items_start = len(rows) + 2   # +2 = PREPARED row + header offset

    dep_pks  = [r2(g.get("depreciation", 0))   for g in gl_pks]
    dl_pks   = [r2(g.get("labor_direct", 0))   for g in gl_pks]
    il_pks   = [r2(g.get("labor_indirect", 0)) for g in gl_pks]
    chem_pks = [r2(g.get("mfg_supplies", 0))   for g in gl_pks]
    elec_pks = [r2(g.get("electricity", 0))    for g in gl_pks]
    sp_pks   = [r2(g.get("supplies", 0))       for g in gl_pks]
    rm_pks   = [r2(g.get("rm", 0))             for g in gl_pks]
    oth_pks  = [r2(g.get("other", 0))          for g in gl_pks]

    # Offsets: +0 Dep, +1 Labor hdr, +2 Direct, +3 Indirect,
    #          +4 Material hdr, +5 Chem, +6 Fuel hdr, +7 Elec,
    #          +8 SP hdr, +9 SP, +10 R&M, [+11 Other]
    pk_rows = [
        cost_row(" Depreciation",          dep_pks,  pk_items_start),
        hdr_row(" Labor"),
        cost_row("  Direct Labor",         dl_pks,   pk_items_start+2),
        cost_row("  Indirect Labor",       il_pks,   pk_items_start+3),
        hdr_row(" Material"),
        cost_row("  Chemicals / Supplies", chem_pks, pk_items_start+5),
        hdr_row(" Fuel & Power"),
        cost_row("  Electricity",          elec_pks, pk_items_start+7),
        hdr_row(" Spare Parts & Supplies"),
        cost_row("  Spare Parts",          sp_pks,   pk_items_start+9),
        cost_row("  Repair & Maintenance", rm_pks,   pk_items_start+10),
    ]
    has_oth_pk = any(x > 0 for x in oth_pks)
    if has_oth_pk:
        pk_rows.append(cost_row("  Other", oth_pks, pk_items_start+11))
    rows.extend(pk_rows)

    pk_offsets = [0, 2, 3, 5, 7, 9, 10] + ([11] if has_oth_pk else [])
    pk_total_row = len(rows) + 2
    pk_total_vals = []
    for i in range(n):
        cells = ",".join(f"{amt_col(i)}{pk_items_start+off}" for off in pk_offsets)
        pk_total_vals += [f"=SUM({cells})", fthb(pk_total_row, i)]
    rows.append(["", "Pickling Conversion Cost"] + pk_total_vals)
    rows.append(blank_row())

    # Section C: Cold Rolling
    rows.append(hdr_row("C. COLD ROLLING — Conversion Cost"))
    rows.append(subhdr)
    cr_items_start = len(rows) + 2

    dep_crs  = [r2(g.get("depreciation", 0))   for g in gl_crs]
    dl_crs   = [r2(g.get("labor_direct", 0))   for g in gl_crs]
    il_crs   = [r2(g.get("labor_indirect", 0)) for g in gl_crs]
    elec_crs = [r2(g.get("electricity", 0))    for g in gl_crs]
    sp_crs   = [r2(g.get("supplies", 0))       for g in gl_crs]
    rm_crs   = [r2(g.get("rm", 0))             for g in gl_crs]
    oth_crs  = [r2(g.get("other", 0))          for g in gl_crs]

    # Offsets: +0 Dep, +1 Labor hdr, +2 Direct, +3 Indirect,
    #          +4 Fuel hdr, +5 Elec, +6 SP hdr, +7 SP, +8 R&M, [+9 Other]
    cr_rows = [
        cost_row(" Depreciation",          dep_crs,  cr_items_start),
        hdr_row(" Labor"),
        cost_row("  Direct Labor",         dl_crs,   cr_items_start+2),
        cost_row("  Indirect Labor",       il_crs,   cr_items_start+3),
        hdr_row(" Fuel & Power"),
        cost_row("  Electricity",          elec_crs, cr_items_start+5),
        hdr_row(" Spare Parts & Supplies"),
        cost_row("  Spare Parts",          sp_crs,   cr_items_start+7),
        cost_row("  Repair & Maintenance", rm_crs,   cr_items_start+8),
    ]
    has_oth_cr = any(x > 0 for x in oth_crs)
    if has_oth_cr:
        cr_rows.append(cost_row("  Other", oth_crs, cr_items_start+9))
    rows.extend(cr_rows)

    cr_offsets = [0, 2, 3, 5, 7, 8] + ([9] if has_oth_cr else [])
    cr_total_row = len(rows) + 2
    cr_total_vals = []
    for i in range(n):
        cells = ",".join(f"{amt_col(i)}{cr_items_start+off}" for off in cr_offsets)
        cr_total_vals += [f"=SUM({cells})", fthb(cr_total_row, i)]
    rows.append(["", "Cold Rolling Conversion Cost"] + cr_total_vals)
    rows.append(blank_row())

    # Section D: Summary
    rows.append(hdr_row("D. PK & CR — COST SUMMARY"))
    rows.append(subhdr)
    sum_start = len(rows) + 2
    hrc_vals  = [v for i, pk in enumerate(pks) for v in [pk["mat"],               fthb(sum_start,   i)]]
    pk_c_vals = [v for i    in range(n)        for v in [f"={amt_col(i)}{pk_total_row}", fthb(sum_start+1, i)]]
    cr_c_vals = [v for i    in range(n)        for v in [f"={amt_col(i)}{cr_total_row}", fthb(sum_start+2, i)]]
    scr_vals  = [v for i    in range(n)        for v in [0,                        fthb(sum_start+3, i)]]
    rows.append(["", " HRC Material Cost"]      + hrc_vals)
    rows.append(["", " Pickling Conversion"]    + pk_c_vals)
    rows.append(["", " Cold Rolling Conversion"]+ cr_c_vals)
    rows.append(["", " Less: Scrap Recovery"]   + scr_vals)
    total_crc_row = sum_start + 4
    total_vals = []
    for i in range(n):
        f = (f"={amt_col(i)}{sum_start}+{amt_col(i)}{sum_start+1}"
             f"+{amt_col(i)}{sum_start+2}+{amt_col(i)}{sum_start+3}")
        total_vals += [f, fthb(total_crc_row, i)]
    rows.append(["", "TOTAL CRC COST"] + total_vals)

    write_tab(ws, rows)
    print(f"    -> PK & CR: {len(rows)} rows, {n} month(s), THB/MT cells are formulas")


# ─────────────────────────────────────────────────────────────
# BUILD: GI LINE  (multi-month: Jan/Feb/Mar side by side)
# ─────────────────────────────────────────────────────────────
def build_gi_line(ws, months=None):
    if months is None: months = MONTHS
    n = len(months)
    print(f"  Building GI Line tab (months={[MNAMES[m] for m in months]})...")

    def amt_col(i): return col_letter(3 + i * 2)
    def thb_col(i): return col_letter(4 + i * 2)
    GR_ROW = 9   # GI output GR qty = thb_col(i) at this row

    def fthb(row, mi):
        return f"=IFERROR({amt_col(mi)}{row}/({thb_col(mi)}{GR_ROW}/1000),\"\")"

    gis      = [prd_agg(m, "GI")              for m in months]
    gl_gis   = [gl_cat_amounts(["13872"], m)   for m in months]
    coatings = [gl_coating_material(m)         for m in months]  # (zinc, zam) per month

    hdr    = ["", "Items"] + [v for m in months for v in [MNAMES[m], ""]]
    subhdr = ["", ""]      + ["Amount (THB)", "THB/MT"] * n

    def cost_row(label, amts, row_num):
        return ["", label] + [v for i, a in enumerate(amts) for v in [a, fthb(row_num, i)]]
    def hdr_row(label): return ["", label]
    def blank_row():    return ["", ""]

    # Per-month derived values
    zinc_ls  = [r2(c[0])               for c in coatings]
    zam_ls   = [r2(c[1])               for c in coatings]
    coat_ls  = [r2(z + za)             for z, za in coatings]
    crc_ls   = [r2(gi["mat"] - coat)   for gi, coat in zip(gis, coat_ls)]
    gi_out_ls= [gi["gr_qty"]           for gi in gis]
    crc_in_ls= [gi["gi_qty"]           for gi in gis]
    scrap_ls = [gi["scrap"]            for gi in gis]

    rows = [
        ["", "ASIA METAL PLC — Galvanizing Line Cost Sheet"],
        ["", ""],
        ["", "Production Lot:"],
        ["", "Month / Year:"] + [f"{m:02d}.2026" for m in months],
        ["", ""],
        ["", "A. MATERIAL — Input Quantities"],
        hdr,
        # Row 9: qty data — thb_col(i) = GI output GR qty
        ["", "GI Line Input Quantity (kg)"] + [
            v for ci, go in zip(crc_in_ls, gi_out_ls) for v in [r2(ci), r2(go)]],
        blank_row(),
        ["", "Material Cost"],
        subhdr,
        # Row 13: output MT reference row
        ["", "GI Galvanized Coil GR (output MT)"] + [
            v for i, go in enumerate(gi_out_ls) for v in [r2(go / 1000), ""]],
        # Row 14: CRC used
        cost_row("CRC Used (at MAP)",    crc_ls,  14),
        # Row 15: Zinc
        cost_row("Zinc Ingot Used",      zinc_ls, 15),
        # Row 16: ZAM
        cost_row("ZAM Alloy Used",       zam_ls,  16),
        blank_row(),
        # Row 18: Scrap Recovery header
        hdr_row("Scrap Recovery"),
        # Row 19: Zinc Dross
        cost_row("  Zinc Dross",         scrap_ls, 19),
        # Row 20: Zinc Slag (zero)
        ["", "  Zinc Slag"] + [v for i in range(n) for v in [0, ""]],
        # Row 21: Total Scrap Recovery
        ["", "Total Scrap Recovery"] + [
            v for i in range(n) for v in [
                f"={amt_col(i)}19+{amt_col(i)}20", fthb(21, i)]],
        # Row 22: % Yield Loss
        ["", "% Yield Loss"] + [
            v for i in range(n) for v in [
                "",
                f"=IFERROR(1-{thb_col(i)}{GR_ROW}/{amt_col(i)}{GR_ROW},\"\")"]],
        blank_row(),
    ]

    # Section B: Galvanizing Conversion — row 24 header, 25 subhdr, items from 26
    rows.append(hdr_row("B. GALVANIZING — Conversion Cost"))
    rows.append(subhdr)
    gi_items_start = len(rows) + 2

    deps  = [r2(g.get("depreciation", 0))   for g in gl_gis]
    dls   = [r2(g.get("labor_direct", 0))   for g in gl_gis]
    ils   = [r2(g.get("labor_indirect", 0)) for g in gl_gis]
    mfgs  = [r2(g.get("mfg_supplies", 0))   for g in gl_gis]
    elecs = [r2(g.get("electricity", 0))    for g in gl_gis]
    sps   = [r2(g.get("supplies", 0))       for g in gl_gis]
    rms   = [r2(g.get("rm", 0))             for g in gl_gis]
    oths  = [r2(g.get("other", 0))          for g in gl_gis]

    # Offsets: +0 Dep, +1 Labor hdr, +2 Direct, +3 Indirect,
    #          +4 Mfg Supplies, +5 Fuel hdr, +6 Elec,
    #          +7 SP hdr, +8 SP, +9 R&M, [+10 Other]
    gi_cost_rows = [
        cost_row(" Depreciation",          deps,  gi_items_start),
        hdr_row(" Labor"),
        cost_row("  Direct Labor",         dls,   gi_items_start+2),
        cost_row("  Indirect Labor",       ils,   gi_items_start+3),
        cost_row(" Mfg Supplies (Gas/Chem.)", mfgs, gi_items_start+4),
        hdr_row(" Fuel & Power"),
        cost_row("  Electricity",          elecs, gi_items_start+6),
        hdr_row(" Spare Parts & Supplies"),
        cost_row("  Spare Parts",          sps,   gi_items_start+8),
        cost_row("  Repair & Maintenance", rms,   gi_items_start+9),
    ]
    has_oth = any(x > 0 for x in oths)
    if has_oth:
        gi_cost_rows.append(cost_row("  Other", oths, gi_items_start+10))
    rows.extend(gi_cost_rows)

    gi_offsets = [0, 2, 3, 4, 6, 8, 9] + ([10] if has_oth else [])
    gi_conv_total_row = len(rows) + 2
    gi_conv_vals = []
    for i in range(n):
        cells = ",".join(f"{amt_col(i)}{gi_items_start+off}" for off in gi_offsets)
        gi_conv_vals += [f"=SUM({cells})", fthb(gi_conv_total_row, i)]
    rows.append(["", "Galvanizing Conversion Cost"] + gi_conv_vals)
    rows.append(blank_row())

    # Section C: Summary
    rows.append(hdr_row("C. GI LINE — COST SUMMARY"))
    rows.append(subhdr)
    sum_s = len(rows) + 2
    rows.append(["", " CRC Cost (from PK & CR)"] + [
        v for i, c in enumerate(crc_ls)  for v in [c, fthb(sum_s, i)]])
    rows.append(["", " Zinc + ZAM Alloy"] + [
        v for i, c in enumerate(coat_ls) for v in [c, fthb(sum_s+1, i)]])
    rows.append(["", " Galvanizing Conversion"] + [
        v for i in range(n) for v in [f"={amt_col(i)}{gi_conv_total_row}", fthb(sum_s+2, i)]])
    rows.append(["", " Less: Scrap Recovery"] + [
        v for i in range(n) for v in [f"=-{amt_col(i)}21", fthb(sum_s+3, i)]])
    total_gi_row = sum_s + 4
    total_vals = []
    for i in range(n):
        f = (f"={amt_col(i)}{sum_s}+{amt_col(i)}{sum_s+1}"
             f"+{amt_col(i)}{sum_s+2}+{amt_col(i)}{sum_s+3}")
        total_vals += [f, fthb(total_gi_row, i)]
    rows.append(["", "TOTAL GI COST"] + total_vals)

    write_tab(ws, rows)
    print(f"    -> GI Line: {len(rows)} rows, {n} month(s), THB/MT cells are formulas")


# ─────────────────────────────────────────────────────────────
# BUILD: SUPPORT  (data source reference)
# ─────────────────────────────────────────────────────────────
def build_support(ws):
    print("  Building Support tab (data source reference)...")

    S = ["", ""]   # blank row shorthand

    def sec(title):
        return ["", title]

    def hdr(*cols):
        return ["", *cols]

    # ── Section 1: Source Files ───────────────────────────────
    file_rows = [
        ["", "ASIA METAL PLC — Data Sources & Support Reference"],
        S,
        sec("1. SOURCE FILES"),
        hdr("File Pattern", "Location", "Coverage", "Description"),
        ["", "PRD_1300_MM.2026.XLSX",
         r"C:\Users\surasit.k\Documents\Month end\analytics\PRD_GI",
         "1 file per month", "SAP Production Order cost extract — Plant 1300 (GI)"],
        ["", "PRD_1100_MM.2026.XLSX",
         r"C:\Users\surasit.k\Documents\Month end\analytics\PRD_GI",
         "1 file per month", "SAP Production Order cost extract — Plant 1100 (Pipe A)"],
        ["", "PRD_1200_MM.2026.XLSX",
         r"C:\Users\surasit.k\Documents\Month end\analytics\PRD_GI",
         "1 file per month", "SAP Production Order cost extract — Plant 1200 (Pipe B)"],
        ["", "AMC_GL_03.2026.XLSX",
         r"C:\Users\surasit.k\Documents\Month end\analytics\PRD_GI",
         "Cumulative Jan–Mar", "SAP GL line items (FI module) — all plants, all accounts"],
        ["", "AMC_TB_MM.2026.XLSX",
         r"C:\Users\surasit.k\Documents\Month end\analytics\PRD_GI",
         "1 file per month", "SAP Trial Balance (F.01) — validation layer (not yet used)"],
        S,
    ]

    # ── Section 2: Data Mapping — Annual Total ────────────────
    mapping_hdr = hdr("Cost Item", "Source", "File / T-Code", "Filter / Key", "Notes")
    mapping_pk = [
        sec("2. DATA MAPPING — ANNUAL TOTAL / PK & CR"),
        mapping_hdr,
        ["", "HRC Used (Amount THB)",
         "PRD", "PRD_1300_MM.XLSX",
         "Order Type = Pickling/Cold Roll  →  col 'Actual GI Amount'",
         "Material cost of HRC consumed in PK+CR process"],
        ["", "HRC Used (Volume MT)",
         "PRD", "PRD_1300_MM.XLSX",
         "col 'Actual GI QTY' (input qty) / 1000",
         "HRC input in kg → convert to MT"],
        ["", "CRC Output (GR) — Volume MT",
         "PRD", "PRD_1300_MM.XLSX",
         "col 'Actual GR QTY' / 1000",
         "CRC output GR qty (finished CRC in kg)"],
        ["", "Scrap Actual (PK+CR)",
         "PRD", "PRD_1300_MM.XLSX",
         "sum(ByProduct Scrap + Grade B + Grade C amounts)",
         "All scrap/downgrade by-product from PK+CR orders"],
        ["", "Pickling Conversion Cost",
         "GL", "AMC_GL_03.2026.XLSX",
         "CC prefix 138711  +  overhead allocation from CC 138700/138710",
         "GL accts 58xx/55xx/56xx/57xx/59xx; excl. 5391020, 52xx, 54xx, 9xxx"],
        ["", "Cold Rolling Conversion Cost",
         "GL", "AMC_GL_03.2026.XLSX",
         "CC prefix 138712  +  overhead allocation",
         "Same account range as Pickling; overhead split by CRC:GIC output ratio"],
        ["", "Overhead allocation basis",
         "Calculated", "—",
         "(CC 138700 + 138710) × (PK GR qty / total qty)",
         "Parent CC overhead split proportionally to CRC output vs GIC output"],
        S,
    ]
    mapping_gi = [
        sec("3. DATA MAPPING — ANNUAL TOTAL / GI LINE"),
        mapping_hdr,
        ["", "CRC Used (GI input)",
         "Calculated", "PRD + GL",
         "PRD GI 'Actual GI Amount' MINUS Zinc+ZAM from GL 5411010",
         "CRC consumed at MAP; Zinc must be excluded from PRD total material"],
        ["", "Zinc + ZAM Alloy (Coating)",
         "GL", "AMC_GL_03.2026.XLSX",
         "GL 5411010 (Consumption-RM)  +  Material no. starts with 10INGZM* or 10GMC*",
         "NO Cost Center on these postings — filtered by material number instead of CC"],
        ["", "  ↳ Zinc Ingot",
         "GL", "AMC_GL_03.2026.XLSX",
         "GL 5411010, Material prefix = 10INGZM",
         "Jan≈3.7M  Feb≈0  Mar≈0 (ZAM catch-up posting in Mar)"],
        ["", "  ↳ ZAM Alloy",
         "GL", "AMC_GL_03.2026.XLSX",
         "GL 5411010, Material prefix = 10GMC",
         "Mar≈48.6M — verify in SAP (may be cumulative catch-up)"],
        ["", "GI Galvanized Output (GR) — Volume MT",
         "PRD", "PRD_1300_MM.XLSX",
         "Order Type contains 'Galvaniz'  →  col 'Actual GR QTY' / 1000",
         "GIC finished output in MT"],
        ["", "Scrap (Dross + Slag)",
         "PRD", "PRD_1300_MM.XLSX",
         "sum(ByProduct Scrap + Grade B + Grade C amounts)  for GI orders",
         "Zinc Dross/Slag recovery; Grade B/C GIC downgrade"],
        ["", "GI Conversion Cost",
         "GL", "AMC_GL_03.2026.XLSX",
         "CC prefix 13872  +  overhead allocation share",
         "Galvanizing Line; same GL account exclusion rules as PK+CR"],
        S,
    ]
    mapping_manual = [
        sec("4. GROUP C — MANUAL ITEMS (not in GL)"),
        hdr("Item", "SAP Status", "Impact", "Action Required"),
        ["", "HCl (Hydrochloric Acid)",
         "NOT in GL system",
         "~2-3% of Pickling conversion cost",
         "Key in actual monthly consumption cost to Annual Total col C/E/G"],
        ["", "LNG / Natural Gas",
         "NOT in GL system",
         "~3-5% of GI conversion cost",
         "Key in actual monthly cost to Annual Total"],
        ["", "Nitrogen (N₂)",
         "NOT in GL system",
         "~1% of GI conversion cost",
         "Key in actual monthly cost"],
        ["", "Hydrogen (H₂)",
         "NOT in GL system",
         "~1% of GI conversion cost",
         "Key in actual monthly cost"],
        ["", "Passivation Chemical",
         "NOT in GL system",
         "< 1% of GI conversion cost",
         "Key in actual monthly cost"],
        ["", "→ TOTAL GROUP C impact",
         "—",
         "~15% of total conversion cost",
         "Annual Total auto-updates Summary once filled"],
        S,
    ]
    gl_accounts = [
        sec("5. GL ACCOUNT REFERENCE — Cost Categories"),
        hdr("GL Prefix", "Description", "Included in Report?", "Notes"),
        ["", "5811xxx", "Depreciation",            "YES", "Fixed asset depreciation for production equipment"],
        ["", "5511xxx", "Labor — Direct (D101)",   "YES", "Direct labor + SAP Activity Type D101"],
        ["", "5512xxx / 5513xxx", "Labor — Indirect (D102)", "YES", "Indirect labor + D102"],
        ["", "5611xxx", "Electricity",             "YES", "Power consumption by CC"],
        ["", "5711xxx", "Repair & Maintenance",    "YES", "R&M costs including spare parts"],
        ["", "5911xxx", "Spare Parts & Supplies",  "YES", "Consumables, tooling"],
        ["", "5912xxx", "Mfg Supplies (Gas/Chem)", "YES", "Gas, chemicals (excludes Group C manual items)"],
        ["", "5991xxx / 6xxx", "Other",            "YES", "Catch-all; review if material"],
        ["", "5411010", "Consumption — Raw Material", "SPECIAL",
         "Zinc/ZAM only; filtered by Material number (no CC)"],
        ["", "5411020", "Consumption — Semi-FG",   "NO",
         "CRC transfer to GI; inter-process move (not conversion cost)"],
        ["", "5391020", "ML Price Adjustment",     "EXCLUDED",
         "Material Ledger correction; Jan Plant 1300 = 45.9M THB — always exclude"],
        ["", "52xxxx",  "Overhead absorption",     "EXCLUDED", ""],
        ["", "54xxxx",  "Consumption (general)",   "EXCLUDED", "Only 5411010 Zinc included via material filter"],
        ["", "7xxxxx",  "Period-end adjustments",  "EXCLUDED", ""],
        ["", "9xxxxx",  "CO statistical postings", "EXCLUDED", "Activity confirmations; not FI cost"],
        S,
    ]
    cc_ref = [
        sec("6. COST CENTER REFERENCE — Plant 1300 GI"),
        hdr("CC Prefix", "Description", "Used As"),
        ["", "138711x", "Pickling Line (Line 01)",      "Direct PK conversion cost"],
        ["", "138712x", "Cold Rolling Mill",             "Direct CR conversion cost"],
        ["", "13872xx", "Galvanizing Line",              "Direct GI conversion cost"],
        ["", "138700",  "GI Production — overhead",     "Allocated to PK+CR and GI proportionally"],
        ["", "138710",  "PK+CR — overhead",             "Allocated to PK+CR proportionally"],
        S,
    ]
    script_ref = [
        sec("7. SCRIPTS"),
        hdr("Script", "Function", "When to Run"),
        ["", "scripts/setup_gi_template.py",
         "Populate Annual Total, Summary formulas, PK & CR, GI Line, Monitoring",
         "Monthly — after SAP files are downloaded"],
        ["", "scripts/format_gi_template.py",
         "Apply professional formatting to all tabs",
         "After setup, or whenever tab structure changes"],
        ["", "scripts/populate_gi_cost_report.py",
         "Populate the main Cost Report Google Sheet (separate from template)",
         "Monthly — same cadence as setup"],
        ["", "scripts/format_gi_cost_report.py",
         "Format the main Cost Report Google Sheet",
         "After populate"],
    ]

    all_rows = (file_rows + mapping_pk + mapping_gi + mapping_manual
                + gl_accounts + cc_ref + script_ref)
    write_tab(ws, all_rows)
    print(f"    -> Support: {len(all_rows)} rows")


# ─────────────────────────────────────────────────────────────
# BUILD: MONITORING  (structure + yield formulas)
# ─────────────────────────────────────────────────────────────
def build_monitoring(ws):
    print("  Building Monitoring tab (structure + yield formulas)...")

    header = ["", "Metric", "Unit",
              "Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    def blank_row(label, unit):
        return ["", label, unit] + [""] * 12

    rows = [
        header,
        ["", ""],
        ["", "PICKLING & COLD ROLLING"],
        blank_row("HRC Input", "MT"),
        blank_row("CRC Grade A", "MT"),
        blank_row("CRC Grade B", "MT"),
        blank_row("Scrap (PK + CR)", "MT"),
        # Row 8 (index 6) = Scrap, Row 9 (index 7) = HRC Input
        # Yield Loss = 1 - CRC_GradeA / HRC_Input
        # In sheet: Scrap is rows[5], HRC is rows[3], CRC_A is rows[4]
        # sheet rows: PREPARED=1, header=2, blank=3, section=4, HRC=5, CRC_A=6, CRC_B=7, Scrap=8
        # Yield formula: =IFERROR(1-(D6+D7)/D5,"") for Jan (col D = Jan)
        ["", "% Yield Loss (PK+CR)", "%",
         *[f"=IFERROR(1-(D{r}+E{r})/D{r-1},\"\")" for r in [6]] +  # placeholder
         [""] * 11],
        blank_row("Electricity — Pickling", "kWh"),
        blank_row("Electricity — Cold Roll", "kWh"),
        blank_row("HCl Consumption (total)", "KG"),
        blank_row("Rolling Oil (Coolant)", "L"),
        ["", ""],
        ["", "GALVANIZING LINE"],
        blank_row("CRC Input", "MT"),
        blank_row("GI/ZAM Grade A", "MT"),
        blank_row("GI/ZAM Grade B", "MT"),
        blank_row("Scrap (GI Line)", "MT"),
        blank_row("% Yield Loss (GI)", "%"),
        blank_row("Zinc Ingot Consumed", "MT"),
        blank_row("Zinc Dross", "MT"),
        blank_row("Zinc Slag", "MT"),
        blank_row("Electricity — GI Line", "kWh"),
        blank_row("LNG Consumed", "NM3"),
        blank_row("Nitrogen Consumed", "NM3"),
        blank_row("Hydrogen Consumed", "NM3"),
        ["", ""],
        ["", "PRODUCTION VOLUME — by Coating Grade (MT)"],
    ]
    for grade in ["Z60","Z80","Z100","Z120","Z140","Z180","Z200","Z220","Z250","Z275","Z300",
                  "ZM60","ZM90","ZM120","ZM150","ZM180"]:
        rows.append(blank_row(f" {grade}", "MT"))

    rows.append(["", ""])
    rows.append(["", "Note: Manual input for physical production quantities (kWh, NM3, KG, MT by grade)."])
    rows.append(["", "      Volume rows (HRC Input, CRC Output, GI Output) are auto-filled from Annual Total "
                      "when script runs."])

    write_tab(ws, rows)
    print(f"    -> Monitoring: {len(rows)} rows")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Set up GI Cost Report Template with formulas")
    parser.add_argument("--months", type=int, nargs="+", default=[1, 2, 3],
                        help="Months to populate (default: 1 2 3)")
    parser.add_argument("--tabs", nargs="+",
                        default=["annual_total", "summary", "pk_cr", "gi_line", "monitoring", "support"],
                        help="Which tabs to rebuild")
    args = parser.parse_args()
    MONTHS[:] = args.months   # mutate in place — no global declaration needed

    print("=" * 65)
    print("GI Cost Report Template Setup")
    print(f"Sheet: {TEMPLATE_ID}")
    print(f"Months: {[MNAMES.get(m, m) for m in MONTHS]}")
    print(f"Tabs:   {args.tabs}")
    print("=" * 65)

    print("\nLoading GL file...")
    get_gl()
    print("GL loaded OK")

    print("\nConnecting to Google Sheets...")
    gc = get_gspread_client()

    # The original file is an XLSX — create a fresh native Google Sheets in the same folder.
    PARENT_FOLDER = "1b5gCkhM4cTfgEKtjRZQzX7ZgrHxpPOsp"
    SHEET_TITLE   = "Plant_GI_Costing_Template_2026"
    try:
        sh = gc.open(SHEET_TITLE)
        print(f"  Found existing sheet: {sh.id}")
    except gspread.SpreadsheetNotFound:
        sh = gc.create(SHEET_TITLE, folder_id=PARENT_FOLDER)
        print(f"  Created new sheet: {sh.id}")
        print(f"  URL: https://docs.google.com/spreadsheets/d/{sh.id}")
    TEMPLATE_ID = sh.id

    def get_ws(title):
        try:
            return sh.worksheet(title)
        except gspread.WorksheetNotFound:
            return sh.add_worksheet(title=title, rows=500, cols=30)

    print()
    if "annual_total" in args.tabs:
        build_annual_total(get_ws("Annual Total"))

    if "summary" in args.tabs:
        build_summary(get_ws("Summary"))

    if "pk_cr" in args.tabs:
        build_pk_cr(get_ws("PK & CR"), months=MONTHS)

    if "gi_line" in args.tabs:
        build_gi_line(get_ws("GI Line"), months=MONTHS)

    if "monitoring" in args.tabs:
        build_monitoring(get_ws("Monitoring"))

    if "support" in args.tabs:
        build_support(get_ws("Support"))

    url = f"https://docs.google.com/spreadsheets/d/{TEMPLATE_ID}"
    print(f"\n{'='*65}")
    print("DONE")
    print(f"URL: {url}")
    print(f"{'='*65}")
