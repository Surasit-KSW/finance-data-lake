"""
Populate GI Production Cost Report 2026
Google Sheet: 1suWgeMTLHrLdP8RYywFeHLwwusgGE2vp_3QfhZlR6wg

Tabs rebuilt:
  Summary      -> Cost Build-Up Overview (all 3 plants, Jan-Mar)
  PK & CR      -> Plant 1300 Pickling & Cold Rolling detail (Jan-Mar)
  GI Line      -> Plant 1300 Galvanizing Line detail (Jan-Mar)
  Monitoring   -> Production KPI by plant (volumes, yields)
  Product Group-> GIC cost by coating grade (Plant 1300)
  Annual Total -> Jan-Dec cost summary (Jan-Mar filled)
  Cost Center  -> (unchanged — kept as reference)
  Pipe_1100    -> Plant 1100 Slit + Pipe cost build-up (NEW)
  Pipe_1200    -> Plant 1200 Slit + Pipe + C-Channel (NEW)

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
SHEET_ID   = "1suWgeMTLHrLdP8RYywFeHLwwusgGE2vp_3QfhZlR6wg"
MONTHS     = [1, 2, 3]
MNAMES     = {1:"Jan", 2:"Feb", 3:"Mar"}
NOW        = datetime.now().strftime("%d/%m/%Y %H:%M")
PREPARED   = f"Prepared by: Claude Code | {NOW}"
I_IDX      = [43,46,49,52,55,58,61,64,67,70,73]

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def to_f(v):
    if pd.isna(v): return 0.0
    s = str(v).replace(",","").strip()
    if s.endswith("-"): return -float(s[:-1])
    try: return float(s)
    except: return 0.0

def r2(v): return round(float(v), 2)
def pct(a,b): return r2(a/b*100) if b else 0.0
def per_mt(cost, qty_kg): return r2(cost/(qty_kg/1000)) if qty_kg else 0.0
def fmt(v): return f"{r2(v):,.2f}"

# ─────────────────────────────────────────────────────────────
# LOAD PRD
# ─────────────────────────────────────────────────────────────
def load_prd(plant, month):
    path = os.path.join(DATA_DIR, f"PRD_{plant}_{month:02d}.2026.XLSX")
    df   = pd.read_excel(path, header=0)
    raw  = pd.read_excel(path, header=None)
    df.columns = [str(c) for c in df.columns]

    for c in ["Actual GI Amount","Actual ByProduct Scrap Amount",
              "Actual ByProduct Grade B Amount","Actual ByProduct Grade C Amount",
              "Actual GR Amount","Actual D101 Amount","Actual D102 Amount"]:
        df[c] = df[c].apply(to_f)

    df["GR_QTY"]  = pd.to_numeric(df["Actual GR QTY"],  errors="coerce").fillna(0)
    df["GI_QTY"]  = pd.to_numeric(df["Actual GI QTY"],  errors="coerce").fillna(0)

    for idx in I_IDX:
        df[f"_I{idx}"] = raw.iloc[1:, idx].apply(to_f).values
    df["_I_total"] = sum(df[f"_I{i}"] for i in I_IDX)
    df["_scrap"]   = (df["Actual ByProduct Scrap Amount"]
                    + df["Actual ByProduct Grade B Amount"]
                    + df["Actual ByProduct Grade C Amount"])

    ot = df["Order Type Name"].fillna("")
    if plant == "1300":
        df["_cat"] = np.where(ot.str.contains("Pickling|Cold Roll", case=False), "PK_CR",
                    np.where(ot.str.contains("Galvaniz", case=False), "GI", "Other"))
    else:
        df["_cat"] = np.where(ot.str.contains("Slit",    case=False), "SLIT",
                    np.where(ot.str.contains("Channel",  case=False), "C_CHANNEL",
                    np.where(ot.str.contains("Pipe",     case=False), "PIPE", "Other")))
    df["_plant"] = plant
    df["_month"] = month
    return df

# ─────────────────────────────────────────────────────────────
# LOAD GL (all 3 months, once)
# ─────────────────────────────────────────────────────────────
print("Loading GL file (this may take a moment)...")
_gl_cache = None

def get_gl():
    global _gl_cache
    if _gl_cache is not None:
        return _gl_cache
    f = os.path.join(DATA_DIR, "AMC_GL_03.2026.XLSX")
    gl = pd.read_excel(f, header=0)
    gl.columns = [str(c) for c in gl.columns]
    gl["CC_str"] = gl["Cost Center"].astype(str).str.strip()
    gl["GL_str"] = gl["G/L Account"].astype(str)
    gl["month"]  = pd.to_datetime(gl["Posting Date"], errors="coerce").dt.month
    gl["amt"]    = pd.to_numeric(gl["Company Code Currency Value"], errors="coerce").fillna(0)
    _gl_cache = gl
    return gl

def gl_conv(cc_prefix, month):
    """Sum actual conversion costs for a CC prefix group, a given month."""
    gl = get_gl()
    mask = (
        gl["CC_str"].str.startswith(cc_prefix) &
        (gl["month"] == month) &
        ~gl["GL_str"].str.startswith("9") &   # exclude CO settlements
        ~gl["GL_str"].str.startswith("52") &  # exclude semi-FG COGM
        ~gl["GL_str"].str.startswith("54") &  # exclude consumption
        ~gl["GL_str"].str.startswith("7") &   # exclude SGA
        (gl["GL_str"] != "5391020")           # exclude ML Adj
    )
    return r2(gl[mask]["amt"].sum())

def gl_by_cat(cc_prefix, month):
    """Breakdown by GL category for a CC prefix + month."""
    gl = get_gl()
    mask = (
        gl["CC_str"].str.startswith(cc_prefix) &
        (gl["month"] == month) &
        ~gl["GL_str"].str.startswith("9") &
        ~gl["GL_str"].str.startswith("52") &
        ~gl["GL_str"].str.startswith("54") &
        ~gl["GL_str"].str.startswith("7") &
        (gl["GL_str"] != "5391020")
    )
    sub = gl[mask].copy()
    def classify(a):
        if a.startswith("5511"): return "Labor Direct"
        if a.startswith("5512") or a.startswith("5513"): return "Labor Indirect/Welfare"
        if a.startswith("5611"): return "Electricity"
        if a.startswith("5711"): return "Repair & Maintenance"
        if a.startswith("5811"): return "Depreciation"
        if a.startswith("5911"): return "Tools & Supplies"
        if a.startswith("5912"): return "Mfg Supplies (Gas/Roller)"
        if a.startswith("599") or a.startswith("611"): return "Other / Transport"
        return "Other"
    sub["cat"] = sub["GL_str"].apply(classify)
    result = sub.groupby(["cat","G/L Account","G/L Account: Long Text"])["amt"].sum()
    return result.reset_index()

# ─────────────────────────────────────────────────────────────
# PRD AGGREGATION HELPERS
# ─────────────────────────────────────────────────────────────
def prd_agg(plant, month, cat):
    df  = load_prd(plant, month)
    sub = df[df["_cat"] == cat]
    if len(sub) == 0:
        return dict(rows=0, mat=0, d101=0, d102=0, i_tot=0,
                    scrap=0, gr_qty=0, gr_amt=0, gi_qty=0)
    return dict(
        rows   = len(sub),
        mat    = r2(sub["Actual GI Amount"].sum()),
        d101   = r2(sub["Actual D101 Amount"].sum()),
        d102   = r2(sub["Actual D102 Amount"].sum()),
        i_tot  = r2(sub["_I_total"].sum()),
        scrap  = r2(sub["_scrap"].sum()),
        gr_qty = r2(sub["GR_QTY"].sum()),   # kg
        gr_amt = r2(sub["Actual GR Amount"].sum()),
        gi_qty = r2(sub["GI_QTY"].sum()),   # kg (input)
    )

def prd_by_grade(month):
    """GIC cost per coating grade — Plant 1300 GI orders."""
    df  = load_prd("1300", month)
    sub = df[df["_cat"] == "GI"].copy()
    sub["_net"] = (sub["Actual GI Amount"] + sub["Actual D101 Amount"]
                 + sub["Actual D102 Amount"] + sub["_I_total"] - sub["_scrap"])
    grp = sub.groupby("GI Coating").agg(
        net_cost = ("_net","sum"),
        gr_qty   = ("GR_QTY","sum"),
    ).reset_index()
    grp["thb_per_mt"] = grp.apply(
        lambda r: per_mt(r["net_cost"], r["gr_qty"]), axis=1)
    return grp

# ─────────────────────────────────────────────────────────────
# SHEET WRITER HELPER
# ─────────────────────────────────────────────────────────────
def clear_and_write(ws, rows_data):
    """rows_data: list of lists. Row 1 = PREPARED stamp."""
    ws.clear()
    all_rows = [[PREPARED]] + rows_data
    ws.update(values=all_rows, range_name="A1")

# ─────────────────────────────────────────────────────────────
# TAB: SUMMARY — Cost Build-Up Overview
# ─────────────────────────────────────────────────────────────
def build_summary_tab(ws):
    print("  Building Summary tab...")
    rows = []

    rows.append(["ASIA METAL PLC — Production Cost Build-Up Report Q1 2026"])
    rows.append([""])
    rows.append(["Unit: THB / MT (metric ton)  |  Source: PRD + GL  |  All amounts ROUND(x,2)"])
    rows.append([""])

    # ── Plant 1300 ──────────────────────────────────────────
    rows.append(["PLANT 1300 — GI Production (Pickling+Cold Rolling → CRC → Galvanizing → GIC)"])
    rows.append(["Layer / Item", "Jan (THB)", "Jan (THB/MT)", "Feb (THB)", "Feb (THB/MT)",
                 "Mar (THB)", "Mar (THB/MT)", "Notes"])

    for m in MONTHS:
        pass  # precompute outside loop for reuse

    # Precompute all months
    p13 = {}
    for m in MONTHS:
        pk  = prd_agg("1300", m, "PK_CR")
        gi  = prd_agg("1300", m, "GI")
        # GL-based conversion (by CC group)
        pk_gl  = gl_conv("138711", m) + gl_conv("138712", m)  # PK + CR
        gi_gl  = gl_conv("13872",  m)                         # GI Line
        oh_gl  = gl_conv("138700", m) + gl_conv("13871000"[:6], m)  # General overhead
        # Allocate overhead by output volume
        tot_qty = pk["gr_qty"] + gi["gr_qty"]
        pk_oh   = r2(oh_gl * pk["gr_qty"] / tot_qty) if tot_qty else 0
        gi_oh   = r2(oh_gl * gi["gr_qty"] / tot_qty) if tot_qty else 0

        crc_mat_total = pk["mat"]
        crc_conv      = r2(pk_gl + pk_oh)
        crc_scrap     = pk["scrap"]
        crc_net       = r2(crc_mat_total + crc_conv - crc_scrap)

        # For GI: GI amount = CRC input at MAP + Zinc. Use PRD GI Amount.
        gic_mat_total = gi["mat"]   # CRC MAP + Zinc
        gic_conv      = r2(gi_gl + gi_oh)
        gic_scrap     = gi["scrap"]
        gic_net       = r2(gic_mat_total + gic_conv - gic_scrap)

        # Cumulative GIC cost (from raw HRC perspective not needed — just show layer add-on)
        p13[m] = dict(
            pk=pk, gi=gi,
            crc_mat=crc_mat_total, crc_conv=crc_conv, crc_scrap=crc_scrap,
            crc_net=crc_net, crc_qty=pk["gr_qty"],
            gic_mat=gic_mat_total, gic_conv=gic_conv, gic_scrap=gic_scrap,
            gic_net=gic_net, gic_qty=gi["gr_qty"],
        )

    def val3(fn):
        """Return [Jan_amt, Jan_thb_mt, Feb_amt, Feb_thb_mt, Mar_amt, Mar_thb_mt]"""
        return [v for m in MONTHS for v in fn(m)]

    # CRC layer
    rows.append(["── INPUT: HRC Material"]
        + val3(lambda m: [fmt(p13[m]["crc_mat"]), fmt(per_mt(p13[m]["crc_mat"], p13[m]["crc_qty"]))]))
    rows.append(["  + PK+CR Conversion (GL actual by CC)"]
        + val3(lambda m: [fmt(p13[m]["crc_conv"]), fmt(per_mt(p13[m]["crc_conv"], p13[m]["crc_qty"]))]))
    rows.append(["  (–) PK+CR Scrap Recovery"]
        + val3(lambda m: [fmt(-p13[m]["crc_scrap"]), fmt(per_mt(-p13[m]["crc_scrap"], p13[m]["crc_qty"]))]))
    rows.append(["= CRC Cost (Semi-FG)  **"]
        + val3(lambda m: [fmt(p13[m]["crc_net"]), fmt(per_mt(p13[m]["crc_net"], p13[m]["crc_qty"]))]))
    rows.append(["  CRC Output (MT)"]
        + val3(lambda m: [fmt(p13[m]["crc_qty"]/1000), ""]))
    rows.append([""])

    # GIC layer
    rows.append(["  + GI Input (CRC at MAP + Zinc Ingot)"]
        + val3(lambda m: [fmt(p13[m]["gic_mat"]), fmt(per_mt(p13[m]["gic_mat"], p13[m]["gic_qty"]))]))
    rows.append(["  + GI Conversion (GL actual by CC)"]
        + val3(lambda m: [fmt(p13[m]["gic_conv"]), fmt(per_mt(p13[m]["gic_conv"], p13[m]["gic_qty"]))]))
    rows.append(["  (–) GI Scrap (Dross/Slag/Grade B-C)"]
        + val3(lambda m: [fmt(-p13[m]["gic_scrap"]), fmt(per_mt(-p13[m]["gic_scrap"], p13[m]["gic_qty"]))]))
    rows.append(["= GIC Cost (Finished GI Coil)  **"]
        + val3(lambda m: [fmt(p13[m]["gic_net"]), fmt(per_mt(p13[m]["gic_net"], p13[m]["gic_qty"]))]))
    rows.append(["  GIC Output (MT)"]
        + val3(lambda m: [fmt(p13[m]["gic_qty"]/1000), ""]))
    rows.append([""])

    # ── Plant 1100 ──────────────────────────────────────────
    rows.append(["PLANT 1100 — Pipe Production Line A (Slitting → Roll Forming → Pipe / C-Channel)"])
    rows.append(["Layer / Item", "Jan (THB)", "Jan (THB/MT)", "Feb (THB)", "Feb (THB/MT)",
                 "Mar (THB)", "Mar (THB/MT)", "Notes"])

    for plant in ["1100","1200"]:
        p_label = "A" if plant=="1100" else "B"
        if plant == "1200":
            rows.append([f"PLANT 1200 — Pipe Production Line B (Slitting → Roll Forming → Pipe / C-Channel)"])
            rows.append(["Layer / Item", "Jan (THB)", "Jan (THB/MT)", "Feb (THB)", "Feb (THB/MT)",
                         "Mar (THB)", "Mar (THB/MT)", "Notes"])

        cc_pfx = "1187" if plant=="1100" else "1287"
        pp = {}
        for m in MONTHS:
            slit = prd_agg(plant, m, "SLIT")
            pipe = prd_agg(plant, m, "PIPE")
            cch  = prd_agg(plant, m, "C_CHANNEL")

            slit_gl = gl_conv(cc_pfx, m)   # all CC for this plant
            # Split GL cost by output volume ratio
            tot_qty = slit["gr_qty"] + pipe["gr_qty"] + cch["gr_qty"]
            slit_alloc = r2(slit_gl * slit["gr_qty"] / tot_qty) if tot_qty else 0
            pipe_alloc = r2(slit_gl * pipe["gr_qty"] / tot_qty) if tot_qty else 0
            cch_alloc  = r2(slit_gl * cch["gr_qty"]  / tot_qty) if tot_qty else 0

            # Use PRD D101+D102+I-total as conversion proxy (GL split is approximate)
            slit_conv = r2(slit["d101"] + slit["d102"] + slit["i_tot"])
            pipe_conv = r2(pipe["d101"] + pipe["d102"] + pipe["i_tot"])
            cch_conv  = r2(cch["d101"]  + cch["d102"]  + cch["i_tot"])

            slit_net = r2(slit["mat"] + slit_conv - slit["scrap"])
            pipe_net = r2(pipe["mat"] + pipe_conv - pipe["scrap"])
            cch_net  = r2(cch["mat"]  + cch_conv  - cch["scrap"])

            pp[m] = dict(
                slit=slit, pipe=pipe, cch=cch,
                slit_conv=slit_conv, pipe_conv=pipe_conv, cch_conv=cch_conv,
                slit_net=slit_net, pipe_net=pipe_net, cch_net=cch_net,
            )

        rows.append(["── INPUT: HRC / GIC Material (for Slitting)"]
            + val3(lambda m, pp=pp: [fmt(pp[m]["slit"]["mat"]),
                                     fmt(per_mt(pp[m]["slit"]["mat"], pp[m]["slit"]["gr_qty"]))]))
        rows.append(["  + Slit Conversion (D101+D102+Indirect)"]
            + val3(lambda m, pp=pp: [fmt(pp[m]["slit_conv"]),
                                     fmt(per_mt(pp[m]["slit_conv"], pp[m]["slit"]["gr_qty"]))]))
        rows.append(["  (–) Slit Scrap Recovery"]
            + val3(lambda m, pp=pp: [fmt(-pp[m]["slit"]["scrap"]),
                                     fmt(per_mt(-pp[m]["slit"]["scrap"], pp[m]["slit"]["gr_qty"]))]))
        rows.append(["= Slit Coil Cost  **"]
            + val3(lambda m, pp=pp: [fmt(pp[m]["slit_net"]),
                                     fmt(per_mt(pp[m]["slit_net"], pp[m]["slit"]["gr_qty"]))]))
        rows.append(["  Slit Output (MT)"]
            + val3(lambda m, pp=pp: [fmt(pp[m]["slit"]["gr_qty"]/1000), ""]))
        rows.append([""])
        rows.append(["  + Slit Coil Input to Pipe (at MAP)"]
            + val3(lambda m, pp=pp: [fmt(pp[m]["pipe"]["mat"]),
                                     fmt(per_mt(pp[m]["pipe"]["mat"], pp[m]["pipe"]["gr_qty"]))]))
        rows.append(["  + Pipe Forming Conversion"]
            + val3(lambda m, pp=pp: [fmt(pp[m]["pipe_conv"]),
                                     fmt(per_mt(pp[m]["pipe_conv"], pp[m]["pipe"]["gr_qty"]))]))
        rows.append(["  (–) Pipe Scrap Recovery"]
            + val3(lambda m, pp=pp: [fmt(-pp[m]["pipe"]["scrap"]),
                                     fmt(per_mt(-pp[m]["pipe"]["scrap"], pp[m]["pipe"]["gr_qty"]))]))
        rows.append(["= Pipe Cost (Finished)  **"]
            + val3(lambda m, pp=pp: [fmt(pp[m]["pipe_net"]),
                                     fmt(per_mt(pp[m]["pipe_net"], pp[m]["pipe"]["gr_qty"]))]))
        rows.append(["  Pipe Output (MT)"]
            + val3(lambda m, pp=pp: [fmt(pp[m]["pipe"]["gr_qty"]/1000), ""]))

        # C-Channel (Plant 1200 only)
        has_cch = any(pp[m]["cch"]["rows"]>0 for m in MONTHS)
        if has_cch:
            rows.append([""])
            rows.append(["  + C-Channel Input (at MAP)"]
                + val3(lambda m, pp=pp: [fmt(pp[m]["cch"]["mat"]),
                                         fmt(per_mt(pp[m]["cch"]["mat"], pp[m]["cch"]["gr_qty"]))]))
            rows.append(["  + C-Channel Forming Conversion"]
                + val3(lambda m, pp=pp: [fmt(pp[m]["cch_conv"]),
                                         fmt(per_mt(pp[m]["cch_conv"], pp[m]["cch"]["gr_qty"]))]))
            rows.append(["  (–) C-Channel Scrap"]
                + val3(lambda m, pp=pp: [fmt(-pp[m]["cch"]["scrap"]),
                                         fmt(per_mt(-pp[m]["cch"]["scrap"], pp[m]["cch"]["gr_qty"]))]))
            rows.append(["= C-Channel Cost (Finished)  **"]
                + val3(lambda m, pp=pp: [fmt(pp[m]["cch_net"]),
                                         fmt(per_mt(pp[m]["cch_net"], pp[m]["cch"]["gr_qty"]))]))
            rows.append(["  C-Channel Output (MT)"]
                + val3(lambda m, pp=pp: [fmt(pp[m]["cch"]["gr_qty"]/1000), ""]))

        rows.append([""])

    rows.append(["** GL Overhead Allocation note: GI_General CC (1387000-099) is allocated by output volume. "
                 "Pipe GL (1187/1287) uses PRD D101+D102+I-total for conversion (GL detail in Pipe_1100/Pipe_1200 tabs)."])

    clear_and_write(ws, rows)
    print(f"    -> {len(rows)} rows written")


# ─────────────────────────────────────────────────────────────
# TAB: PK & CR + GI LINE (detail by GL category)
# ─────────────────────────────────────────────────────────────
def build_process_detail_tab(ws, process_label, cc_prefix_list, tab_label):
    print(f"  Building {tab_label} tab...")
    rows = []
    rows.append([f"ASIA METAL PLC — Plant 1300 | {process_label} | Cost Detail by GL Account"])
    rows.append([""])
    rows.append(["Item / GL Account", "GL Account#", "Jan (THB)", "Jan (THB/MT)",
                 "Feb (THB)", "Feb (THB/MT)", "Mar (THB)", "Mar (THB/MT)"])

    # PRD volumes for THB/MT
    prd_cat = "PK_CR" if "PK" in tab_label else "GI"
    vol = {m: prd_agg("1300", m, prd_cat)["gr_qty"] for m in MONTHS}

    # Categories to show in order
    cat_order = ["Labor Direct","Labor Indirect/Welfare","Electricity",
                 "Repair & Maintenance","Depreciation","Mfg Supplies (Gas/Roller)",
                 "Tools & Supplies","Other / Transport","Other"]

    # Aggregate all GL data for all CC prefixes + all months
    gl_data = {}  # (month, cc_pfx) -> dataframe
    for m in MONTHS:
        combined = []
        for pfx in cc_prefix_list:
            sub = gl_by_cat(pfx, m)
            combined.append(sub)
        if combined:
            merged = pd.concat(combined).groupby(["cat","G/L Account","G/L Account: Long Text"])["amt"].sum()
            gl_data[m] = merged.reset_index()
        else:
            gl_data[m] = pd.DataFrame(columns=["cat","G/L Account","G/L Account: Long Text","amt"])

    # Get union of all GL accounts across months
    all_accounts = set()
    for m in MONTHS:
        for _, row in gl_data[m].iterrows():
            all_accounts.add((row["cat"], row["G/L Account"], row["G/L Account: Long Text"]))

    # Sort by category order then GL account
    def sort_key(x):
        cat, gl, _ = x
        return (cat_order.index(cat) if cat in cat_order else 99, gl)
    all_accounts = sorted(all_accounts, key=sort_key)

    # Build rows grouped by category
    current_cat = None
    cat_totals = {m: {c: 0.0 for c in cat_order+["Other"]} for m in MONTHS}

    for (cat, gl_acc, gl_name) in all_accounts:
        if cat != current_cat:
            if current_cat is not None:
                rows.append([""])
            rows.append([f"  [{cat}]"])
            current_cat = cat

        vals = []
        for m in MONTHS:
            sub = gl_data[m]
            mask = (sub["G/L Account"] == gl_acc)
            amt = r2(sub.loc[mask,"amt"].sum())
            cat_totals[m][cat] = r2(cat_totals[m][cat] + amt)
            vals += [fmt(amt), fmt(per_mt(amt, vol[m]))]

        rows.append(["  " + gl_name, gl_acc] + vals)

    # Category subtotals
    rows.append([""])
    rows.append(["─── SUBTOTALS BY CATEGORY ───"])
    rows.append(["Category", "", "Jan (THB)", "Jan (THB/MT)", "Feb (THB)", "Feb (THB/MT)",
                 "Mar (THB)", "Mar (THB/MT)"])
    grand = {m: 0.0 for m in MONTHS}
    for cat in cat_order:
        has_data = any(cat_totals[m][cat] != 0 for m in MONTHS)
        if not has_data:
            continue
        vals = []
        for m in MONTHS:
            v = cat_totals[m][cat]
            grand[m] = r2(grand[m] + v)
            vals += [fmt(v), fmt(per_mt(v, vol[m]))]
        rows.append([cat, ""] + vals)

    rows.append(["TOTAL CONVERSION COST", ""]
        + [v for m in MONTHS for v in [fmt(grand[m]), fmt(per_mt(grand[m], vol[m]))]])
    rows.append(["Output (MT)", ""]
        + [v for m in MONTHS for v in [fmt(vol[m]/1000), ""]])

    clear_and_write(ws, rows)
    print(f"    -> {len(rows)} rows written")


# ─────────────────────────────────────────────────────────────
# TAB: MONITORING — Production KPI
# ─────────────────────────────────────────────────────────────
def build_monitoring_tab(ws):
    print("  Building Monitoring tab...")
    rows = []
    rows.append(["ASIA METAL PLC — Production Monitoring | Q1 2026"])
    rows.append([""])
    rows.append(["Metric", "Unit", "Jan", "Feb", "Mar", "Q1 Total"])

    def row_data(plant, cat, field, divisor=1, unit="MT"):
        vals = []
        for m in MONTHS:
            s = prd_agg(plant, m, cat)
            v = r2(s[field] / divisor)
            vals.append(v)
        total = r2(sum(vals))
        return [unit] + [fmt(v) for v in vals] + [fmt(total)]

    rows.append([""])
    rows.append(["=== PLANT 1300 — GI Production ==="])
    rows.append(["HRC Input (raw material)",   "MT"] + [fmt(prd_agg("1300",m,"PK_CR")["gi_qty"]/1000) for m in MONTHS] + [""])
    rows.append(["CRC Output (PK+CR)",         "MT"] + [fmt(prd_agg("1300",m,"PK_CR")["gr_qty"]/1000) for m in MONTHS] + [""])
    rows.append(["Scrap (PK+CR)",               "MT"] + [fmt(prd_agg("1300",m,"PK_CR")["scrap"]/1000) for m in MONTHS] + [""])
    # Yield PK+CR
    rows.append(["Yield Loss % (PK+CR)",        "%"] + [
        fmt(pct(prd_agg("1300",m,"PK_CR")["scrap"], prd_agg("1300",m,"PK_CR")["gi_qty"])) for m in MONTHS] + [""])

    rows.append([""])
    rows.append(["CRC Input (to GI Line)",      "MT"] + [fmt(prd_agg("1300",m,"GI")["gi_qty"]/1000) for m in MONTHS] + [""])
    rows.append(["GIC Output (Galvanizing)",    "MT"] + [fmt(prd_agg("1300",m,"GI")["gr_qty"]/1000) for m in MONTHS] + [""])
    rows.append(["Scrap (GI Line incl. Dross)", "MT"] + [fmt(prd_agg("1300",m,"GI")["scrap"]/1000) for m in MONTHS] + [""])
    rows.append(["Yield Loss % (GI Line)",      "%"] + [
        fmt(pct(prd_agg("1300",m,"GI")["scrap"], prd_agg("1300",m,"GI")["gi_qty"])) for m in MONTHS] + [""])

    for plant, label in [("1100","PLANT 1100 — Pipe Line A"),("1200","PLANT 1200 — Pipe Line B")]:
        rows.append([""])
        rows.append([f"=== {label} ==="])
        for cat, cat_label in [("SLIT","Slitting"),("PIPE","Pipe Forming"),("C_CHANNEL","C-Channel")]:
            has_data = any(prd_agg(plant,m,cat)["rows"]>0 for m in MONTHS)
            if not has_data: continue
            rows.append([f"{cat_label} Input",  "MT"] + [fmt(prd_agg(plant,m,cat)["gi_qty"]/1000)  for m in MONTHS] + [""])
            rows.append([f"{cat_label} Output", "MT"] + [fmt(prd_agg(plant,m,cat)["gr_qty"]/1000)  for m in MONTHS] + [""])
            rows.append([f"{cat_label} Scrap",  "MT"] + [fmt(prd_agg(plant,m,cat)["scrap"]/1000)   for m in MONTHS] + [""])
            rows.append([f"Yield Loss % ({cat_label})","%"] + [
                fmt(pct(prd_agg(plant,m,cat)["scrap"], prd_agg(plant,m,cat)["gi_qty"])) for m in MONTHS] + [""])

    clear_and_write(ws, rows)
    print(f"    -> {len(rows)} rows written")


# ─────────────────────────────────────────────────────────────
# TAB: PRODUCT GROUP — GIC cost by coating grade
# ─────────────────────────────────────────────────────────────
def build_product_group_tab(ws):
    print("  Building Product Group tab...")
    rows = []
    rows.append(["ASIA METAL PLC — Plant 1300 | GIC Cost by Coating Grade | Q1 2026"])
    rows.append([""])
    rows.append(["Coating Grade", "Jan Output (MT)", "Jan Net Cost (THB)", "Jan THB/MT",
                 "Feb Output (MT)", "Feb Net Cost (THB)", "Feb THB/MT",
                 "Mar Output (MT)", "Mar Net Cost (THB)", "Mar THB/MT"])

    # Collect all grades
    all_grades = set()
    grade_data = {}
    for m in MONTHS:
        grp = prd_by_grade(m)
        grade_data[m] = grp.set_index("GI Coating")
        all_grades.update(grp["GI Coating"].tolist())

    # Sort grades
    def grade_sort(g):
        g = str(g)
        if g.startswith("Z"):
            try: return (0, int(g.replace("Z","").replace("M","")), g)
            except: return (0, 999, g)
        return (1, 0, g)
    all_grades = sorted(all_grades, key=grade_sort)

    for grade in all_grades:
        row_vals = [grade]
        for m in MONTHS:
            if grade in grade_data[m].index:
                r = grade_data[m].loc[grade]
                row_vals += [fmt(r["gr_qty"]/1000), fmt(r["net_cost"]), fmt(r["thb_per_mt"])]
            else:
                row_vals += ["0", "0.00", "0.00"]
        rows.append(row_vals)

    # Total row
    tot_row = ["TOTAL"]
    for m in MONTHS:
        grp = prd_by_grade(m)
        tot_row += [fmt(grp["gr_qty"].sum()/1000), fmt(grp["net_cost"].sum()),
                    fmt(per_mt(grp["net_cost"].sum(), grp["gr_qty"].sum()))]
    rows.append([""])
    rows.append(tot_row)
    rows.append([""])
    rows.append(["Note: Net Cost = GI Material (CRC+Zinc) + D101 + D102 + I-total – Scrap Recovery"])
    rows.append(["      Overhead (GL General CC) not allocated per grade — included in Summary tab"])

    clear_and_write(ws, rows)
    print(f"    -> {len(rows)} rows written")


# ─────────────────────────────────────────────────────────────
# TAB: ANNUAL TOTAL
# ─────────────────────────────────────────────────────────────
def build_annual_total_tab(ws):
    print("  Building Annual Total tab...")

    col_headers = ["Item", "Unit"]
    for m in [1,2,3]: col_headers += [f"{MNAMES[m]} THB", f"{MNAMES[m]} THB/MT"]
    for m_name in ["Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]:
        col_headers += [f"{m_name} THB", f"{m_name} THB/MT"]
    col_headers += ["YE'2026 THB", "YE'2026 THB/MT"]

    rows = [["ASIA METAL PLC — Annual Production Cost 2026"], [""], col_headers]

    def blank_future():
        return [""] * 18  # Apr-Dec + YE (9 months * 2 cols)

    def ye(vals_thb, vals_mt_denom):
        # YE = sum of Jan-Mar only (Apr-Dec blank)
        total = r2(sum(vals_thb))
        total_qty = r2(sum(vals_mt_denom))
        return [fmt(total), fmt(per_mt(total, total_qty))]

    for plant, plant_label in [("1300","Plant 1300 GI"), ("1100","Plant 1100 Pipe"), ("1200","Plant 1200 Pipe")]:
        rows.append([f""])
        rows.append([f"=== {plant_label} ==="])

        if plant == "1300":
            cat_list = [("PK_CR","PK+CR (CRC)"),("GI","GI Line (GIC)")]
        else:
            cat_list = [("SLIT","Slitting"),("PIPE","Pipe"),("C_CHANNEL","C-Channel")]

        for cat, cat_label in cat_list:
            has_data = any(prd_agg(plant,m,cat)["rows"]>0 for m in MONTHS)
            if not has_data: continue
            rows.append([f"  {cat_label}"])

            items = [
                ("  Material Input",     "THB", "mat"),
                ("  Conversion Cost",    "THB", "conv"),
                ("  Scrap Recovery",     "THB", "scrap"),
                ("  Net Cost",           "THB", "net"),
                ("  Output Volume",      "MT",  "vol"),
                ("  Net Cost/MT",        "THB/MT","rate"),
            ]

            for item_label, unit, key in items:
                vals_thb = []
                vals_qty = []
                for m in MONTHS:
                    s = prd_agg(plant, m, cat)
                    conv_s = r2(s["d101"]+s["d102"]+s["i_tot"])
                    net_s  = r2(s["mat"]+conv_s-s["scrap"])
                    vol_s  = s["gr_qty"]
                    mapping = {"mat":s["mat"],"conv":conv_s,"scrap":-s["scrap"],
                               "net":net_s,"vol":r2(vol_s/1000),"rate":per_mt(net_s,vol_s)}
                    v = mapping[key]
                    vals_thb.append(v)
                    vals_qty.append(vol_s)

                row = [item_label, unit]
                for i,m in enumerate(MONTHS):
                    v = vals_thb[i]
                    row += [fmt(v), fmt(per_mt(v, vals_qty[i])) if unit=="THB" else ""]
                row += blank_future()
                if unit == "THB":
                    row += ye(vals_thb, vals_qty)
                else:
                    row += [fmt(sum(vals_thb)), ""]
                rows.append(row)
            rows.append([])

    clear_and_write(ws, rows)
    print(f"    -> {len(rows)} rows written")


# ─────────────────────────────────────────────────────────────
# TAB: PIPE PLANT DETAIL (1100 or 1200)
# ─────────────────────────────────────────────────────────────
def build_pipe_tab(ws, plant):
    label = "1100 — Pipe Production Line A" if plant=="1100" else "1200 — Pipe Production Line B"
    print(f"  Building Pipe_{plant} tab...")
    rows = []
    rows.append([f"ASIA METAL PLC — Plant {label} | Cost Build-Up Detail | Q1 2026"])
    rows.append([""])

    header = ["Layer / Item", "Unit", "Jan (THB)", "Jan (THB/MT)", "Feb (THB)", "Feb (THB/MT)",
              "Mar (THB)", "Mar (THB/MT)"]
    rows.append(header)
    rows.append([""])

    cats = [("SLIT","Slitting"), ("PIPE","Pipe Forming")]
    if plant == "1200":
        cats.append(("C_CHANNEL","C-Channel Forming"))

    for cat, cat_label in cats:
        has_data = any(prd_agg(plant,m,cat)["rows"]>0 for m in MONTHS)
        if not has_data: continue

        rows.append([f"=== {cat_label.upper()} ==="])

        items = [
            ("Input Material (HRC/GIC/Slit Coil)", "mat"),
            ("  D101 — Direct Machine",            "d101"),
            ("  D102 — Direct Labour",             "d102"),
            ("  Indirect (I101-I111 pool)",         "i_tot"),
            ("  TOTAL Conversion",                  "conv"),
            ("  (–) Scrap Recovery",                "neg_scrap"),
            ("= NET Cost",                          "net"),
            ("Output Volume",                       "vol_mt"),
            ("Net Cost / MT",                       "rate"),
        ]

        for label_i, key in items:
            vals = []
            for m in MONTHS:
                s = prd_agg(plant, m, cat)
                conv = r2(s["d101"]+s["d102"]+s["i_tot"])
                net  = r2(s["mat"]+conv-s["scrap"])
                vol  = s["gr_qty"]
                mapping = {
                    "mat":s["mat"],"d101":s["d101"],"d102":s["d102"],"i_tot":s["i_tot"],
                    "conv":conv,"neg_scrap":-s["scrap"],"net":net,
                    "vol_mt":r2(vol/1000),"rate":per_mt(net,vol),
                }
                v = mapping[key]
                vals.append((v, vol))

            row = [label_i, "MT" if key in ("vol_mt","rate") else "THB"]
            for v, vol in vals:
                row += [fmt(v), fmt(per_mt(v, vol)) if key not in ("vol_mt","rate") else ""]
            rows.append(row)

        rows.append([""])

    # Order type breakdown
    rows.append(["=== ORDER TYPE BREAKDOWN ==="])
    rows.append(["Order Type", "Month", "Work Center", "# Orders",
                 "GR Output (MT)", "Net Cost (THB)", "THB/MT"])
    for m in MONTHS:
        df = load_prd(plant, m)
        for cat, cat_label in [("SLIT","Slit"),("PIPE","Pipe"),("C_CHANNEL","C-Channel")]:
            sub = df[df["_cat"]==cat]
            if len(sub)==0: continue
            # Group by Work Center Description
            for wc, g in sub.groupby("Work Center Description"):
                conv = r2(g["Actual D101 Amount"].sum()+g["Actual D102 Amount"].sum()+g["_I_total"].sum())
                net  = r2(g["Actual GI Amount"].sum()+conv-g["_scrap"].sum())
                vol  = g["GR_QTY"].sum()
                rows.append([cat_label, MNAMES[m], wc, len(g),
                              fmt(vol/1000), fmt(net), fmt(per_mt(net,vol))])

    rows.append([""])
    rows.append(["Note: Indirect (I101-I111) = activity-based allocation from cost center to orders."])
    rows.append(["      Full GL breakdown by account available in GL file filtered by CC " +
                 ("1187xxx" if plant=="1100" else "1287xxx")])
    rows.append([f"      Combined Orders: material on header row, conversion on original sub-rows."])

    clear_and_write(ws, rows)
    print(f"    -> {len(rows)} rows written")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 65)
    print("Populate GI Production Cost Report 2026")
    print("=" * 65)

    # Pre-load GL once
    get_gl()
    print("GL loaded OK\n")

    print("Connecting to Google Sheets...")
    gc = get_gspread_client()
    sh = gc.open_by_key(SHEET_ID)

    def get_or_create_ws(title, rows=500, cols=30):
        try:
            return sh.worksheet(title)
        except gspread.WorksheetNotFound:
            return sh.add_worksheet(title=title, rows=rows, cols=cols)

    tabs = {
        "Summary":      get_or_create_ws("Summary"),
        "PK & CR":      get_or_create_ws("PK & CR"),
        "GI Line":      get_or_create_ws("GI Line"),
        "Monitoring":   get_or_create_ws("Monitoring"),
        "Product Group":get_or_create_ws("Product Group"),
        "Annual Total": get_or_create_ws("Annual Total", rows=300, cols=28),
        "Pipe_1100":    get_or_create_ws("Pipe_1100"),
        "Pipe_1200":    get_or_create_ws("Pipe_1200"),
    }
    print()

    build_summary_tab(tabs["Summary"])
    build_process_detail_tab(tabs["PK & CR"], "Pickling & Cold Rolling",
                             ["138711","138712"], "PK_CR")
    build_process_detail_tab(tabs["GI Line"], "Galvanizing Line",
                             ["13872"], "GI")
    build_monitoring_tab(tabs["Monitoring"])
    build_product_group_tab(tabs["Product Group"])
    build_annual_total_tab(tabs["Annual Total"])
    build_pipe_tab(tabs["Pipe_1100"], "1100")
    build_pipe_tab(tabs["Pipe_1200"], "1200")

    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    print(f"\n{'='*65}")
    print(f"DONE")
    print(f"URL: {url}")
    print(f"{'='*65}")
