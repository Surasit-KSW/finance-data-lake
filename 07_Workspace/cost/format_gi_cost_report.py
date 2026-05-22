"""
Format & rebuild GI Production Cost Report 2026 with:
  - Professional colors, borders, frozen headers
  - Formulas for all total / THB/MT rows (traceable)
  - Source annotation in each tab
  - Number formats (#,##0.00)

Google Sheet: 1suWgeMTLHrLdP8RYywFeHLwwusgGE2vp_3QfhZlR6wg
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
SHEET_ID = "1suWgeMTLHrLdP8RYywFeHLwwusgGE2vp_3QfhZlR6wg"
MONTHS   = [1, 2, 3]
MN       = {1:"Jan", 2:"Feb", 3:"Mar"}
NOW      = datetime.now().strftime("%d/%m/%Y %H:%M")
I_IDX    = [43,46,49,52,55,58,61,64,67,70,73]

# ── Colour palette (normalised 0-1 for Sheets API) ──────────
def rgb(r,g,b): return {"red":r/255,"green":g/255,"blue":b/255}

C = {
    "dark_blue":   rgb(13 ,71 ,161),   # section plant header
    "mid_blue":    rgb(25 ,118,210),   # process sub-header
    "light_blue":  rgb(187,222,251),   # total / net row bg
    "pale_blue":   rgb(227,242,253),   # alt data row
    "green_bg":    rgb(200,230,201),   # final output / finished cost row
    "red_bg":      rgb(252,228,236),   # scrap / deduction row
    "yellow_bg":   rgb(255,249,196),   # highlight / grade row
    "header_dark": rgb(38 ,50 ,56 ),   # col header
    "white":       rgb(255,255,255),
    "black":       rgb(0  ,0  ,0  ),
    "gray_light":  rgb(245,245,245),
    "border_dark": rgb(33 ,33 ,33 ),
}

# ─────────────────────────────────────────────────────────────
# DATA HELPERS  (PRD + GL)
# ─────────────────────────────────────────────────────────────
def to_f(v):
    if pd.isna(v): return 0.0
    s = str(v).replace(",","").strip()
    if s.endswith("-"): return -float(s[:-1])
    try:    return float(s)
    except: return 0.0

def r2(v): return round(float(v),2)
def pct(a,b): return r2(a/b*100) if b else 0.0

print("Loading PRD files …")
_prd_cache = {}
def load_prd(plant, month):
    key = (plant, month)
    if key in _prd_cache: return _prd_cache[key]
    path = os.path.join(DATA_DIR, f"PRD_{plant}_{month:02d}.2026.XLSX")
    df   = pd.read_excel(path, header=0)
    raw  = pd.read_excel(path, header=None)
    df.columns = [str(c) for c in df.columns]
    for c in ["Actual GI Amount","Actual ByProduct Scrap Amount",
              "Actual ByProduct Grade B Amount","Actual ByProduct Grade C Amount",
              "Actual GR Amount","Actual D101 Amount","Actual D102 Amount"]:
        df[c] = df[c].apply(to_f)
    df["GR_QTY"] = pd.to_numeric(df["Actual GR QTY"], errors="coerce").fillna(0)
    df["GI_QTY"] = pd.to_numeric(df["Actual GI QTY"], errors="coerce").fillna(0)
    for idx in I_IDX:
        df[f"_I{idx}"] = raw.iloc[1:,idx].apply(to_f).values
    df["_I"]     = sum(df[f"_I{i}"] for i in I_IDX)
    df["_scrap"] = (df["Actual ByProduct Scrap Amount"]
                  + df["Actual ByProduct Grade B Amount"]
                  + df["Actual ByProduct Grade C Amount"])
    ot = df["Order Type Name"].fillna("")
    if plant == "1300":
        df["_cat"] = np.where(ot.str.contains("Pickling|Cold Roll",case=False),"PK_CR",
                    np.where(ot.str.contains("Galvaniz",           case=False),"GI","Other"))
    else:
        df["_cat"] = np.where(ot.str.contains("Slit",   case=False),"SLIT",
                    np.where(ot.str.contains("Channel", case=False),"C_CHANNEL",
                    np.where(ot.str.contains("Pipe",    case=False),"PIPE","Other")))
    _prd_cache[key] = df
    return df

def agg(plant, month, cat):
    df  = load_prd(plant, month)
    sub = df[df["_cat"]==cat]
    if len(sub)==0:
        return dict(mat=0,d101=0,d102=0,i=0,scrap=0,gr_kg=0,gi_kg=0,gr_amt=0)
    return dict(
        mat   = r2(sub["Actual GI Amount"].sum()),
        d101  = r2(sub["Actual D101 Amount"].sum()),
        d102  = r2(sub["Actual D102 Amount"].sum()),
        i     = r2(sub["_I"].sum()),
        scrap = r2(sub["_scrap"].sum()),
        gr_kg = r2(sub["GR_QTY"].sum()),
        gi_kg = r2(sub["GI_QTY"].sum()),
        gr_amt= r2(sub["Actual GR Amount"].sum()),
    )

print("Loading GL file …")
_gl = None
def get_gl():
    global _gl
    if _gl is not None: return _gl
    f  = os.path.join(DATA_DIR, "AMC_GL_03.2026.XLSX")
    gl = pd.read_excel(f, header=0)
    gl.columns = [str(c) for c in gl.columns]
    gl["CC"]    = gl["Cost Center"].astype(str).str.strip()
    gl["GL"]    = gl["G/L Account"].astype(str)
    gl["month"] = pd.to_datetime(gl["Posting Date"], errors="coerce").dt.month
    gl["amt"]   = pd.to_numeric(gl["Company Code Currency Value"], errors="coerce").fillna(0)
    _gl = gl
    return gl

def gl_sum(cc_pfx, month, exclude_sets=None):
    gl = get_gl()
    ex = {"9","52","54","7"}
    if exclude_sets: ex |= set(exclude_sets)
    mask = (
        gl["CC"].str.startswith(cc_pfx) &
        (gl["month"]==month) &
        ~gl["GL"].str[:2].isin({p[:2] for p in ex if len(p)==2}) &
        ~gl["GL"].str[:1].isin({p for p in ex if len(p)==1}) &
        (gl["GL"] != "5391020")
    )
    # finer exclusion
    mask2 = mask
    for p in ex:
        if len(p)>1:
            mask2 = mask2 & ~gl["GL"].str.startswith(p)
    return r2(gl[mask2]["amt"].sum())

def gl_by_cat(cc_pfx_list, month):
    gl = get_gl()
    def cl(a):
        if a.startswith("5511"): return "Labor Direct"
        if a.startswith("5512") or a.startswith("5513"): return "Labor Indirect & Welfare"
        if a.startswith("5611"): return "Electricity"
        if a.startswith("5711"): return "Repair & Maintenance"
        if a.startswith("5811"): return "Depreciation"
        if a.startswith("5911"): return "Tools & Supplies"
        if a.startswith("5912"): return "Mfg Supplies (Gas / Roller)"
        if a.startswith("599") or a.startswith("611"): return "Other & Transport"
        return None
    frames=[]
    for pfx in cc_pfx_list:
        mask = (
            gl["CC"].str.startswith(pfx) &
            (gl["month"]==month) &
            ~gl["GL"].str.startswith("9") &
            ~gl["GL"].str.startswith("52") &
            ~gl["GL"].str.startswith("54") &
            ~gl["GL"].str.startswith("7") &
            (gl["GL"]!="5391020")
        )
        frames.append(gl[mask])
    if not frames: return pd.DataFrame()
    sub = pd.concat(frames)
    sub = sub.copy()
    sub["cat"] = sub["GL"].apply(cl)
    sub = sub[sub["cat"].notna()]
    return sub.groupby(["cat","G/L Account","G/L Account: Long Text"])["amt"].sum().reset_index()

def grade_data(month):
    df  = load_prd("1300", month)
    sub = df[df["_cat"]=="GI"].copy()
    sub["_net"] = sub["Actual GI Amount"]+sub["Actual D101 Amount"]+sub["Actual D102 Amount"]+sub["_I"]-sub["_scrap"]
    return sub.groupby("GI Coating").agg(net=("_net","sum"),gr_kg=("GR_QTY","sum")).reset_index()

# ─────────────────────────────────────────────────────────────
# SHEET BUILDER  — tracks rows, builds data + fmt requests
# ─────────────────────────────────────────────────────────────
class SB:
    CAT_ORDER = ["Labor Direct","Labor Indirect & Welfare","Electricity",
                 "Repair & Maintenance","Depreciation",
                 "Mfg Supplies (Gas / Roller)","Tools & Supplies","Other & Transport"]

    def __init__(self, ws_id):
        self.ws_id = ws_id
        self.rows  = []   # list-of-list (values / formula strings)
        self.fmts  = []   # list of API format requests
        self.r     = 0    # current 0-based row index

    # ── cell reference helpers ────────────────────────────
    def col_letter(self, c):
        c += 1
        s=""
        while c:
            s = chr(65+(c-1)%26)+s
            c=(c-1)//26
        return s

    def ref(self, row0, col0):
        """1-based A1 ref from 0-based indices."""
        return f"{self.col_letter(col0)}{row0+1}"

    # ── row appenders ─────────────────────────────────────
    def add(self, cells, bg=None, bold=False, fg=None, num_fmt=None,
            italic=False, size=10, align=None, border_top=False, border_bot=False):
        self.rows.append(cells)
        ri = self.r
        cols = len(cells)

        cell_fmt = {}
        if bg:   cell_fmt["backgroundColor"] = bg
        if bold or italic or fg or size != 10:
            tf = {"bold": bold, "italic": italic, "fontSize": size}
            if fg: tf["foregroundColor"] = fg
            cell_fmt["textFormat"] = tf
        if num_fmt:
            cell_fmt["numberFormat"] = {"type":"NUMBER","pattern":num_fmt}
        if align:
            cell_fmt["horizontalAlignment"] = align

        if cell_fmt:
            self.fmts.append({
                "repeatCell":{
                    "range":{"sheetId":self.ws_id,"startRowIndex":ri,"endRowIndex":ri+1,
                             "startColumnIndex":0,"endColumnIndex":max(cols,12)},
                    "cell":{"userEnteredFormat":cell_fmt},
                    "fields":"userEnteredFormat("+",".join(cell_fmt.keys())+")"
                }
            })

        # borders
        if border_top or border_bot:
            sides = {}
            bstyle = {"style":"SOLID","width":1,"color":C["border_dark"]}
            if border_top: sides["top"]    = bstyle
            if border_bot: sides["bottom"] = bstyle
            self.fmts.append({
                "updateBorders":{
                    "range":{"sheetId":self.ws_id,"startRowIndex":ri,"endRowIndex":ri+1,
                             "startColumnIndex":0,"endColumnIndex":max(cols,12)},
                    **sides
                }
            })

        self.r += 1
        return ri  # return 0-based row index of this row

    def blank(self, n=1):
        for _ in range(n):
            self.add([""], bg=C["white"])

    # ── column-width setter ───────────────────────────────
    def set_col_width(self, col0, px):
        self.fmts.append({
            "updateDimensionProperties":{
                "range":{"sheetId":self.ws_id,"dimension":"COLUMNS",
                         "startIndex":col0,"endIndex":col0+1},
                "properties":{"pixelSize":px},
                "fields":"pixelSize"
            }
        })

    # ── freeze rows ───────────────────────────────────────
    def freeze(self, rows=1, cols=1):
        self.fmts.append({
            "updateSheetProperties":{
                "properties":{"sheetId":self.ws_id,
                               "gridProperties":{"frozenRowCount":rows,
                                                  "frozenColumnCount":cols}},
                "fields":"gridProperties.frozenRowCount,gridProperties.frozenColumnCount"
            }
        })

    # ── standard section builders ─────────────────────────
    def title_block(self, title, subtitle=""):
        self.add([title], bg=C["dark_blue"], bold=True, fg=C["white"], size=13, border_bot=True)
        if subtitle:
            self.add([subtitle], bg=C["pale_blue"], italic=True, size=9)
        self.blank()

    def col_header(self, cells):
        self.add(cells, bg=C["header_dark"], bold=True, fg=C["white"], size=9,
                 border_bot=True, align="CENTER")
        self.freeze(rows=self.r, cols=1)

    def section_header(self, label, color="mid_blue"):
        self.add([label], bg=C[color], bold=True, fg=C["white"], size=10,
                 border_top=True, border_bot=True)

    def data_row(self, cells, alt=False):
        return self.add(cells, bg=C["pale_blue"] if alt else C["white"], size=9)

    def scrap_row(self, cells):
        return self.add(cells, bg=C["red_bg"], size=9, italic=True)

    def total_row(self, cells, final=False):
        bg = C["green_bg"] if final else C["light_blue"]
        return self.add(cells, bg=bg, bold=True, size=9, border_top=True, border_bot=True)

    def source_note(self, txt):
        return self.add([txt], bg=C["gray_light"], italic=True, size=8)

    # ── number format overlay ─────────────────────────────
    def apply_num_fmt(self, start_row0, end_row0, start_col0, end_col0, pattern="#,##0.00"):
        self.fmts.append({
            "repeatCell":{
                "range":{"sheetId":self.ws_id,
                         "startRowIndex":start_row0,"endRowIndex":end_row0+1,
                         "startColumnIndex":start_col0,"endColumnIndex":end_col0+1},
                "cell":{"userEnteredFormat":{"numberFormat":{"type":"NUMBER","pattern":pattern}}},
                "fields":"userEnteredFormat.numberFormat"
            }
        })

    def apply_pct_fmt(self, start_row0, end_row0, start_col0, end_col0):
        self.apply_num_fmt(start_row0, end_row0, start_col0, end_col0, "0.00%")

    # ── write to sheet ────────────────────────────────────
    def flush(self, ws, sh):
        ws.clear()
        # 1) Clear ALL existing formatting + unmerge ALL cells first
        full_range = {
            "sheetId": self.ws_id,
            "startRowIndex": 0, "endRowIndex": 1000,
            "startColumnIndex": 0, "endColumnIndex": 30
        }
        sh.batch_update({"requests": [
            {"unmergeCells":  {"range": full_range}},
            {"updateCells":   {"range": full_range, "fields": "userEnteredFormat"}},
        ]})
        # 2) Write data
        ws.update(values=self.rows, range_name="A1", value_input_option="USER_ENTERED")
        # 3) Apply new formatting
        sh.batch_update({"requests": self.fmts})


# ─────────────────────────────────────────────────────────────
# TAB 1 — SUMMARY  (Cost Build-Up waterfall, all plants)
# ─────────────────────────────────────────────────────────────
def build_summary(ws, sh):
    print("  Summary …", end=" ")
    b = SB(ws.id)
    b.set_col_width(0, 310)
    for c in [1,3,5]: b.set_col_width(c, 150)
    for c in [2,4,6]: b.set_col_width(c, 115)

    b.title_block(
        "ASIA METAL PLC — Production Cost Build-Up Report 2026",
        f"Source: PRD + GL (Plant 1300 = GL actual by CC | Plant 1100/1200 = PRD D101+D102+I)  |  {NOW}"
    )
    b.col_header(["Layer / Item","Jan (THB)","Jan (THB/MT)","Feb (THB)","Feb (THB/MT)","Mar (THB)","Mar (THB/MT)"])

    # ── helper: write one 3-layer plant section ───────────
    def plant_section(plant, label, layers):
        """
        layers: list of dicts with keys:
          name, color, sub_items: [(row_label, values_list, row_type)]
          total_label, total_type, vol_row
        """
        b.blank()
        b.section_header(f"  {label}", "dark_blue")

        for layer in layers:
            b.section_header(f"    {layer['name']}", "mid_blue")
            comp_rows = []
            for row_label, vals, rtype in layer["items"]:
                fn = {"data": b.data_row, "scrap": b.scrap_row}.get(rtype, b.data_row)
                ri = fn([row_label] + vals)
                comp_rows.append(ri)

            # total row with formula
            tot_vals = []
            for ci in [1,3,5]:  # amount columns
                refs = "+".join(b.ref(ri, ci) for ri in comp_rows)
                tot_vals += [f"={refs}", ""]  # amount, THB/MT placeholder

            vol_row_label, vol_vals = layer["vol"]
            tot_ri   = b.total_row([layer["total_label"]] + tot_vals, final=layer.get("final",False))
            vol_ri   = b.data_row([vol_row_label] + vol_vals,
                                   alt=False)
            b.add([""], bg=C["white"])  # blank placeholder for THB/MT formulas

            # THB/MT formulas — overlay back on total row (right-aligned cols)
            # We'll just write a dedicated THB/MT row instead
            thb_mt_vals = []
            for ai, vi in [(1,1),(3,3),(5,5)]:  # amount col index, vol col index
                a_ref = b.ref(tot_ri, ai)
                v_ref = b.ref(vol_ri, vi)
                thb_mt_vals += ["", f'=IFERROR(ROUND({a_ref}/{v_ref},2),"-")']
            # patch tot_row columns 2,4,6 with THB/MT formulas
            for m_idx, ci in enumerate([2,4,6]):
                a_ref = b.ref(tot_ri, ci-1)
                v_ref = b.ref(vol_ri, ci-1)
                b.rows[tot_ri][ci] = f'=IFERROR(ROUND({a_ref}/{v_ref},2),"-")'
            b.rows[b.r-1] = [""]  # clear placeholder blank

    # ── Plant 1300 ───────────────────────────────────────
    p13 = {m: {
        "pk": agg("1300",m,"PK_CR"),
        "gi": agg("1300",m,"GI"),
        "pk_gl": sum(gl_sum(p,m) for p in ["138711","138712"]),
        "gi_gl": gl_sum("13872",m),
        "oh_gl": gl_sum("138700",m),
    } for m in MONTHS}

    # allocate overhead by volume
    for m in MONTHS:
        d = p13[m]
        tot_qty = d["pk"]["gr_kg"] + d["gi"]["gr_kg"]
        d["pk_oh"] = r2(d["oh_gl"]*d["pk"]["gr_kg"]/tot_qty) if tot_qty else 0
        d["gi_oh"] = r2(d["oh_gl"]*d["gi"]["gr_kg"]/tot_qty) if tot_qty else 0
        d["pk_conv"] = r2(d["pk_gl"] + d["pk_oh"])
        d["gi_conv"] = r2(d["gi_gl"] + d["gi_oh"])

    b.blank()
    b.section_header("PLANT 1300 — GI Production   (HRC → Pickling+CR → CRC → Galvanizing → GIC)", "dark_blue")

    # LAYER 1 PK+CR
    b.section_header("  LAYER 1 — Pickling & Cold Rolling → CRC (Semi-Finished)", "mid_blue")
    hrc_ri   = b.data_row(["  ▸ HRC Material Input (PRD GI Amount)"]
                          + [v for m in MONTHS for v in [p13[m]["pk"]["mat"], ""]])
    conv_ri  = b.data_row(["  ▸ PK+CR Conversion Cost  (GL actual CC 138711/138712 + overhead alloc)"]
                          + [v for m in MONTHS for v in [p13[m]["pk_conv"], ""]])
    scrap_ri = b.scrap_row(["  (–) PK+CR Scrap Recovery  (PRD ByProduct)"]
                           + [v for m in MONTHS for v in [-p13[m]["pk"]["scrap"], ""]])

    crc_refs = [f'={b.ref(hrc_ri,c)}+{b.ref(conv_ri,c)}+{b.ref(scrap_ri,c)}' for c in [1,3,5]]
    crc_vals  = [v for r in crc_refs for v in [r, ""]]
    crc_ri   = b.total_row(["= CRC Cost (Semi-FG)  ★"] + crc_vals)

    vol_pk = [v for m in MONTHS for v in [r2(p13[m]["pk"]["gr_kg"]/1000), ""]]
    vol_ri = b.data_row(["  CRC Output Volume (MT)"] + vol_pk, alt=True)

    # THB/MT formulas in total row cols 2,4,6
    for ai, vi in zip([1,3,5],[1,3,5]):
        col_thb = ai; col_vol = vi; col_mt = ai+1
        b.rows[crc_ri][col_mt] = f'=IFERROR(ROUND({b.ref(crc_ri,col_thb)}/{b.ref(vol_ri,col_vol)},2),"-")'

    b.blank()

    # LAYER 2 GI
    b.section_header("  LAYER 2 — Galvanizing Line → GIC (Finished GI Coil)", "mid_blue")
    mat_ri  = b.data_row(["  ▸ CRC Input at MAP + Zinc Ingot  (PRD GI Amount GI orders)"]
                         + [v for m in MONTHS for v in [p13[m]["gi"]["mat"], ""]])
    gconv_ri= b.data_row(["  ▸ GI Conversion Cost  (GL actual CC 13872x + overhead alloc)"]
                         + [v for m in MONTHS for v in [p13[m]["gi_conv"], ""]])
    gscr_ri = b.scrap_row(["  (–) GI Scrap Recovery  (Zinc Dross / Slag / Grade B-C)"]
                          + [v for m in MONTHS for v in [-p13[m]["gi"]["scrap"], ""]])

    gic_refs = [f'={b.ref(mat_ri,c)}+{b.ref(gconv_ri,c)}+{b.ref(gscr_ri,c)}' for c in [1,3,5]]
    gic_vals = [v for r in gic_refs for v in [r, ""]]
    gic_ri   = b.total_row(["= GIC Cost (Finished GI Coil)  ★"] + gic_vals, final=True)

    vol_gi = [v for m in MONTHS for v in [r2(p13[m]["gi"]["gr_kg"]/1000), ""]]
    gvol_ri= b.data_row(["  GIC Output Volume (MT)"] + vol_gi, alt=True)

    for ai in [1,3,5]:
        b.rows[gic_ri][ai+1] = f'=IFERROR(ROUND({b.ref(gic_ri,ai)}/{b.ref(gvol_ri,ai)},2),"-")'

    b.source_note("  Source: PRD_1300_MM.2026.XLSX + AMC_GL_03.2026.XLSX (CC 1387xxx, excl GL 5391020 ML Adj)")

    # ── Plant 1100 & 1200 ────────────────────────────────
    for plant, p_label in [("1100","PLANT 1100 — Pipe Production Line A"),
                           ("1200","PLANT 1200 — Pipe Production Line B")]:

        sub_label = "(HRC/GIC → Slitting → Roll Forming → Pipe"
        if plant=="1200": sub_label += " / C-Channel"
        sub_label += ")"

        b.blank()
        b.section_header(f"{p_label}   {sub_label}", "dark_blue")

        cats = [("SLIT","LAYER 1 — Slitting → Slit Coil"),
                ("PIPE","LAYER 2 — Pipe Forming → Finished Pipe")]
        if plant=="1200":
            cats.append(("C_CHANNEL","LAYER 3 — C-Channel Forming → Finished C-Channel"))

        for cat, layer_label in cats:
            has = any(agg(plant,m,cat)["gr_kg"]>0 for m in MONTHS)
            if not has: continue

            b.section_header(f"  {layer_label}", "mid_blue")

            mat_ri  = b.data_row(["  ▸ Input Material (HRC / GIC / Slit Coil at MAP)  — PRD GI Amount"]
                                 + [v for m in MONTHS for v in [agg(plant,m,cat)["mat"], ""]])
            d1_ri   = b.data_row(["    D101 Direct Machine  (PRD)"]
                                 + [v for m in MONTHS for v in [agg(plant,m,cat)["d101"], ""]])
            d2_ri   = b.data_row(["    D102 Direct Labour  (PRD)"]
                                 + [v for m in MONTHS for v in [agg(plant,m,cat)["d102"], ""]])
            ii_ri   = b.data_row(["    I101–I111 Indirect Pool  (PRD)"]
                                 + [v for m in MONTHS for v in [agg(plant,m,cat)["i"], ""]])

            conv_refs = [f'={b.ref(d1_ri,c)}+{b.ref(d2_ri,c)}+{b.ref(ii_ri,c)}' for c in [1,3,5]]
            conv_vals = [v for r in conv_refs for v in [r, ""]]
            conv_ri = b.data_row(["  ▸ Conversion Cost  (D101+D102+I-pool)  ="] + conv_vals, alt=True)

            scr_ri  = b.scrap_row(["  (–) Scrap Recovery  (PRD ByProduct)"]
                                  + [v for m in MONTHS for v in [-agg(plant,m,cat)["scrap"], ""]])

            net_refs = [f'={b.ref(mat_ri,c)}+{b.ref(conv_ri,c)}+{b.ref(scr_ri,c)}' for c in [1,3,5]]
            net_vals = [v for r in net_refs for v in [r, ""]]
            net_ri   = b.total_row(["= Net Cost  ★"] + net_vals,
                                   final=(cat in ["PIPE","C_CHANNEL"]))

            vol_vals = [v for m in MONTHS for v in [r2(agg(plant,m,cat)["gr_kg"]/1000), ""]]
            vol_ri   = b.data_row([f"  Output Volume (MT)"] + vol_vals, alt=True)

            for ai in [1,3,5]:
                b.rows[net_ri][ai+1] = f'=IFERROR(ROUND({b.ref(net_ri,ai)}/{b.ref(vol_ri,ai)},2),"-")'

        cc_str = "1187xxx" if plant=="1100" else "1287xxx"
        b.source_note(f"  Source: PRD_{plant}_MM.2026.XLSX  |  Conversion = PRD D101+D102+I-pool  |  GL detail: filter CC {cc_str} in Pipe_{plant} tab")

    # number format for amount cols
    b.apply_num_fmt(4, b.r-1, 1, 6, "#,##0.00")
    b.flush(ws, sh)
    print(f"OK  ({b.r} rows)")


# ─────────────────────────────────────────────────────────────
# HELPER — build one GL-detail section onto an existing SB
# ─────────────────────────────────────────────────────────────
def _gl_section(b, section_title, cc_pfx_list, prd_cat, vol_label):
    """
    Writes one GL-detail section (PK+CR or GI) onto builder b.
    Returns: grand_total_row_index, {month: vol_mt}
    """
    vols = {m: r2(agg("1300",m,prd_cat)["gr_kg"]/1000) for m in MONTHS}

    b.section_header(section_title, "dark_blue")
    b.add(["GL Account Name","GL#",
           "Jan (THB)","Jan (THB/MT)","Feb (THB)","Feb (THB/MT)","Mar (THB)","Mar (THB/MT)"],
          bg=C["header_dark"], bold=True, fg=C["white"], size=9)

    # collect GL accounts
    all_gl = {}
    for m in MONTHS:
        df = gl_by_cat(cc_pfx_list, m)
        if df.empty: continue
        for _, row in df.iterrows():
            k = (row["cat"], row["G/L Account"], row["G/L Account: Long Text"])
            if k not in all_gl: all_gl[k] = {}
            all_gl[k][m] = r2(row["amt"])

    cat_order = SB.CAT_ORDER
    def sk(k):
        cat,gl,_ = k
        return (cat_order.index(cat) if cat in cat_order else 99, gl)

    prev_cat = None
    cat_row_range = {}
    for key in sorted(all_gl.keys(), key=sk):
        cat, gl_acc, gl_name = key
        if cat != prev_cat:
            b.blank()
            b.section_header(f"    {cat}", "mid_blue")
            cat_row_range[cat] = []
            prev_cat = cat
        vals = [v for m in MONTHS for v in [all_gl[key].get(m,0), ""]]
        ri = b.data_row(["    " + gl_name, gl_acc] + vals)
        cat_row_range[cat].append(ri)

    # subtotals
    b.blank()
    b.add(["  Subtotal by Category","",
           "Jan (THB)","Jan (THB/MT)","Feb (THB)","Feb (THB/MT)","Mar (THB)","Mar (THB/MT)"],
          bg=C["header_dark"], bold=True, fg=C["white"], size=9)
    grand_rows = []
    for cat in cat_order:
        if cat not in cat_row_range or not cat_row_range[cat]: continue
        rlist = cat_row_range[cat]
        sub_vals = []
        for ci in [2,4,6]:
            sub_vals += [f'={"+" .join(b.ref(ri,ci) for ri in rlist)}', ""]
        sub_ri = b.total_row(["  " + cat, ""] + sub_vals)
        grand_rows.append(sub_ri)
        for ai, m in zip([2,4,6], MONTHS):
            b.rows[sub_ri][ai+1] = f'=IFERROR(ROUND({b.ref(sub_ri,ai)}/{vols[m]},2),"-")'

    # grand total
    b.blank()
    gt_vals = []
    for ci in [2,4,6]:
        refs = "+".join(b.ref(ri,ci) for ri in grand_rows) if grand_rows else "0"
        gt_vals += [f"={refs}", ""]
    gt_ri = b.total_row(["  TOTAL CONVERSION COST", ""] + gt_vals, final=True)
    for ai, m in zip([2,4,6], MONTHS):
        b.rows[gt_ri][ai+1] = f'=IFERROR(ROUND({b.ref(gt_ri,ai)}/{vols[m]},2),"-")'

    vol_vals = [v for m in MONTHS for v in [vols[m], ""]]
    b.data_row([f"  {vol_label}", ""] + vol_vals, alt=True)

    return gt_ri, vols


# ─────────────────────────────────────────────────────────────
# TAB 2 — PLANT_1300  (PK+CR + GI Line in one view)
# ─────────────────────────────────────────────────────────────
def build_plant_1300_tab(ws, sh):
    print("  Plant_1300 …", end=" ")
    b = SB(ws.id)
    b.set_col_width(0, 340)
    b.set_col_width(1, 110)
    for c in [2,4,6]: b.set_col_width(c, 148)
    for c in [3,5,7]: b.set_col_width(c, 115)

    b.title_block(
        "ASIA METAL PLC — Plant 1300 | GI Production Cost Detail  (PK+CR → CRC → GI Line → GIC)",
        f"Source: AMC_GL_03.2026.XLSX (CC 1387xxx, excl 5391020/52xxxx/54xxxx/7xxxx)  |  {NOW}"
    )
    b.col_header(["Item / GL Account","GL#",
                  "Jan (THB)","Jan (THB/MT)","Feb (THB)","Feb (THB/MT)",
                  "Mar (THB)","Mar (THB/MT)"])

    # ── SECTION 1: Pickling & Cold Rolling ───────────────
    b.blank()
    pk_gt_ri, pk_vols = _gl_section(
        b,
        "SECTION 1 — PICKLING & COLD ROLLING (CC 138711x / 138712x)   Output = CRC",
        ["138711","138712"], "PK_CR",
        "CRC Output Volume (MT) — PRD"
    )

    # CRC cost build-up box
    b.blank()
    hrc_vals = [v for m in MONTHS for v in [agg("1300",m,"PK_CR")["mat"], ""]]
    scr_vals = [v for m in MONTHS for v in [-agg("1300",m,"PK_CR")["scrap"], ""]]
    b.section_header("  ── CRC Cost Build-Up ──", "mid_blue")
    hrc_ri = b.data_row(["  HRC Material Input  (PRD Actual GI Amount)",""] + hrc_vals)
    pk_conv_ri = b.data_row(["  PK+CR Conversion  (GL total above)", ""]
        + [v for m in MONTHS
           for ci in [2]
           for v in [f'={b.ref(pk_gt_ri, 2 + list(MONTHS).index(m)*2)}', ""]])
    scr_ri   = b.scrap_row(["  (–) Scrap Recovery  (PRD ByProduct)",""] + scr_vals)

    crc_vals = []
    for ci in [2,4,6]:
        crc_vals += [f'={b.ref(hrc_ri,ci)}+{b.ref(pk_conv_ri,ci)}+{b.ref(scr_ri,ci)}',""]
    crc_ri = b.total_row(["= CRC COST (Semi-FG)  ★",""] + crc_vals, final=False)
    vol_pk = [v for m in MONTHS for v in [pk_vols[m], ""]]
    vol_pk_ri = b.data_row(["  CRC Output Volume (MT)",""] + vol_pk, alt=True)
    for ai in [2,4,6]:
        b.rows[crc_ri][ai+1] = f'=IFERROR(ROUND({b.ref(crc_ri,ai)}/{b.ref(vol_pk_ri,ai)},2),"-")'

    # ── SECTION 2: Galvanizing Line ───────────────────────
    b.blank()
    b.blank()
    gi_gt_ri, gi_vols = _gl_section(
        b,
        "SECTION 2 — GALVANIZING LINE (CC 13872xx)   Output = GIC",
        ["13872"], "GI",
        "GIC Output Volume (MT) — PRD"
    )

    # GIC cost build-up box
    b.blank()
    gi_mat_vals = [v for m in MONTHS for v in [agg("1300",m,"GI")["mat"], ""]]
    gi_scr_vals = [v for m in MONTHS for v in [-agg("1300",m,"GI")["scrap"], ""]]
    b.section_header("  ── GIC Cost Build-Up ──", "mid_blue")
    gi_mat_ri  = b.data_row(["  CRC Input at MAP + Zinc Ingot  (PRD Actual GI Amount)",""] + gi_mat_vals)
    gi_conv_ri = b.data_row(["  GI Conversion  (GL total above)",""]
        + [v for m in MONTHS
           for v in [f'={b.ref(gi_gt_ri, 2 + list(MONTHS).index(m)*2)}', ""]])
    gi_scr_ri  = b.scrap_row(["  (–) Scrap Recovery  (Dross / Slag / Grade B-C)",""] + gi_scr_vals)

    gic_vals = []
    for ci in [2,4,6]:
        gic_vals += [f'={b.ref(gi_mat_ri,ci)}+{b.ref(gi_conv_ri,ci)}+{b.ref(gi_scr_ri,ci)}',""]
    gic_ri = b.total_row(["= GIC COST (Finished GI Coil)  ★",""] + gic_vals, final=True)
    vol_gi = [v for m in MONTHS for v in [gi_vols[m], ""]]
    vol_gi_ri = b.data_row(["  GIC Output Volume (MT)",""] + vol_gi, alt=True)
    for ai in [2,4,6]:
        b.rows[gic_ri][ai+1] = f'=IFERROR(ROUND({b.ref(gic_ri,ai)}/{b.ref(vol_gi_ri,ai)},2),"-")'

    b.blank()
    b.source_note("  GL Exclusions: 5391020 (ML Price Adj) | 52xxxx (Semi-FG COGM) | 54xxxx (Consumption) | 7xxxxx (SGA)")
    b.source_note("  Overhead CC 1387000-099 included in respective section based on CC prefix")

    b.apply_num_fmt(3, b.r-1, 2, 7, "#,##0.00")
    b.flush(ws, sh)
    print(f"OK  ({b.r} rows)")


# ─────────────────────────────────────────────────────────────
# TAB 4 — MONITORING
# ─────────────────────────────────────────────────────────────
def build_monitoring(ws, sh):
    print("  Monitoring …", end=" ")
    b = SB(ws.id)
    b.set_col_width(0, 290)
    b.set_col_width(1, 65)
    for c in [2,3,4,5]: b.set_col_width(c, 120)

    b.title_block(
        "ASIA METAL PLC — Production Monitoring | Q1 2026",
        f"Source: PRD files (3 plants × 3 months)  |  {NOW}"
    )
    b.col_header(["Metric","Unit","Jan","Feb","Mar","Q1 Total"])

    def section(plant, label, cats):
        b.blank()
        b.section_header(f"  {label}", "dark_blue")
        for cat, cat_label in cats:
            has = any(agg(plant,m,cat)["gr_kg"]>0 for m in MONTHS)
            if not has: continue
            b.section_header(f"    {cat_label}", "mid_blue")

            rows_data = [
                ("Input (GI QTY)", "MT",  lambda s: r2(s["gi_kg"]/1000)),
                ("Output (GR QTY)","MT",  lambda s: r2(s["gr_kg"]/1000)),
                ("Scrap Recovery", "MT",  lambda s: r2(s["scrap"]/1000)),
                ("Yield Loss %",   "%",   lambda s: pct(s["scrap"], s["gi_kg"]) if s["gi_kg"] else 0),
            ]
            for r_label, unit, fn in rows_data:
                vals = [fn(agg(plant,m,cat)) for m in MONTHS]
                is_pct = unit == "%"
                r_ri  = b.data_row(["    " + r_label, unit]
                                    + [v/100 if is_pct else v for v in vals] + [""])
                # Q1 total formula (sum or avg for %)
                if is_pct:
                    # yield% = scrap_total / input_total
                    scrap_refs = "+".join(b.ref(r_ri, 2+i) for i in range(3))  # placeholder
                    b.rows[r_ri][5] = f'=IFERROR(AVERAGE({",".join(b.ref(r_ri,2+i) for i in range(3))}),"-")'
                else:
                    b.rows[r_ri][5] = f'=SUM({b.ref(r_ri,2)}:{b.ref(r_ri,4)})'
                if is_pct:
                    b.apply_pct_fmt(r_ri, r_ri, 2, 5)
                else:
                    b.apply_num_fmt(r_ri, r_ri, 2, 5, "#,##0.00")

    section("1300","PLANT 1300 — GI Production",
            [("PK_CR","Pickling & Cold Rolling → CRC"),("GI","Galvanizing → GIC")])
    section("1100","PLANT 1100 — Pipe Line A",
            [("SLIT","Slitting → Slit Coil"),("PIPE","Pipe Forming"),("C_CHANNEL","C-Channel")])
    section("1200","PLANT 1200 — Pipe Line B",
            [("SLIT","Slitting → Slit Coil"),("PIPE","Pipe Forming"),("C_CHANNEL","C-Channel")])

    b.source_note("  Note: Yield Loss % = Scrap (MT) / Input (MT) × 100")
    b.flush(ws, sh)
    print(f"OK  ({b.r} rows)")


# ─────────────────────────────────────────────────────────────
# TAB 5 — PRODUCT GROUP  (GIC cost by coating grade)
# ─────────────────────────────────────────────────────────────
def build_product_group(ws, sh):
    print("  Product Group …", end=" ")
    b = SB(ws.id)
    b.set_col_width(0, 130)
    for c in range(1,10): b.set_col_width(c, 130)

    b.title_block(
        "ASIA METAL PLC — Plant 1300 | GIC Cost by Coating Grade | Q1 2026",
        f"Source: PRD_1300_MM.2026.XLSX (GI orders grouped by GI Coating column)  |  {NOW}"
    )
    b.col_header(["Coating Grade",
                  "Jan Output (MT)","Jan Net Cost (THB)","Jan THB/MT",
                  "Feb Output (MT)","Feb Net Cost (THB)","Feb THB/MT",
                  "Mar Output (MT)","Mar Net Cost (THB)","Mar THB/MT"])

    all_grades = set()
    gd = {}
    for m in MONTHS:
        g = grade_data(m).set_index("GI Coating")
        gd[m] = g
        all_grades |= set(g.index)

    def gsort(g):
        s = str(g)
        num = s.replace("Z","").replace("M","")
        try:    return (0 if "M" not in s else 1, int(num))
        except: return (2, 0)

    tot_rows = []
    for grade in sorted(all_grades, key=gsort):
        vals = []
        for m in MONTHS:
            if grade in gd[m].index:
                r = gd[m].loc[grade]
                vals += [r2(r["gr_kg"]/1000), r2(r["net"]), ""]
            else:
                vals += [0, 0, ""]
        ri = b.data_row([grade] + vals)
        # THB/MT formulas
        for ci in [1,4,7]:
            vol_col = ci; cost_col = ci+1; rate_col = ci+2
            b.rows[ri][rate_col] = f'=IFERROR(ROUND({b.ref(ri,cost_col)}/{b.ref(ri,vol_col)},2),"-")'
        tot_rows.append(ri)

    b.blank()
    tot_vals = []
    for ci in [1,4,7]:
        sum_vol  = f'=SUM({",".join(b.ref(ri,ci)   for ri in tot_rows)})'
        sum_cost = f'=SUM({",".join(b.ref(ri,ci+1) for ri in tot_rows)})'
        tot_vals += [sum_vol, sum_cost, ""]
    tot_ri = b.total_row(["TOTAL"] + tot_vals, final=True)
    for ci in [1,4,7]:
        b.rows[tot_ri][ci+2] = f'=IFERROR(ROUND({b.ref(tot_ri,ci+1)}/{b.ref(tot_ri,ci)},2),"-")'

    b.blank()
    b.source_note("  Net Cost = GI Material Input + D101 + D102 + I-pool – Scrap  |  Overhead CC not allocated per grade (see Summary tab)")
    b.apply_num_fmt(3, b.r-1, 1, 9, "#,##0.00")
    b.flush(ws, sh)
    print(f"OK  ({b.r} rows)")


# ─────────────────────────────────────────────────────────────
# TAB 6 — ANNUAL TOTAL
# ─────────────────────────────────────────────────────────────
def build_annual_total(ws, sh):
    print("  Annual Total …", end=" ")
    b = SB(ws.id)
    b.set_col_width(0, 280)
    b.set_col_width(1, 65)
    for c in range(2, 28): b.set_col_width(c, 105)

    b.title_block(
        "ASIA METAL PLC — Annual Production Cost 2026  (Jan–Mar filled | Apr–Dec pending)",
        f"Source: PRD + GL  |  {NOW}"
    )

    all_months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    hdr = ["Item","Unit"]
    for mn in all_months: hdr += [f"{mn} THB", f"{mn} THB/MT"]
    hdr += ["YE'2026 THB","YE'2026 THB/MT"]
    b.col_header(hdr)

    def blank_cols(n=18): return [""]*n  # 9 months × 2 cols

    for plant, plant_label in [("1300","Plant 1300 — GI"),
                                ("1100","Plant 1100 — Pipe A"),
                                ("1200","Plant 1200 — Pipe B")]:
        b.blank()
        b.section_header(f"  {plant_label}", "dark_blue")

        cats = [("PK_CR","PK+CR → CRC"),("GI","GI Line → GIC")] if plant=="1300" else \
               [("SLIT","Slitting"),("PIPE","Pipe"),("C_CHANNEL","C-Channel")]

        for cat, cat_label in cats:
            has = any(agg(plant,m,cat)["gr_kg"]>0 for m in MONTHS)
            if not has: continue
            b.section_header(f"    {cat_label}", "mid_blue")

            items = [
                ("    Material Input",    "THB",   lambda s: s["mat"]),
                ("    Conversion",        "THB",   lambda s: r2(s["d101"]+s["d102"]+s["i"])),
                ("    (–) Scrap",         "THB",   lambda s: -s["scrap"]),
                ("    Net Cost",          "THB",   None),   # formula
                ("    Output Volume",     "MT",    lambda s: r2(s["gr_kg"]/1000)),
                ("    Net Cost / MT",     "THB/MT",None),   # formula
            ]

            item_rows = {}
            for i_label, unit, fn in items:
                if fn is None:
                    item_rows[i_label] = None
                    continue
                vals = []
                for m in MONTHS: vals += [fn(agg(plant,m,cat)), ""]
                ri = b.data_row([i_label, unit] + vals + blank_cols() + ["",""])
                item_rows[i_label] = ri

            # Net Cost formula row
            mat_ri  = item_rows["    Material Input"]
            conv_ri = item_rows["    Conversion"]
            scr_ri  = item_rows["    (–) Scrap"]
            net_vals = []
            for ci in [2,4,6]:
                net_vals += [f'={b.ref(mat_ri,ci)}+{b.ref(conv_ri,ci)}+{b.ref(scr_ri,ci)}',""]
            net_ri = b.total_row(["    Net Cost","THB"] + net_vals + blank_cols() + ["",""])

            vol_ri = item_rows["    Output Volume"]

            # THB/MT formula row
            rate_vals = []
            for ai, vi in [(2,2),(4,4),(6,6)]:
                rate_vals += ["", f'=IFERROR(ROUND({b.ref(net_ri,ai)}/{b.ref(vol_ri,vi)},2),"-")']
            b.total_row(["    Net Cost / MT","THB/MT"] + rate_vals + blank_cols() + ["",""])

            # YE formula (sum Jan-Mar amounts in net row)
            ye_val  = f'=SUM({b.ref(net_ri,2)},{b.ref(net_ri,4)},{b.ref(net_ri,6)})'
            ye_vol  = f'=SUM({b.ref(vol_ri,2)},{b.ref(vol_ri,4)},{b.ref(vol_ri,6)})'
            b.rows[net_ri][26] = ye_val
            b.rows[net_ri][27] = f'=IFERROR(ROUND({b.ref(net_ri,26)}/{ye_vol},2),"-")'

    b.apply_num_fmt(3, b.r-1, 2, 27, "#,##0.00")
    b.flush(ws, sh)
    print(f"OK  ({b.r} rows)")


# ─────────────────────────────────────────────────────────────
# TAB 7/8 — PIPE PLANT DETAIL  (1100 / 1200)
# ─────────────────────────────────────────────────────────────
def build_pipe_detail(ws, sh, plant):
    label = f"Pipe Production Line {'A' if plant=='1100' else 'B'}"
    print(f"  Pipe_{plant} …", end=" ")
    b = SB(ws.id)
    b.set_col_width(0, 320)
    for c in [1,3,5]: b.set_col_width(c, 145)
    for c in [2,4,6]: b.set_col_width(c, 115)

    b.title_block(
        f"ASIA METAL PLC — Plant {plant} | {label} | Cost Build-Up Detail",
        f"Source: PRD_{plant}_MM.2026.XLSX  |  Conversion = PRD D101+D102+I-pool  |  {NOW}"
    )
    b.col_header(["Layer / Item","Jan (THB)","Jan (THB/MT)","Feb (THB)","Feb (THB/MT)","Mar (THB)","Mar (THB/MT)"])

    cats = [("SLIT","LAYER 1 — Slitting → Slit Coil"),
            ("PIPE","LAYER 2 — Pipe Forming → Finished Pipe")]
    if plant=="1200":
        cats.append(("C_CHANNEL","LAYER 3 — C-Channel Forming → Finished C-Channel"))

    for cat, layer_label in cats:
        has = any(agg(plant,m,cat)["gr_kg"]>0 for m in MONTHS)
        if not has: continue

        b.blank()
        b.section_header(layer_label, "dark_blue")
        b.section_header("  ── Cost Components ──", "mid_blue")

        items = [
            ("  ▸ Input Material  (PRD Actual GI Amount)",  "mat",  False),
            ("    D101 — Direct Machine                   (PRD col 37)", "d101", False),
            ("    D102 — Direct Labour                    (PRD col 40)", "d102", False),
            ("    I101–I111 — Indirect Cost Pool          (PRD col 43…73)", "i",  False),
        ]
        comp_rows = []
        for i_label, key, is_scrap in items:
            vals = [v for m in MONTHS for v in [agg(plant,m,cat)[key], ""]]
            ri   = b.data_row([i_label] + vals)
            comp_rows.append(ri)

        conv_refs = [f'={b.ref(comp_rows[1],c)}+{b.ref(comp_rows[2],c)}+{b.ref(comp_rows[3],c)}'
                     for c in [1,3,5]]
        conv_vals = [v for r in conv_refs for v in [r, ""]]
        conv_ri   = b.data_row(["  ▸ Total Conversion  = D101+D102+I  (formula)"] + conv_vals, alt=True)

        scr_vals = [v for m in MONTHS for v in [-agg(plant,m,cat)["scrap"], ""]]
        scr_ri   = b.scrap_row(["  (–) Scrap Recovery  (PRD ByProduct Amounts)"] + scr_vals)

        net_refs = [f'={b.ref(comp_rows[0],c)}+{b.ref(conv_ri,c)}+{b.ref(scr_ri,c)}'
                    for c in [1,3,5]]
        net_vals = [v for r in net_refs for v in [r, ""]]
        net_ri   = b.total_row(["= Net Cost  ★"] + net_vals, final=True)

        vol_vals = [v for m in MONTHS for v in [r2(agg(plant,m,cat)["gr_kg"]/1000), ""]]
        vol_ri   = b.data_row(["  Output Volume (MT)"] + vol_vals, alt=True)

        for ai in [1,3,5]:
            b.rows[net_ri][ai+1] = f'=IFERROR(ROUND({b.ref(net_ri,ai)}/{b.ref(vol_ri,ai)},2),"-")'

    # Work-Center breakdown
    b.blank()
    b.blank()
    b.section_header("  ── BREAKDOWN BY WORK CENTER & ORDER TYPE ──", "dark_blue")
    b.col_header(["Order Type","Month","Work Center","# Orders",
                  "Output (MT)","Net Cost (THB)","THB/MT"])

    def wc_grp(cat_label):
        for m in MONTHS:
            df = load_prd(plant, m)
            cat_map = {"SLIT":"SLIT","PIPE":"PIPE","C_CHANNEL":"C_CHANNEL"}
            for cat, cl in [("SLIT","Slit"),("PIPE","Pipe"),("C_CHANNEL","C-Channel")]:
                sub = df[df["_cat"]==cat]
                if len(sub)==0: continue
                for wc, g in sub.groupby("Work Center Description"):
                    conv = r2(g["Actual D101 Amount"].sum()+g["Actual D102 Amount"].sum()+g["_I"].sum())
                    net  = r2(g["Actual GI Amount"].sum()+conv-g["_scrap"].sum())
                    vol  = g["GR_QTY"].sum()
                    ri = b.data_row([cl, MN[m], wc, int(len(g)),
                                     r2(vol/1000), net,
                                     r2(net/(vol/1000)) if vol else 0])
    wc_grp("")
    b.blank()
    b.source_note(f"  Note: Combined Orders — material on header row, conversion on sub-rows  |  I-pool may understate if indirect allocated outside CO to order")
    b.apply_num_fmt(3, b.r-1, 1, 6, "#,##0.00")
    b.flush(ws, sh)
    print(f"OK  ({b.r} rows)")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("="*65)
    print("Format & Rebuild  —  GI Production Cost Report 2026")
    print("="*65)

    get_gl()
    print("GL ready\n")

    gc = get_gspread_client()
    sh = gc.open_by_key(SHEET_ID)

    def ws(name):
        try:    return sh.worksheet(name)
        except: return sh.add_worksheet(title=name, rows=500, cols=30)

    build_summary       (ws("Summary"),      sh)
    build_plant_1300_tab(ws("Plant_1300"),   sh)
    build_monitoring    (ws("Monitoring"),   sh)
    build_product_group (ws("Product Group"),sh)
    build_annual_total  (ws("Annual Total"),  sh)
    build_pipe_detail   (ws("Pipe_1100"),     sh, "1100")
    build_pipe_detail   (ws("Pipe_1200"),     sh, "1200")

    print(f"\n{'='*65}")
    print(f"DONE  —  https://docs.google.com/spreadsheets/d/{SHEET_ID}")
    print(f"{'='*65}")
