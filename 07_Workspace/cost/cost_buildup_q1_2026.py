"""
Cost Build-Up Report — Q1 2026 (Jan-Mar)
Plants: 1300 (GI), 1100 (Pipe A), 1200 (Pipe B)

Output: Google Sheet with 3 sections:
  1. Summary — Cost/kg waterfall per plant per month
  2. Detail_1300 — GI layer breakdown (PK+CR / GI)
  3. Detail_1100 — Slit / Pipe / C-Channel breakdown
  4. Detail_1200 — Slit / Pipe / C-Channel breakdown
  5. Raw_PRD — Full PRD data (all plants, all months)

Prepared by: Claude Code
"""

import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.auth import get_gspread_client

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
DATA_DIR  = r"C:\Users\surasit.k\Documents\Month end\analytics\PRD_GI"
MONTHS    = [1, 2, 3]
PLANTS    = ["1300", "1100", "1200"]
SHEET_NAME = "COST_BUILDUP_GI_Pipe_Q1_2026"

I_COLS_IDX = [43, 46, 49, 52, 55, 58, 61, 64, 67, 70, 73]

GL_GROUPS = {
    "Labor_Direct":    lambda g: str(g).startswith("5511"),
    "Labor_Indirect":  lambda g: str(g).startswith("5512"),
    "Labor_Welfare":   lambda g: str(g).startswith("5513"),
    "Electricity":     lambda g: str(g).startswith("5611"),
    "RM":              lambda g: str(g).startswith("5711"),
    "Depreciation":    lambda g: str(g).startswith("5811"),
    "Tools_Supplies":  lambda g: str(g).startswith("5911"),
    "Mfg_Supplies":    lambda g: str(g).startswith("5912"),
    "Other_Expense":   lambda g: str(g).startswith("599") or str(g).startswith("611"),
    "CO_Settlement":   lambda g: str(g).startswith("943"),
    "Consumption":     lambda g: str(g).startswith("541"),
    "Variance":        lambda g: str(g).startswith("531"),
    "ML_Adj_EXCLUDE":  lambda g: str(g) == "5391020",
}

# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────
def to_f(v):
    """Convert SAP-formatted number string to float."""
    if pd.isna(v):
        return 0.0
    s = str(v).replace(",", "").strip()
    if s.endswith("-"):
        return -float(s[:-1])
    try:
        return float(s)
    except:
        return 0.0

def r2(v):
    return round(v, 2)

def per_kg(cost, qty):
    """Cost per kg, returns 0 if qty == 0."""
    if qty == 0:
        return 0.0
    return r2(cost / qty)

# ──────────────────────────────────────────────
# LOAD PRD
# ──────────────────────────────────────────────
def load_prd(plant, month):
    """Load PRD for a given plant/month. Returns (df_named, df_raw)."""
    path = os.path.join(DATA_DIR, f"PRD_{plant}_{month:02d}.2026.XLSX")
    df   = pd.read_excel(path, header=0)
    raw  = pd.read_excel(path, header=None)
    df.columns = [str(c) for c in df.columns]

    # Amount columns
    amt_cols = [
        "Actual GI Amount", "Actual ByProduct Scrap Amount",
        "Actual ByProduct Grade B Amount", "Actual ByProduct Grade C Amount",
        "Actual GR Amount", "Actual D101 Amount", "Actual D102 Amount",
    ]
    for c in amt_cols:
        df[c] = df[c].apply(to_f)

    df["Actual GR QTY"] = pd.to_numeric(df["Actual GR QTY"], errors="coerce").fillna(0)

    # I-columns from raw (header=None)
    for idx in I_COLS_IDX:
        df[f"_I_{idx}"] = raw.iloc[1:, idx].apply(to_f).values

    df["_I_total"] = sum(df[f"_I_{i}"] for i in I_COLS_IDX)
    df["_scrap_total"] = (
        df["Actual ByProduct Scrap Amount"]
        + df["Actual ByProduct Grade B Amount"]
        + df["Actual ByProduct Grade C Amount"]
    )

    # Categorise
    ot = df["Order Type Name"].fillna("")
    if plant == "1300":
        df["_cat"] = np.where(ot.str.contains("Pickling|Cold Roll", case=False), "PK_CR",
                    np.where(ot.str.contains("Galvaniz",            case=False), "GI", "Other"))
    else:
        df["_cat"] = np.where(ot.str.contains("Slit",    case=False), "SLIT",
                    np.where(ot.str.contains("Channel",  case=False), "C_CHANNEL",
                    np.where(ot.str.contains("Pipe",     case=False), "PIPE", "Other")))

    df["_plant"] = plant
    df["_month"] = month
    return df

# ──────────────────────────────────────────────
# AGGREGATE LAYER COSTS
# ──────────────────────────────────────────────
def layer_summary(sub):
    """Aggregate one category slice into cost components."""
    return {
        "rows":         len(sub),
        "mat_input":    r2(sub["Actual GI Amount"].sum()),
        "d101":         r2(sub["Actual D101 Amount"].sum()),
        "d102":         r2(sub["Actual D102 Amount"].sum()),
        "indirect":     r2(sub["_I_total"].sum()),
        "scrap":        r2(sub["_scrap_total"].sum()),
        "gr_qty_kg":    r2(sub["Actual GR QTY"].sum()),
        "gr_amount":    r2(sub["Actual GR Amount"].sum()),
    }

def net_cost(s):
    return r2(s["mat_input"] + s["d101"] + s["d102"] + s["indirect"] - s["scrap"])

# ──────────────────────────────────────────────
# BUILD SUMMARY TABLE
# ──────────────────────────────────────────────
def build_summary():
    rows = []

    for month in MONTHS:
        month_name = ["", "Jan", "Feb", "Mar"][month]

        # ── Plant 1300 ──────────────────────────
        df = load_prd("1300", month)

        pk   = layer_summary(df[df["_cat"] == "PK_CR"])
        gi   = layer_summary(df[df["_cat"] == "GI"])

        crc_cost = net_cost(pk)
        gic_cost = r2(crc_cost + net_cost(gi))  # cumulative

        rows += [
            ["1300", month_name, "── Input: HRC Material",
             pk["mat_input"], "", "", "", ""],
            ["1300", month_name, "  + PK+CR Conversion (D101+D102+Indirect)",
             r2(pk["d101"]+pk["d102"]+pk["indirect"]), "", "", "", ""],
            ["1300", month_name, "  - PK+CR Scrap Recovery",
             -pk["scrap"], "", "", "", ""],
            ["1300", month_name, "= CRC Cost (Semi-FG)",
             crc_cost, pk["gr_qty_kg"], per_kg(crc_cost, pk["gr_qty_kg"]), "", ""],
            ["1300", month_name, "  + GI Input (Zinc + other mat)",
             gi["mat_input"], "", "", "", ""],
            ["1300", month_name, "  + GI Conversion (D101+D102+Indirect)",
             r2(gi["d101"]+gi["d102"]+gi["indirect"]), "", "", "", ""],
            ["1300", month_name, "  - GI Scrap Recovery (Dross/Slag/Grade B-C)",
             -gi["scrap"], "", "", "", ""],
            ["1300", month_name, "= GIC Cost (Finished GI Coil)",
             gic_cost, gi["gr_qty_kg"], per_kg(gic_cost, gi["gr_qty_kg"]), "", ""],
            ["1300", month_name, "", "", "", "", "", ""],
        ]

        # ── Plant 1100 / 1200 ────────────────────
        for plant in ["1100", "1200"]:
            df = load_prd(plant, month)

            slit = layer_summary(df[df["_cat"] == "SLIT"])
            pipe = layer_summary(df[df["_cat"] == "PIPE"])
            cch  = layer_summary(df[df["_cat"] == "C_CHANNEL"])

            slit_net = net_cost(slit)
            pipe_net = r2(pipe["mat_input"] + pipe["d101"] + pipe["d102"] + pipe["indirect"] - pipe["scrap"])
            cch_net  = r2(cch["mat_input"]  + cch["d101"]  + cch["d102"]  + cch["indirect"]  - cch["scrap"])

            rows += [
                [plant, month_name, "── Input: HRC / GIC Material (for Slitting)",
                 slit["mat_input"], "", "", "", ""],
                [plant, month_name, "  + Slit Conversion (D101+D102+Indirect)",
                 r2(slit["d101"]+slit["d102"]+slit["indirect"]), "", "", "", ""],
                [plant, month_name, "  - Slit Scrap Recovery",
                 -slit["scrap"], "", "", "", ""],
                [plant, month_name, "= Slit Coil Cost",
                 slit_net, slit["gr_qty_kg"], per_kg(slit_net, slit["gr_qty_kg"]), "", ""],
                [plant, month_name, "  + Slit Coil Input to Pipe (at MAP)",
                 pipe["mat_input"], "", "", "", ""],
                [plant, month_name, "  + Pipe Conversion (D101+D102+Indirect)",
                 r2(pipe["d101"]+pipe["d102"]+pipe["indirect"]), "", "", "", ""],
                [plant, month_name, "  - Pipe Scrap Recovery",
                 -pipe["scrap"], "", "", "", ""],
                [plant, month_name, "= Pipe Cost (Finished)",
                 pipe_net, pipe["gr_qty_kg"], per_kg(pipe_net, pipe["gr_qty_kg"]), "", ""],
            ]

            if cch["rows"] > 0:
                rows += [
                    [plant, month_name, "  + C-Channel Input (at MAP)",
                     cch["mat_input"], "", "", "", ""],
                    [plant, month_name, "  + C-Channel Conversion",
                     r2(cch["d101"]+cch["d102"]+cch["indirect"]), "", "", "", ""],
                    [plant, month_name, "  - C-Channel Scrap",
                     -cch["scrap"], "", "", "", ""],
                    [plant, month_name, "= C-Channel Cost (Finished)",
                     cch_net, cch["gr_qty_kg"], per_kg(cch_net, cch["gr_qty_kg"]), "", ""],
                ]

            rows.append([plant, month_name, "", "", "", "", "", ""])

    cols = ["Plant", "Month", "Layer", "Amount (THB)", "Output QTY (kg)", "THB/kg",
            "Notes", "Ref"]
    return pd.DataFrame(rows, columns=cols)

# ──────────────────────────────────────────────
# BUILD DETAIL BREAKDOWN (per GL category)
# ──────────────────────────────────────────────
def build_detail(plant):
    """Build per-month cost component breakdown for a plant."""
    rows = []

    if plant == "1300":
        cats = [("PK_CR", "Pickling & Cold Rolling"), ("GI", "Galvanizing")]
    else:
        cats = [("SLIT", "Slitting"), ("PIPE", "Pipe Forming"), ("C_CHANNEL", "C-Channel Forming")]

    for month in MONTHS:
        month_name = ["", "Jan", "Feb", "Mar"][month]
        df = load_prd(plant, month)

        for cat, cat_label in cats:
            sub = df[df["_cat"] == cat]
            if len(sub) == 0:
                continue

            s = layer_summary(sub)
            total_conv = r2(s["d101"] + s["d102"] + s["indirect"])

            rows += [
                [month_name, cat_label, "GR Output QTY (kg)", "", s["gr_qty_kg"], ""],
                [month_name, cat_label, "GR Output Amount (THB)", s["gr_amount"], "", ""],
                [month_name, cat_label, "── Material Input", s["mat_input"], "",
                 per_kg(s["mat_input"], s["gr_qty_kg"])],
                [month_name, cat_label, "  D101 Direct Machine", s["d101"], "",
                 per_kg(s["d101"], s["gr_qty_kg"])],
                [month_name, cat_label, "  D102 Direct Labour", s["d102"], "",
                 per_kg(s["d102"], s["gr_qty_kg"])],
                [month_name, cat_label, "  Indirect (I101-I111)", s["indirect"], "",
                 per_kg(s["indirect"], s["gr_qty_kg"])],
                [month_name, cat_label, "  Total Conversion", total_conv, "",
                 per_kg(total_conv, s["gr_qty_kg"])],
                [month_name, cat_label, "  (–) Scrap Recovery", -s["scrap"], "",
                 per_kg(-s["scrap"], s["gr_qty_kg"])],
                [month_name, cat_label, "= Net Cost", net_cost(s), "",
                 per_kg(net_cost(s), s["gr_qty_kg"])],
                [month_name, cat_label, "", "", "", ""],
            ]

    cols = ["Month", "Process", "Item", "Amount (THB)", "QTY (kg)", "THB/kg"]
    return pd.DataFrame(rows, columns=cols)

# ──────────────────────────────────────────────
# BUILD RAW PRD (all plants, all months)
# ──────────────────────────────────────────────
def build_raw_prd():
    frames = []
    for plant in PLANTS:
        for month in MONTHS:
            df = load_prd(plant, month)
            keep = [
                "_plant", "_month", "_cat",
                "Order Type Name", "Work Center", "Work Center Description",
                "Order", "Combined Order", "Combined Order Status", "Original Order Status",
                "Material", "Description (EN)",
                "Actual GI QTY", "Actual GI Amount",
                "Actual GR QTY", "Actual GR Amount",
                "Actual D101 Amount", "Actual D102 Amount",
                "_I_total", "_scrap_total",
            ]
            keep = [c for c in keep if c in df.columns]
            frames.append(df[keep])
    all_df = pd.concat(frames, ignore_index=True)
    all_df = all_df.rename(columns={"_plant":"Plant","_month":"Month","_cat":"Category"})
    return all_df

# ──────────────────────────────────────────────
# WRITE TO GOOGLE SHEET
# ──────────────────────────────────────────────
def write_sheet(gc, summary_df, detail_1300, detail_1100, detail_1200, raw_df):
    import gspread

    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    print(f"Creating Google Sheet: {SHEET_NAME}...")
    try:
        sh = gc.open(SHEET_NAME)
        print("  (sheet exists, clearing)")
    except gspread.SpreadsheetNotFound:
        sh = gc.create(SHEET_NAME)
        sh.share("surasit.ksw11@gmail.com", perm_type="user", role="writer", notify=False)
        print("  (new sheet created)")

    def write_tab(sh, title, df, note=""):
        try:
            ws = sh.worksheet(title)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=title, rows=max(len(df)+20, 100), cols=max(len(df.columns)+5, 20))

        # Header note
        meta_row = [f"Prepared by: Claude Code | {now} | {note}"]
        ws.update(values=[meta_row], range_name="A1")

        # Data
        data = [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()
        ws.update(values=data, range_name="A2")
        print(f"  OK Tab '{title}': {len(df)} rows")
        return ws

    # Delete default Sheet1 if present and we have other sheets
    tabs_to_write = [
        ("Summary",      summary_df,   "Cost Build-Up Waterfall per Plant per Month"),
        ("Detail_1300",  detail_1300,  "Plant 1300 GI — Layer cost breakdown"),
        ("Detail_1100",  detail_1100,  "Plant 1100 Pipe — Slit+Pipe+C-Channel breakdown"),
        ("Detail_1200",  detail_1200,  "Plant 1200 Pipe — Slit+Pipe+C-Channel breakdown"),
        ("Raw_PRD",      raw_df,       "All PRD data — 3 plants × 3 months"),
    ]

    for title, df, note in tabs_to_write:
        write_tab(sh, title, df, note)

    # Remove default sheet if it's the only remaining one
    try:
        ws_default = sh.worksheet("Sheet1")
        if len(sh.worksheets()) > 1:
            sh.del_worksheet(ws_default)
    except:
        pass

    url = f"https://docs.google.com/spreadsheets/d/{sh.id}"
    print(f"\nSheet URL: {url}")
    return url

# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("Cost Build-Up Report — Q1 2026")
    print("=" * 60)

    print("\n[1/5] Building Summary (waterfall)...")
    summary_df = build_summary()
    print(f"  {len(summary_df)} rows")

    print("[2/5] Building Plant 1300 detail...")
    detail_1300 = build_detail("1300")

    print("[3/5] Building Plant 1100 detail...")
    detail_1100 = build_detail("1100")

    print("[4/5] Building Plant 1200 detail...")
    detail_1200 = build_detail("1200")

    print("[5/5] Building Raw PRD (all plants)...")
    raw_df = build_raw_prd()
    print(f"  {len(raw_df)} rows total")

    print("\nConnecting to Google Sheets...")
    gc = get_gspread_client()

    url = write_sheet(gc, summary_df, detail_1300, detail_1100, detail_1200, raw_df)

    print(f"\n{'='*60}")
    print(f"DONE — Cost Build-Up Report Q1 2026")
    print(f"URL: {url}")
    print(f"{'='*60}")
