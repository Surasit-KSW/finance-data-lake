"""
AMC Electricity Workbook v2 — Full Redesign
Plants 1100 / 1200 / 1300  |  เมษายน 2026

Tabs created/updated in Google Sheet:
  PRD_1100 | PRD_1200 | PRD_1300 | STC | A1 | A2+SCG | Goblex | 04.2026

Usage:
    python scripts/electricity_alloc_amc_v2.py
    python scripts/electricity_alloc_amc_v2.py --dry-run
"""
from __future__ import annotations
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from utils import get_gspread_client, open_or_create_sheet, get_or_add_worksheet, append_analytics_log
from config.settings import DRIVE_FOLDERS, ANALYTICS_LOG_SHEET_ID

# ─────────────────────────── CONFIG ────────────────────────────────────────

SHEET_ID      = "18OPPQLLmrVyyLlPGhKclEzSDleDRBC7DaQcJ4QluCHU"
BASE          = Path(__file__).parent.parent.parent / "01_Bronze_Raw"
KS13_PATH     = BASE / "Master" / "KS13_Master.XLSX"
PRD_PATHS     = {
    1100: BASE / "PRD_GI" / "PRD_1100_04.2026.XLSX",
    1200: BASE / "PRD_GI" / "PRD_1200_04.2026.XLSX",
    1300: BASE / "PRD_GI" / "PRD_1300_04.2026.XLSX",
}
COMBINED_WC_MAP = {"CR01, PK01": ["CR01", "PK01"]}

MONTH_LABEL   = "04.2026"
MONTH_DISPLAY = "เมษายน 2026"
SHEET_NAME    = "ปันส่วนค่าไฟฟ้า AMC 2026"

GL_ELEC      = "5611010"
GL_INPUT_TAX = "1540101"
GL_AP_TRADE  = "2110101"

# ── Row constants for cross-tab references in 04.2026 summary ──────────────
A1_BILL_EXCL_ROW   = 5   # B5 in A1 tab = excl VAT (input)
A1_BILL_VAT_ROW    = 6   # B6 = VAT (formula)
A1_BILL_TOTAL_ROW  = 7   # B7 = total incl VAT (formula)

A2SCG_COMB_EXCL_ROW  = 13   # B13 = combined excl VAT
A2SCG_COMB_VAT_ROW   = 14   # B14 = combined VAT
A2SCG_COMB_TOTAL_ROW = 15   # B15 = combined total
A2SCG_1300_PCT_ROW   = 22   # B22 = % for Plant 1300 (manual input)
A2SCG_1300_AMT_ROW   = 23   # B23 = Plant 1300 amount excl VAT

GOBLEX_COMB_EXCL_ROW  = 13
GOBLEX_COMB_VAT_ROW   = 14
GOBLEX_COMB_TOTAL_ROW = 15
GOBLEX_1300_PCT_ROW   = 22
GOBLEX_1300_AMT_ROW   = 23

# ─────────────────────────── MACHINE DEFINITIONS ───────────────────────────

PLANT_1100_MACHINES = [
    # CC codes from KS13_Master.XLSX — Category L, 118xxx range
    {"pk":  1, "name": "SL02 — Slitter Line 02",      "wc": ["SL02"], "cc": "1187101", "gl": GL_ELEC, "plant": 1100},
    {"pk":  2, "name": "SL03 — Slitter Line 03",      "wc": ["SL03"], "cc": "1187102", "gl": GL_ELEC, "plant": 1100},
    {"pk":  3, "name": "SL09 — Mini Slitter 09",      "wc": ["SL09"], "cc": "1187104", "gl": GL_ELEC, "plant": 1100},
    {"pk":  4, "name": "PL01 — Pipe Line 01",         "wc": ["PL01"], "cc": "1187201", "gl": GL_ELEC, "plant": 1100},
    {"pk":  5, "name": "PL08 — Pipe Line 08",         "wc": ["PL08"], "cc": "1187202", "gl": GL_ELEC, "plant": 1100},
    {"pk":  6, "name": "PL12 — Pipe Line 12",         "wc": ["PL12"], "cc": "1187203", "gl": GL_ELEC, "plant": 1100},
    {"pk":  7, "name": "PL17 — Pipe Line 17",         "wc": ["PL17"], "cc": "1187204", "gl": GL_ELEC, "plant": 1100},
    {"pk":  8, "name": "PL18 — Pipe Line 18",         "wc": ["PL18"], "cc": "1187205", "gl": GL_ELEC, "plant": 1100},
    {"pk":  9, "name": "FF01 — Fur Pipe Line 01",     "wc": ["FF01"], "cc": "1187601", "gl": GL_ELEC, "plant": 1100},
    {"pk": 10, "name": "FF02 — Fur Pipe Line 02",     "wc": ["FF02"], "cc": "1187602", "gl": GL_ELEC, "plant": 1100},
    {"pk": 11, "name": "RW01 — Rework A1",            "wc": ["RW01"], "cc": "1187501", "gl": GL_ELEC, "plant": 1100},
    {"pk": 12, "name": "CP01 — Clip Pressing 01",     "wc": ["CP01"], "cc": "1187401", "gl": GL_ELEC, "plant": 1100},
]

PLANT_1200_MACHINES = [
    # CC codes from KS13_Master.XLSX — Category L, 128xxx range
    {"pk": 13, "name": "SL06 — Slitter Line 06",      "wc": ["SL06"], "cc": "1287102", "gl": GL_ELEC, "plant": 1200},
    {"pk": 14, "name": "SL10 — Mini Slitter 10",      "wc": ["SL10"], "cc": "1287103", "gl": GL_ELEC, "plant": 1200},
    {"pk": 15, "name": "SL11 — Mini Slitter 11",      "wc": ["SL11"], "cc": "1287104", "gl": GL_ELEC, "plant": 1200},
    {"pk": 16, "name": "PL02 — Pipe Line 02",         "wc": ["PL02"], "cc": "1287301", "gl": GL_ELEC, "plant": 1200},
    {"pk": 17, "name": "PL03 — Pipe Line 03",         "wc": ["PL03"], "cc": "1287302", "gl": GL_ELEC, "plant": 1200},
    {"pk": 18, "name": "PL06 — Pipe Line 06",         "wc": ["PL06"], "cc": "1287304", "gl": GL_ELEC, "plant": 1200},
    {"pk": 19, "name": "PL07 — Pipe Line 07",         "wc": ["PL07"], "cc": "1287305", "gl": GL_ELEC, "plant": 1200},
    {"pk": 20, "name": "PL10 — Pipe Line 10",         "wc": ["PL10"], "cc": "1287306", "gl": GL_ELEC, "plant": 1200},
    {"pk": 21, "name": "PL13 — Pipe Line 13",         "wc": ["PL13"], "cc": "1287201", "gl": GL_ELEC, "plant": 1200},
    {"pk": 22, "name": "PL15 — Pipe Line 15",         "wc": ["PL15"], "cc": "1287203", "gl": GL_ELEC, "plant": 1200},
    {"pk": 23, "name": "PL19 — Pipe Line 19",         "wc": ["PL19"], "cc": "1287307", "gl": GL_ELEC, "plant": 1200},
    {"pk": 24, "name": "PL20 — Pipe Line 20",         "wc": ["PL20"], "cc": "1287308", "gl": GL_ELEC, "plant": 1200},
    {"pk": 25, "name": "CC02 — C-Channel Line 02",    "wc": ["CC02"], "cc": "1287601", "gl": GL_ELEC, "plant": 1200},
    {"pk": 26, "name": "CC03 — C-Channel Line 03",    "wc": ["CC03"], "cc": "1287602", "gl": GL_ELEC, "plant": 1200},
    {"pk": 27, "name": "CC09 — C-Channel Line 09",    "wc": ["CC09"], "cc": "1287604", "gl": GL_ELEC, "plant": 1200},
]

PLANT_1300_MACHINES = [
    # CC codes from KS13_Master.XLSX — Category L, 138xxx range
    {"pk": 28, "name": "GL01 — Galvanizing Line 01",  "wc": ["GL01"], "cc": "1387210", "gl": GL_ELEC, "plant": 1300},
    {"pk": 29, "name": "CR01 — Cold Rolling Mill 01", "wc": ["CR01"], "cc": "1387120", "gl": GL_ELEC, "plant": 1300},
    {"pk": 30, "name": "PK01 — Pickling Line 01",     "wc": ["PK01"], "cc": "1387110", "gl": GL_ELEC, "plant": 1300},
    {"pk": 31, "name": "SL12 — Mini Slitter 12",      "wc": ["SL12"], "cc": "1387301", "gl": GL_ELEC, "plant": 1300},
]

ALL_MACHINES = PLANT_1100_MACHINES + PLANT_1200_MACHINES + PLANT_1300_MACHINES


# ─────────────────────────── FORMATTING HELPERS ─────────────────────────────

def _rgb(hex_color: str) -> dict:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return {"red": round(r/255, 4), "green": round(g/255, 4), "blue": round(b/255, 4)}

C_NAVY    = "#1F3864"; C_BLUE   = "#2F5496"; C_LBLUE  = "#D9E1F2"
C_WHITE   = "#FFFFFF"; C_BLACK  = "#000000"; C_DARK   = "#1F3864"
C_ALTROW  = "#F0F4FB"; C_YELLOW = "#FFF2CC"; C_GREEN_BG = "#E2EFDA"
C_GREEN_FG= "#375623"; C_RED_BG = "#FFE2E2"; C_RED_FG = "#9C0006"
C_INFO_BG = "#DEEBF7"; C_JE_DR  = "#EBF3FB"; C_JE_CR  = "#FDE9D9"
C_MOCK_BG = "#FFF9C4"; C_MOCK_FG= "#7D6608"
C_P1100H  = "#4CAF50"; C_P1200H = "#1E88E5"; C_P1300H = "#FF7043"
C_P1100   = "#E8F4E8"; C_P1200  = "#E8EFF8"; C_P1300  = "#F8EDE8"
C_P1100A  = "#D7EED7"; C_P1200A = "#D7E6F5"; C_P1300A = "#F5DDD7"
PLANT_HC  = {1100: C_P1100H, 1200: C_P1200H, 1300: C_P1300H}
PLANT_RC  = {1100: (C_P1100, C_P1100A), 1200: (C_P1200, C_P1200A), 1300: (C_P1300, C_P1300A)}

NF_THB = {"type": "NUMBER", "pattern": "#,##0.00"}
NF_KG  = {"type": "NUMBER", "pattern": "#,##0"}
NF_PCT = {"type": "NUMBER", "pattern": "0.0000%"}
NF_PCT2= {"type": "NUMBER", "pattern": "0.00%"}


def _cell_format(*, bold=False, italic=False, font_size=10, fg=C_BLACK,
                 bg=None, halign=None, valign=None, wrap=False,
                 number_format=None, borders=None) -> dict:
    fmt = {
        "textFormat": {"bold": bold, "italic": italic, "fontSize": font_size,
                       "foregroundColor": _rgb(fg)},
        "wrapStrategy": "WRAP" if wrap else "OVERFLOW_CELL",
    }
    if bg:             fmt["backgroundColor"]     = _rgb(bg)
    if halign:         fmt["horizontalAlignment"] = halign
    if valign:         fmt["verticalAlignment"]   = valign
    if number_format:  fmt["numberFormat"]        = number_format
    if borders:        fmt["borders"]             = borders
    return fmt


def _solid_border(color_hex="#BFBFBF", width=1):
    return {"style": "SOLID", "width": width, "color": _rgb(color_hex)}


def _sheet_id(ws):
    return ws._properties["sheetId"]


def _col_w(ws, col: int, px: int) -> dict:
    return {"updateDimensionProperties": {
        "range": {"sheetId": _sheet_id(ws), "dimension": "COLUMNS",
                  "startIndex": col, "endIndex": col+1},
        "properties": {"pixelSize": px}, "fields": "pixelSize"}}


def _row_h(ws, row: int, px: int) -> dict:
    return {"updateDimensionProperties": {
        "range": {"sheetId": _sheet_id(ws), "dimension": "ROWS",
                  "startIndex": row, "endIndex": row+1},
        "properties": {"pixelSize": px}, "fields": "pixelSize"}}


def _freeze(ws, rows=0, cols=0) -> dict:
    return {"updateSheetProperties": {
        "properties": {"sheetId": _sheet_id(ws),
                       "gridProperties": {"frozenRowCount": rows, "frozenColumnCount": cols}},
        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}}


def _merge(ws, r1, c1, r2, c2) -> dict:
    return {"mergeCells": {
        "range": {"sheetId": _sheet_id(ws),
                  "startRowIndex": r1, "endRowIndex": r2,
                  "startColumnIndex": c1, "endColumnIndex": c2},
        "mergeType": "MERGE_ALL"}}


def _unmerge_all(ws) -> dict:
    """Unmerge all cells in the sheet (to clear old merged formatting before rewriting)."""
    return {"unmergeCells": {
        "range": {"sheetId": _sheet_id(ws),
                  "startRowIndex": 0, "endRowIndex": 500,
                  "startColumnIndex": 0, "endColumnIndex": 20}}}


def _cond_fmt(ws, r1, c1, r2, c2, formula, bg, fg) -> dict:
    return {"addConditionalFormatRule": {
        "rule": {
            "ranges": [{"sheetId": _sheet_id(ws),
                        "startRowIndex": r1, "endRowIndex": r2,
                        "startColumnIndex": c1, "endColumnIndex": c2}],
            "booleanRule": {
                "condition": {"type": "CUSTOM_FORMULA",
                              "values": [{"userEnteredValue": formula}]},
                "format": {"backgroundColor": _rgb(bg),
                           "textFormat": {"foregroundColor": _rgb(fg), "bold": True}},
            }},
        "index": 0}}


def _af_req(rng: str, **kw) -> dict:
    return {"range": rng, "format": _cell_format(**kw)}


# ─────────────────────────── DATA LOADING ──────────────────────────────────

def load_ks13(path: Path) -> dict[str, str]:
    """Load KS13 master → {cc_code: cc_name}"""
    if not path.exists():
        print(f"  WARNING: KS13 not found at {path} — CC names will be blank")
        return {}
    df = pd.read_excel(str(path), sheet_name="Sheet1", header=0)
    df["Cost Center"] = df["Cost Center"].astype(str).str.strip()
    df["Name"] = df["Name"].astype(str).str.strip()
    result = {row["Cost Center"]: row["Name"]
              for _, row in df.iterrows()
              if row["Cost Center"] not in ("nan", "", "None")}
    print(f"  KS13: {len(result)} cost centers loaded")
    return result


def load_prd(plant: int, path: Path, machines: list[dict]) -> tuple[pd.DataFrame, dict[str, float]]:
    """
    Load PRD Excel for a plant.
    Returns (df_raw_key_cols, wc_totals {wc_code: gr_qty_kg})
    Combined WCs are expanded per COMBINED_WC_MAP.
    WCs not in machine definitions are skipped with a warning.
    """
    if not path.exists():
        raise FileNotFoundError(f"PRD not found: {path}")
    df = pd.read_excel(str(path), sheet_name="Sheet1", header=0)

    for col in ("Work Center", "Actual GR QTY"):
        if col not in df.columns:
            raise ValueError(f"PRD Plant {plant}: missing column '{col}'")

    df["Actual GR QTY"] = pd.to_numeric(df["Actual GR QTY"], errors="coerce").fillna(0)
    df["Work Center"]   = df["Work Center"].astype(str).str.strip()

    BYPRODUCT_COLS = [
        "Actual ByProduct Scrap QTY",
        "Actual ByProduct Grade B QTY",
        "Actual ByProduct Grade C QTY",
    ]
    for col in BYPRODUCT_COLS:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["_total_qty"] = df["Actual GR QTY"] + df[BYPRODUCT_COLS].sum(axis=1)

    machine_wcs: set[str] = {wc for m in machines for wc in m["wc"]}
    wc_totals:   dict[str, float] = {}
    unknown_wcs: set[str] = set()

    for _, row in df.iterrows():
        wc_raw = str(row["Work Center"]).strip()
        qty    = float(row["_total_qty"])
        if qty <= 0:
            continue
        if wc_raw in COMBINED_WC_MAP:
            for wc in COMBINED_WC_MAP[wc_raw]:
                if wc in machine_wcs:
                    wc_totals[wc] = wc_totals.get(wc, 0.0) + qty
        elif wc_raw in machine_wcs:
            wc_totals[wc_raw] = wc_totals.get(wc_raw, 0.0) + qty
        else:
            unknown_wcs.add(wc_raw)

    if unknown_wcs:
        print(f"  Plant {plant}: PRD WCs not in machine list (skipped): {sorted(unknown_wcs)}")

    key_cols = ["Work Center", "Order", "Material", "Description (EN)",
                "Actual GR QTY", "Actual ByProduct Scrap QTY",
                "Actual ByProduct Grade B QTY", "Actual ByProduct Grade C QTY",
                "Actual GR Unit", "Status"]
    avail    = [c for c in key_cols if c in df.columns]
    df_raw   = df[df["_total_qty"] > 0][avail].reset_index(drop=True)

    total = sum(wc_totals.values())
    print(f"  Plant {plant}: {len(wc_totals)} WCs | total Qty = {total:,.0f} kg | {len(df_raw)} raw rows")
    return df_raw, wc_totals


def validate_ccs(machines: list[dict], ks13: dict[str, str]) -> None:
    if not ks13:
        return
    missing = [m for m in machines if m["cc"] not in ks13]
    if missing:
        print(f"  WARNING: {len(missing)} CC codes not found in KS13:")
        for m in missing:
            print(f"    {m['cc']} ({m['name']})")
    else:
        print(f"  All {len(machines)} CC codes validated in KS13.")


def _last_nonzero_idx(machines: list[dict], wc_totals: dict[str, float]) -> int:
    """Index (0-based in list) of the last machine with GR Qty > 0."""
    idx = -1
    for i, m in enumerate(machines):
        if any(wc_totals.get(wc, 0) > 0 for wc in m["wc"]):
            idx = i
    return idx


# ─────────────────────────── PRD TAB WRITER ────────────────────────────────

def write_prd_tab(ws, sh, plant: int, df_raw: pd.DataFrame, wc_totals: dict[str, float],
                  machines: list[dict], ks13: dict[str, str], source_path: str, timestamp: str) -> None:
    ws.clear()

    wc_to_cc = {wc: m["cc"] for m in machines for wc in m["wc"]}
    total_qty = sum(wc_totals.values())
    plant_hdr_col = {1100: C_P1100H, 1200: C_P1200H, 1300: C_P1300H}[plant]

    # Reverse-lookup: wc → combined-key labels that include it (e.g. "CR01" → ["CR01, PK01"])
    combined_addons: dict[str, list[str]] = {}
    for combined_key, parts in COMBINED_WC_MAP.items():
        for part in parts:
            combined_addons.setdefault(part, []).append(combined_key)

    # Pre-compute row constants (all 1-indexed)
    WC_HDR_ROW    = 5
    n_wc_rows     = sum(len(m["wc"]) for m in machines)
    D_WC_S        = WC_HDR_ROW + 1                # first WC data row
    D_WC_E        = WC_HDR_ROW + n_wc_rows        # last WC data row
    TOTAL_ROW_NUM = D_WC_E + 1
    RAW_HDR_ROW   = TOTAL_ROW_NUM + 2             # "Raw Data" section title
    RAW_DATA_START = RAW_HDR_ROW + 2              # actual data rows (after title + col-header)

    # SUMIFS formula for a WC row — references column A of the same row as criteria
    # so renaming WC in col A auto-updates. Appends extra term for each combined-WC key.
    def _gr_formula(wc: str, r: int) -> str:
        # Sum GR QTY + ByProduct Scrap + Grade B + Grade C (cols E,F,G,H in raw data)
        rng_a    = f"$A${RAW_DATA_START}:$A$9999"
        criteria = [f"A{r}"] + [f'"{key}"' for key in combined_addons.get(wc, [])]
        parts    = [
            f"SUMIFS(${c}${RAW_DATA_START}:${c}$9999,{rng_a},{crit})"
            for c in ("E", "F", "G", "H") for crit in criteria
        ]
        return "=" + "+".join(parts)

    # --- Build rows ---
    rows: list[list] = [
        [f"PRD Report — Plant {plant}  |  {MONTH_DISPLAY}"],             # row 1
        [f"Source: {source_path}", "", "", "Loaded:", timestamp],         # row 2
        [],                                                                # row 3
        ["WC Summary — GR Qty by Work Center (Allocation Basis)"],        # row 4
        ["Work Center", "Cost Center", "CC Name", "Total Qty (kg)", "% of Plant"],  # row 5
    ]

    for m in machines:
        for wc in m["wc"]:
            r       = len(rows) + 1   # 1-indexed (rows has 5 entries → first machine = row 6)
            cc      = m["cc"]
            cc_name = ks13.get(cc, "—")
            rows.append([wc, cc, cc_name, _gr_formula(wc, r), f"=IFERROR(D{r}/D{TOTAL_ROW_NUM},0)"])

    rows.append(["Total", "", "",
                 f"=SUM(D{D_WC_S}:D{D_WC_E})",
                 f"=IF(D{TOTAL_ROW_NUM}>0,1,0)"])
    rows.append([])

    RAW_HDR_ROW = TOTAL_ROW_NUM + 2
    rows.append([f"Raw Data — PRD Plant {plant}  (rows with Total Qty > 0)"])
    if not df_raw.empty:
        rows.append(list(df_raw.columns))
        for _, row in df_raw.iterrows():
            rows.append([None if pd.isna(v) else v for v in row.values])
    else:
        rows.append(["No data"])

    ws.append_rows(rows, value_input_option="USER_ENTERED")

    # --- Structural requests ---
    sid = _sheet_id(ws)
    n_cols = 5
    struct = [
        _freeze(ws, rows=WC_HDR_ROW, cols=0),
        _merge(ws, 0, 0, 1, n_cols),                         # title
        _merge(ws, 3, 0, 4, n_cols),                         # "WC Summary" header
        _merge(ws, RAW_HDR_ROW-1, 0, RAW_HDR_ROW, n_cols),  # "Raw Data" header
        _row_h(ws, 0, 32),
        _row_h(ws, 3, 26),
        _row_h(ws, WC_HDR_ROW-1, 22),
        _row_h(ws, RAW_HDR_ROW-1, 26),
    ] + [_col_w(ws, i, w) for i, w in enumerate([100, 100, 200, 120, 80])]
    sh.batch_update({"requests": [_unmerge_all(ws)] + struct})

    # --- Cell formatting ---
    fmt = [
        _af_req(f"A1", bold=True, font_size=12, fg=C_WHITE, bg=plant_hdr_col, halign="LEFT"),
        _af_req(f"A4", bold=True, font_size=10, fg=C_WHITE, bg=C_NAVY),
        _af_req(f"A{WC_HDR_ROW}:E{WC_HDR_ROW}", bold=True, fg=C_DARK, bg=C_LBLUE, halign="CENTER"),
    ]
    for i in range(n_wc_rows):
        r = WC_HDR_ROW + 1 + i
        bg = C_ALTROW if i % 2 == 1 else C_WHITE
        fmt += [
            _af_req(f"A{r}:E{r}", fg=C_BLACK, bg=bg),
            _af_req(f"D{r}", number_format=NF_KG, halign="RIGHT", bg=bg),
            _af_req(f"E{r}", number_format=NF_PCT2, halign="RIGHT", bg=bg),
        ]
    fmt += [
        _af_req(f"A{TOTAL_ROW_NUM}:E{TOTAL_ROW_NUM}", bold=True, bg=C_LBLUE,
                borders={"top": _solid_border(C_BLUE, 2)}),
        _af_req(f"D{TOTAL_ROW_NUM}", number_format=NF_KG, halign="RIGHT", bold=True, bg=C_LBLUE),
        _af_req(f"E{TOTAL_ROW_NUM}", number_format=NF_PCT2, halign="RIGHT", bold=True, bg=C_LBLUE),
        _af_req(f"A{RAW_HDR_ROW}", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
    ]
    ws.batch_format(fmt)


# ─────────────────────────── STC TAB ───────────────────────────────────────

def write_stc_tab(ws, sh, timestamp: str) -> None:
    ws.clear()
    rows = [
        ["ค่าไฟฟ้า STC — 04.2026"],                                    # row 1
        [],                                                               # row 2
        ["NOTE:", "AMC ไม่ได้เช่า STC แล้ว — ยอดรอบนี้ = 0 บาท"],  # row 3
        [],                                                               # row 4
        ["Bill Ref",   "STC 04.26"],                                     # row 5
        ["Amount",     0.00],                                             # row 6
        ["Status",     "INACTIVE — ไม่มีบิล"],                           # row 7
        [],                                                               # row 8
        ["Prepared by", "Claude Code"],                                   # row 9
        ["Timestamp",   timestamp],                                       # row 10
    ]
    ws.append_rows(rows, value_input_option="USER_ENTERED")

    struct = [
        _merge(ws, 0, 0, 1, 6),
        _merge(ws, 2, 1, 3, 6),
        _row_h(ws, 0, 32),
        _row_h(ws, 2, 28),
    ] + [_col_w(ws, i, w) for i, w in enumerate([120, 300, 0, 0, 0, 0])]
    sh.batch_update({"requests": [_unmerge_all(ws)] + struct})

    fmt = [
        _af_req("A1", bold=True, font_size=12, fg=C_WHITE, bg=C_NAVY),
        _af_req("A3:F3", bold=True, italic=True, fg=C_MOCK_FG, bg=C_MOCK_BG),
        _af_req("A5", bold=True), _af_req("A6", bold=True), _af_req("A7", bold=True),
        _af_req("B6", number_format=NF_THB),
        _af_req("B7", bold=True, fg=C_RED_FG),
    ]
    ws.batch_format(fmt)


# ─────────────────────────── A1 TAB ────────────────────────────────────────

def write_a1_tab(ws, sh, wc_totals_1100: dict[str, float], ks13: dict[str, str], timestamp: str) -> None:
    ws.clear()
    machines = PLANT_1100_MACHINES
    total_qty = sum(wc_totals_1100.get(wc, 0.0) for m in machines for wc in m["wc"])

    # Row layout (1-indexed)
    R_TITLE   = 1
    R_SEC_A   = 3
    R_REF     = 4
    R_EXCL    = A1_BILL_EXCL_ROW   # 5  ← input cell
    R_VAT     = A1_BILL_VAT_ROW    # 6
    R_TOTAL   = A1_BILL_TOTAL_ROW  # 7
    R_METER   = 8
    R_PLANT   = 9
    R_PREPBY  = 10
    R_TS      = 11
    R_STATUS  = 12
    # blank 13
    R_SEC_B   = 14
    R_COL_HDR = 15
    R_DATA_S  = 16
    R_DATA_E  = R_DATA_S + len(machines) - 1   # 27
    R_SUB     = R_DATA_E + 1                    # 28
    # blank 29
    R_VAT_ROW = 30
    R_GRAND   = 31
    # blank 32
    R_SEC_C   = 33
    R_HDR_C   = 34
    R_JE_S    = 35

    nonzero_idx = _last_nonzero_idx(machines, wc_totals_1100)

    # Alloc% formula denominator
    denom = f"SUM($D${R_DATA_S}:$D${R_DATA_E})"

    COL_H = ["PK", "Machine Name", "Work Center", "GR Qty (kg)",
             "Alloc %", "Amount Excl.VAT (THB)", "Cost Center", "CC Name",
             "GL Account", "Tax", "Description (JE)"]

    rows: list[list] = [
        [f"ปันส่วนค่าไฟฟ้า A1 — Plant 1100  |  {MONTH_DISPLAY}"],  # 1
        [],                                                             # 2
        ["SECTION A — Bill Information"],                              # 3
        ["Bill Ref",         "A1 04.26"],                             # 4
        ["Amount excl VAT (THB)", 0.00],                              # 5  ← INPUT
        ["VAT 7%",           f"=ROUND(B{R_EXCL}*0.07,2)"],           # 6
        ["Total incl VAT",   f"=B{R_EXCL}+B{R_VAT}"],               # 7
        ["Meter",            "A1"],                                    # 8
        ["Plant",            "1100"],                                  # 9
        ["Prepared by",      "Claude Code"],                           # 10
        ["Timestamp",        timestamp],                               # 11
        ["Status",           "Draft — Pending Review"],                # 12
        [],                                                            # 13
        [f"SECTION B — Machine Allocation by GR Qty (kg)  |  {MONTH_DISPLAY}"],  # 14
        COL_H,                                                         # 15
    ]

    for i, m in enumerate(machines):
        r = R_DATA_S + i
        qty_val = wc_totals_1100.get(m["wc"][0], 0.0)  # Python value for logic
        qty = f"=IFERROR(VLOOKUP(C{r},'PRD_1100'!$A:$D,4,0),0)"  # live formula for cross-check
        cc_name = ks13.get(m["cc"], "—")
        is_last_nonzero = (i == nonzero_idx)

        if qty_val == 0:
            amount_formula = 0
        elif is_last_nonzero:
            amount_formula = f"=ROUND(B{R_EXCL},2)-SUM(F{R_DATA_S}:F{r-1})"
        else:
            amount_formula = f"=IF(D{r}=0,0,ROUND($B${R_EXCL}*E{r},2))"

        alloc_f = f"=IF(D{r}=0,0,D{r}/{denom})"
        rows.append([
            m["pk"], m["name"], m["wc"][0], qty,
            alloc_f, amount_formula,
            m["cc"], cc_name, m["gl"], "V7",
            f"Elec {MONTH_LABEL} {m['name']}",
        ])

    # Subtotal
    rows.append(["", "Subtotal Plant 1100", "",
                 f"=SUM(D{R_DATA_S}:D{R_DATA_E})",
                 f"=SUM(E{R_DATA_S}:E{R_DATA_E})",
                 f"=SUM(F{R_DATA_S}:F{R_DATA_E})",
                 "", "", "", "", ""])
    rows.append([])                                     # blank 29
    # VAT row
    rows.append(["VAT", "Input VAT (Deductible)", "", "", "",
                 f"=B{R_VAT}",
                 "", "", GL_INPUT_TAX, "V7",
                 f"VAT Input Tax {MONTH_LABEL}"])
    # Grand total
    rows.append(["", "GRAND TOTAL", "", "", "",
                 f"=F{R_SUB}+F{R_VAT_ROW}",
                 "", "", GL_AP_TRADE, "",
                 f'=IF(ABS(F{R_GRAND}-B{R_TOTAL})<0.01,"CHECK OK","CHECK FAIL")'])
    rows.append([])                                     # blank 32

    # Section C — JE
    rows.append([f"SECTION C — Journal Entry (SAP FB50)  |  {MONTH_LABEL}"])
    rows.append(["Itm", "D/C", "GL Account", "Cost Center", "Amount (THB)", "Tax Code", "Description"])

    itm = 1
    nonzero_machines = [(i, m) for i, m in enumerate(machines)
                        if any(wc_totals_1100.get(wc, 0) > 0 for wc in m["wc"])]
    for i, m in nonzero_machines:
        src_r = R_DATA_S + i
        rows.append([itm, "Dr", m["gl"], m["cc"],
                     f"=F{src_r}", "V7",
                     f"Elec {MONTH_LABEL} {m['name']}"])
        itm += 1

    R_JE_VAT = R_JE_S + len(nonzero_machines)
    R_JE_CR  = R_JE_VAT + 1
    R_JE_BAL = R_JE_CR + 1

    rows.append([itm,   "Dr", GL_INPUT_TAX, "", f"=B{R_VAT}",   "V7", f"VAT Input Tax {MONTH_LABEL}"])
    rows.append([itm+1, "Cr", GL_AP_TRADE,  "", f"=B{R_TOTAL}", "",   f"AP Elec A1 {MONTH_LABEL}"])
    dr_range = f"E{R_JE_S}:E{R_JE_VAT}"
    rows.append(["", "Balance", "", "",
                 f"=SUM({dr_range})-E{R_JE_CR}", "",
                 f'=IF(ABS(SUM({dr_range})-E{R_JE_CR})<0.01,"BALANCED","ERROR")'])
    rows.append([])

    R_SEC_D = R_JE_BAL + 2
    R_HDR_D = R_SEC_D + 1
    R_VER_1 = R_HDR_D + 1
    R_VER_2 = R_VER_1 + 1
    R_VER_3 = R_VER_2 + 1

    rows.append(["SECTION D — Verification"])
    rows.append(["Check", "Actual", "Expected", "Status"])
    rows += [
        ["Sum Alloc% = 100%",
         f"=TEXT(E{R_SUB},\"0.0000%\")", "100.0000%",
         f'=IF(ABS(E{R_SUB}-1)<0.00001,"PASS","FAIL")'],
        ["Sum Amount = Bill excl VAT",
         f"=TEXT(F{R_SUB},\"#,##0.00\")",
         f"=TEXT(B{R_EXCL},\"#,##0.00\")",
         f'=IF(ABS(F{R_SUB}-B{R_EXCL})<0.01,"PASS","FAIL")'],
        ["Grand Total = Bill incl VAT",
         f"=TEXT(F{R_GRAND},\"#,##0.00\")",
         f"=TEXT(B{R_TOTAL},\"#,##0.00\")",
         f'=IF(ABS(F{R_GRAND}-B{R_TOTAL})<0.01,"PASS","FAIL")'],
    ]

    ws.append_rows(rows, value_input_option="USER_ENTERED")

    # --- Structural ---
    n_cols = 11
    struct = [
        _freeze(ws, rows=R_COL_HDR, cols=0),
        _merge(ws, R_TITLE-1, 0, R_TITLE, n_cols),
        _merge(ws, R_SEC_A-1, 0, R_SEC_A, n_cols),
        _merge(ws, R_SEC_B-1, 0, R_SEC_B, n_cols),
        _merge(ws, R_SEC_C-1, 0, R_SEC_C, 7),
        _merge(ws, R_SEC_D-1, 0, R_SEC_D, n_cols),
        _row_h(ws, R_TITLE-1, 36),
        _row_h(ws, R_SEC_A-1, 26), _row_h(ws, R_SEC_B-1, 26),
        _row_h(ws, R_COL_HDR-1, 24), _row_h(ws, R_SUB-1, 22),
        _row_h(ws, R_GRAND-1, 26), _row_h(ws, R_SEC_C-1, 26),
    ] + [_col_w(ws, i, w) for i, w in enumerate([35, 200, 80, 110, 85, 145, 80, 140, 80, 45, 240])]
    sh.batch_update({"requests": [_unmerge_all(ws)] + struct})

    # --- Formatting ---
    fmt = [
        _af_req(f"A{R_TITLE}", bold=True, font_size=12, fg=C_WHITE, bg=C_NAVY, halign="LEFT"),
        _af_req(f"A{R_SEC_A}", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
        _af_req(f"A{R_SEC_B}", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
        _af_req(f"A{R_SEC_C}", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
        _af_req(f"A{R_SEC_D}", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
        _af_req(f"A{R_COL_HDR}:K{R_COL_HDR}", bold=True, fg=C_DARK, bg=C_LBLUE, halign="CENTER",
                borders={"bottom": _solid_border(C_BLUE, 2)}),
        # Bill labels
        *[_af_req(f"A{r}", bold=True, fg=C_DARK) for r in [R_REF, R_EXCL, R_VAT, R_TOTAL, R_METER, R_PLANT, R_PREPBY, R_TS, R_STATUS]],
        _af_req(f"B{R_EXCL}", number_format=NF_THB, bold=True, font_size=11, fg=C_NAVY, bg=C_YELLOW),
        _af_req(f"B{R_VAT}",  number_format=NF_THB),
        _af_req(f"B{R_TOTAL}",number_format=NF_THB, bold=True),
    ]
    # Machine data rows
    for i, m in enumerate(machines):
        r = R_DATA_S + i
        bg = C_P1100A if i % 2 == 1 else C_P1100
        qty_val = wc_totals_1100.get(m["wc"][0], 0.0)
        row_fg = "#AAAAAA" if qty_val == 0 else C_BLACK
        fmt += [
            _af_req(f"A{r}:K{r}", fg=row_fg, bg=bg),
            _af_req(f"D{r}", number_format=NF_KG,  halign="RIGHT", bg=bg),
            _af_req(f"E{r}", number_format=NF_PCT,  halign="RIGHT", bg=bg),
            _af_req(f"F{r}", number_format=NF_THB,  halign="RIGHT", bold=True, fg=C_DARK, bg=bg),
        ]
    # Subtotal
    fmt += [
        _af_req(f"A{R_SUB}:K{R_SUB}", bold=True, bg=C_LBLUE, fg=C_DARK,
                borders={"top": _solid_border(C_BLUE), "bottom": _solid_border(C_BLUE)}),
        _af_req(f"D{R_SUB}", number_format=NF_KG, halign="RIGHT", bold=True, bg=C_LBLUE),
        _af_req(f"E{R_SUB}", number_format=NF_PCT, halign="RIGHT", bold=True, bg=C_LBLUE),
        _af_req(f"F{R_SUB}", number_format=NF_THB, halign="RIGHT", bold=True, bg=C_LBLUE),
        # VAT + Grand Total
        _af_req(f"A{R_VAT_ROW}:K{R_VAT_ROW}", bg=C_YELLOW, italic=True),
        _af_req(f"F{R_VAT_ROW}", number_format=NF_THB, halign="RIGHT", bg=C_YELLOW),
        _af_req(f"A{R_GRAND}:K{R_GRAND}", bold=True, bg=C_GREEN_BG, fg=C_GREEN_FG,
                borders={"top": _solid_border(C_BLUE, 2), "bottom": _solid_border(C_BLUE, 2)}),
        _af_req(f"F{R_GRAND}", number_format=NF_THB, halign="RIGHT", bold=True, bg=C_GREEN_BG),
        # JE
        _af_req(f"A{R_HDR_C}:G{R_HDR_C}", bold=True, fg=C_DARK, bg=C_LBLUE, halign="CENTER"),
    ]
    for r in range(R_JE_S, R_JE_VAT+1):
        fmt += [_af_req(f"A{r}:G{r}", bg=C_JE_DR),
                _af_req(f"B{r}", bold=True, fg="#2F5496", halign="CENTER", bg=C_JE_DR),
                _af_req(f"E{r}", number_format=NF_THB, halign="RIGHT", bg=C_JE_DR)]
    fmt += [
        _af_req(f"A{R_JE_CR}:G{R_JE_CR}", bg=C_JE_CR),
        _af_req(f"B{R_JE_CR}", bold=True, fg="#9C3600", halign="CENTER", bg=C_JE_CR),
        _af_req(f"E{R_JE_CR}", number_format=NF_THB, halign="RIGHT", bg=C_JE_CR),
        # Verification
        _af_req(f"A{R_HDR_D}:D{R_HDR_D}", bold=True, fg=C_DARK, bg=C_LBLUE, halign="CENTER"),
    ]
    for r in [R_VER_1, R_VER_2, R_VER_3]:
        fmt.append(_af_req(f"D{r}", halign="CENTER", bold=True))
    ws.batch_format(fmt)

    cond = []
    for r in [R_VER_1, R_VER_2, R_VER_3]:
        cond += [
            _cond_fmt(ws, r-1, 3, r, 4, f'=$D${r}="PASS"', C_GREEN_BG, C_GREEN_FG),
            _cond_fmt(ws, r-1, 3, r, 4, f'=$D${r}="FAIL"', C_RED_BG, C_RED_FG),
        ]
    cond += [
        _cond_fmt(ws, R_GRAND-1, 10, R_GRAND, 11, f'=$K${R_GRAND}="CHECK OK"', C_GREEN_BG, C_GREEN_FG),
        _cond_fmt(ws, R_GRAND-1, 10, R_GRAND, 11, f'=$K${R_GRAND}="CHECK FAIL"', C_RED_BG, C_RED_FG),
    ]
    sh.batch_update({"requests": cond})


# ─────────────────────────── SHARED BILL TAB (A2+SCG / Goblex) ─────────────

def _write_dual_bill_tab(ws, sh, tab_label: str, plant_label: str,
                         bill1_label: str, bill2_label: str,
                         wc_totals_1200: dict[str, float],
                         wc_totals_1300: dict[str, float],
                         ks13: dict[str, str], timestamp: str,
                         # Row constants (returned by function as well)
                         comb_excl_row: int, pct_1300_row: int, amt_1300_row: int) -> None:
    """
    Shared writer for A2+SCG and Goblex tabs.
    Layout is identical; only labels differ.
    """
    ws.clear()
    machines_1300 = PLANT_1300_MACHINES
    machines_1200 = PLANT_1200_MACHINES

    # ── Row layout ──────────────────────────────────────────────────────────
    R_TITLE = 1
    R_SEC_A = 3
    # Bill 1
    R_B1_REF   = 4
    R_B1_EXCL  = 5   # INPUT
    R_B1_VAT   = 6
    R_B1_TOTAL = 7
    # Bill 2
    R_B2_REF   = 8
    R_B2_EXCL  = 9   # INPUT
    R_B2_VAT   = 10
    R_B2_TOTAL = 11
    # Combined
    # blank 12
    R_COMB_EXCL  = 13   # ← comb_excl_row
    R_COMB_VAT   = 14
    R_COMB_TOTAL = 15
    R_PREPBY     = 16
    R_TS         = 17
    R_STATUS     = 18
    # blank 19
    R_SEC_B      = 20
    R_1300_NOTE  = 21
    R_1300_PCT   = 22   # ← pct_1300_row   B22 = input %
    R_1300_AMT   = 23   # ← amt_1300_row   B23 = =ROUND(B13*B22,2)
    # blank 24
    R_HDR_1300   = 25
    R_1300_S     = 26   # GL01
    R_1300_E     = 29   # SL12 (4 machines)
    R_1300_SUB   = 30
    # blank 31
    R_SEC_C      = 32
    R_REM_LBL    = 33   # B33 = remaining for 1200 = B13-B23
    R_HDR_1200   = 34
    R_1200_S     = 35
    R_1200_E     = 49   # 15 machines
    R_1200_SUB   = 50
    # blank 51
    R_VAT_ROW    = 52
    R_GRAND      = 53
    # blank 54

    n1300  = len(machines_1300)   # 4
    n1200  = len(machines_1200)   # 15
    lni_1300 = _last_nonzero_idx(machines_1300, wc_totals_1300)
    lni_1200 = _last_nonzero_idx(machines_1200, wc_totals_1200)

    denom_1300 = f"SUM($D${R_1300_S}:$D${R_1300_E})"
    denom_1200 = f"SUM($D${R_1200_S}:$D${R_1200_E})"

    COL_H = ["PK", "Machine Name", "Work Center", "GR Qty (kg)",
             "Alloc % (within plant)", "Amount Excl.VAT (THB)",
             "Cost Center", "CC Name", "GL Account", "Tax", "Description (JE)"]

    # ── Build rows ──────────────────────────────────────────────────────────
    rows: list[list] = [
        [f"ปันส่วนค่าไฟฟ้า {tab_label} — {plant_label}  |  {MONTH_DISPLAY}"],  # 1
        [],                                                                        # 2
        ["SECTION A — Bill Information"],                                          # 3
        [f"{bill1_label} Billing Ref",  f"{bill1_label} 04.26"],                  # 4
        [f"{bill1_label} Amount excl VAT (THB)", 0.00],                           # 5 INPUT
        [f"{bill1_label} VAT 7%",        f"=ROUND(B{R_B1_EXCL}*0.07,2)"],        # 6
        [f"{bill1_label} Total incl VAT",f"=B{R_B1_EXCL}+B{R_B1_VAT}"],          # 7
        [f"{bill2_label} Billing Ref",  f"{bill2_label} 04.26"],                  # 8
        [f"{bill2_label} Amount excl VAT (THB)", 0.00],                           # 9 INPUT
        [f"{bill2_label} VAT 7%",        f"=ROUND(B{R_B2_EXCL}*0.07,2)"],        # 10
        [f"{bill2_label} Total incl VAT",f"=B{R_B2_EXCL}+B{R_B2_VAT}"],          # 11
        [],                                                                        # 12 blank
        ["รวม Amount excl VAT",  f"=B{R_B1_EXCL}+B{R_B2_EXCL}"],                # 13
        ["รวม VAT",              f"=B{R_B1_VAT}+B{R_B2_VAT}"],                   # 14
        ["รวม Total incl VAT",   f"=B{R_B1_TOTAL}+B{R_B2_TOTAL}"],              # 15
        ["Prepared by", "Claude Code"],                                            # 16
        ["Timestamp",   timestamp],                                                # 17
        ["Status",      "Draft — Pending Review"],                                 # 18
        [],                                                                        # 19
        [f"SECTION B — Plant 1300 Allocation (สัดส่วนจากหน้างาน)"],              # 20
        ["** กรอก % Plant 1300 ใน B22 (หน้างานแจ้ง) — 1200 คำนวณอัตโนมัติ **"], # 21
        ["% สำหรับ Plant 1300",  0.0],                                            # 22 INPUT (%)
        ["Amount Plant 1300 excl VAT (THB)", f"=ROUND(B{R_COMB_EXCL}*B{R_1300_PCT},2)"],  # 23
        [],                                                                        # 24
        COL_H,                                                                     # 25 HDR 1300
    ]

    # Plant 1300 machine rows (26-29)
    for i, m in enumerate(machines_1300):
        r = R_1300_S + i
        qty_val = wc_totals_1300.get(m["wc"][0], 0.0)  # Python value for logic
        qty = f"=IFERROR(VLOOKUP(C{r},'PRD_1300'!$A:$D,4,0),0)"  # live formula for cross-check
        cc_name = ks13.get(m["cc"], "—")
        is_last = (i == lni_1300)
        if qty_val == 0:
            amt = 0
        elif is_last:
            amt = f"=ROUND(B{R_1300_AMT},2)-SUM(F{R_1300_S}:F{r-1})"
        else:
            amt = f"=IF(D{r}=0,0,ROUND($B${R_1300_AMT}*E{r},2))"
        rows.append([
            m["pk"], m["name"], m["wc"][0], qty,
            f"=IF(D{r}=0,0,D{r}/{denom_1300})", amt,
            m["cc"], cc_name, m["gl"], "V7",
            f"Elec {MONTH_LABEL} {m['name']}",
        ])

    rows += [
        ["", "Subtotal Plant 1300", "",
         f"=SUM(D{R_1300_S}:D{R_1300_E})",
         f"=SUM(E{R_1300_S}:E{R_1300_E})",
         f"=SUM(F{R_1300_S}:F{R_1300_E})",
         "", "", "", "", ""],  # 30
        [],  # 31
        [f"SECTION C — Plant 1200 Allocation (คงเหลือหลังหัก 1300)"],  # 32
        ["Remaining Plant 1200 excl VAT", f"=B{R_COMB_EXCL}-B{R_1300_AMT}"],  # 33
        COL_H,  # 34 HDR 1200
    ]

    # Plant 1200 machine rows (35-49)
    for i, m in enumerate(machines_1200):
        r = R_1200_S + i
        qty_val = wc_totals_1200.get(m["wc"][0], 0.0)  # Python value for logic
        qty = f"=IFERROR(VLOOKUP(C{r},'PRD_1200'!$A:$D,4,0),0)"  # live formula for cross-check
        cc_name = ks13.get(m["cc"], "—")
        is_last = (i == lni_1200)
        if qty_val == 0:
            amt = 0
        elif is_last:
            amt = f"=ROUND(B{R_REM_LBL},2)-SUM(F{R_1200_S}:F{r-1})"
        else:
            amt = f"=IF(D{r}=0,0,ROUND($B${R_REM_LBL}*E{r},2))"
        rows.append([
            m["pk"], m["name"], m["wc"][0], qty,
            f"=IF(D{r}=0,0,D{r}/{denom_1200})", amt,
            m["cc"], cc_name, m["gl"], "V7",
            f"Elec {MONTH_LABEL} {m['name']}",
        ])

    rows += [
        ["", "Subtotal Plant 1200", "",
         f"=SUM(D{R_1200_S}:D{R_1200_E})",
         f"=SUM(E{R_1200_S}:E{R_1200_E})",
         f"=SUM(F{R_1200_S}:F{R_1200_E})",
         "", "", "", "", ""],  # 50
        [],  # 51
        ["VAT", "Input VAT (Deductible)", "", "", "",
         f"=B{R_COMB_VAT}", "", "", GL_INPUT_TAX, "V7",
         f"VAT Input Tax {MONTH_LABEL}"],  # 52
        ["", "GRAND TOTAL", "", "", "",
         f"=F{R_1300_SUB}+F{R_1200_SUB}+F{R_VAT_ROW}", "", "", "", "",
         f'=IF(ABS(F{R_GRAND}-B{R_COMB_TOTAL})<0.01,"CHECK OK","CHECK FAIL")'],  # 53
        [],  # 54
    ]

    # Section D — JE
    R_SEC_D = 55
    R_HDR_D = 56
    R_JE_S  = 57
    rows.append([f"SECTION D — Journal Entry (SAP FB50)  |  {MONTH_LABEL}"])  # 55
    rows.append(["Itm", "D/C", "GL Account", "Cost Center", "Amount (THB)", "Tax Code", "Description"])  # 56

    itm = 1
    je_machines = (
        [(i, m, R_1300_S) for i, m in enumerate(machines_1300)
         if any(wc_totals_1300.get(wc, 0) > 0 for wc in m["wc"])]
        + [(i, m, R_1200_S) for i, m in enumerate(machines_1200)
           if any(wc_totals_1200.get(wc, 0) > 0 for wc in m["wc"])]
    )
    for idx, m, r_start in je_machines:
        src_r = r_start + idx
        rows.append([itm, "Dr", m["gl"], m["cc"],
                     f"=F{src_r}", "V7",
                     f"Elec {MONTH_LABEL} {m['name']}"])
        itm += 1

    R_JE_VAT = R_JE_S + len(je_machines)
    R_JE_CR  = R_JE_VAT + 1
    R_JE_BAL = R_JE_CR + 1
    dr_range = f"E{R_JE_S}:E{R_JE_VAT}"

    rows += [
        [itm,   "Dr", GL_INPUT_TAX, "", f"=B{R_COMB_VAT}",   "V7", f"VAT Input Tax {MONTH_LABEL}"],
        [itm+1, "Cr", GL_AP_TRADE,  "", f"=B{R_COMB_TOTAL}", "",   f"AP Elec {tab_label} {MONTH_LABEL}"],
        ["", "Balance", "", "", f"=SUM({dr_range})-E{R_JE_CR}", "",
         f'=IF(ABS(SUM({dr_range})-E{R_JE_CR})<0.01,"BALANCED","ERROR")'],
        [],
    ]

    # Section E — Verification
    R_SEC_E = R_JE_BAL + 2
    R_HDR_E = R_SEC_E + 1
    R_VE_1  = R_HDR_E + 1
    R_VE_2  = R_VE_1 + 1
    R_VE_3  = R_VE_2 + 1
    R_VE_4  = R_VE_3 + 1

    rows += [
        ["SECTION E — Verification"],  # R_SEC_E
        ["Check", "Actual", "Expected", "Status"],
        ["Sum 1300 + Sum 1200 = Combined excl VAT",
         f"=TEXT(F{R_1300_SUB}+F{R_1200_SUB},\"#,##0.00\")",
         f"=TEXT(B{R_COMB_EXCL},\"#,##0.00\")",
         f'=IF(ABS(F{R_1300_SUB}+F{R_1200_SUB}-B{R_COMB_EXCL})<0.01,"PASS","FAIL")'],
        ["Grand Total = Combined incl VAT",
         f"=TEXT(F{R_GRAND},\"#,##0.00\")",
         f"=TEXT(B{R_COMB_TOTAL},\"#,##0.00\")",
         f'=IF(ABS(F{R_GRAND}-B{R_COMB_TOTAL})<0.01,"PASS","FAIL")'],
        ["% 1300 + % 1200 = 100%",
         f"=TEXT(B{R_1300_PCT}+(B{R_1300_AMT}/(IF(B{R_COMB_EXCL}=0,1,B{R_COMB_EXCL}))),\"0.00%\")",
         "100.00%",
         f'=IF(ABS(B{R_1300_PCT}+(B{R_COMB_EXCL}-B{R_1300_AMT})/(IF(B{R_COMB_EXCL}=0,1,B{R_COMB_EXCL}))-1)<0.001,"PASS","FAIL")'],
        ["JE balanced",
         f"=TEXT(SUM({dr_range})-E{R_JE_CR},\"#,##0.00\")", "0.00",
         f'=IF(ABS(SUM({dr_range})-E{R_JE_CR})<0.01,"PASS","FAIL")'],
    ]

    ws.append_rows(rows, value_input_option="USER_ENTERED")

    # ── Structural ───────────────────────────────────────────────────────────
    n_cols = 11
    struct = [
        _freeze(ws, rows=R_HDR_1300, cols=0),
        _merge(ws, R_TITLE-1, 0, R_TITLE, n_cols),
        _merge(ws, R_SEC_A-1, 0, R_SEC_A, n_cols),
        _merge(ws, R_SEC_B-1, 0, R_SEC_B, n_cols),
        _merge(ws, R_1300_NOTE-1, 0, R_1300_NOTE, n_cols),
        _merge(ws, R_SEC_C-1, 0, R_SEC_C, n_cols),
        _merge(ws, R_SEC_D-1, 0, R_SEC_D, 7),
        _merge(ws, R_SEC_E-1, 0, R_SEC_E, n_cols),
        _row_h(ws, R_TITLE-1, 36),
        _row_h(ws, R_SEC_A-1, 26), _row_h(ws, R_SEC_B-1, 26),
        _row_h(ws, R_1300_NOTE-1, 28),
        _row_h(ws, R_HDR_1300-1, 22), _row_h(ws, R_1300_SUB-1, 22),
        _row_h(ws, R_SEC_C-1, 26), _row_h(ws, R_HDR_1200-1, 22), _row_h(ws, R_1200_SUB-1, 22),
        _row_h(ws, R_GRAND-1, 26), _row_h(ws, R_SEC_D-1, 26), _row_h(ws, R_SEC_E-1, 26),
    ] + [_col_w(ws, i, w) for i, w in enumerate([35, 210, 80, 110, 85, 150, 80, 140, 80, 45, 240])]
    sh.batch_update({"requests": [_unmerge_all(ws)] + struct})

    # ── Cell formatting ───────────────────────────────────────────────────────
    fmt = [
        _af_req(f"A{R_TITLE}", bold=True, font_size=12, fg=C_WHITE, bg=C_NAVY),
        _af_req(f"A{R_SEC_A}", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
        _af_req(f"A{R_SEC_B}", bold=True, font_size=10, fg=C_WHITE, bg=C_P1300H),
        _af_req(f"A{R_1300_NOTE}:K{R_1300_NOTE}", bold=True, italic=True, fg=C_MOCK_FG, bg=C_MOCK_BG),
        _af_req(f"A{R_SEC_C}", bold=True, font_size=10, fg=C_WHITE, bg=C_P1200H),
        _af_req(f"A{R_SEC_D}", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
        _af_req(f"A{R_SEC_E}", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
        # Bill labels + inputs
        *[_af_req(f"A{r}", bold=True, fg=C_DARK)
          for r in [R_B1_REF, R_B1_EXCL, R_B1_VAT, R_B1_TOTAL,
                    R_B2_REF, R_B2_EXCL, R_B2_VAT, R_B2_TOTAL,
                    R_COMB_EXCL, R_COMB_VAT, R_COMB_TOTAL, R_PREPBY, R_TS, R_STATUS]],
        _af_req(f"B{R_B1_EXCL}", number_format=NF_THB, bg=C_YELLOW, bold=True),
        _af_req(f"B{R_B2_EXCL}", number_format=NF_THB, bg=C_YELLOW, bold=True),
        _af_req(f"B{R_B1_VAT}", number_format=NF_THB),
        _af_req(f"B{R_B2_VAT}", number_format=NF_THB),
        _af_req(f"B{R_B1_TOTAL}", number_format=NF_THB, bold=True),
        _af_req(f"B{R_B2_TOTAL}", number_format=NF_THB, bold=True),
        _af_req(f"B{R_COMB_EXCL}", number_format=NF_THB, bold=True, font_size=11, fg=C_NAVY,
                borders={"top": _solid_border(C_BLUE)}),
        _af_req(f"B{R_COMB_VAT}", number_format=NF_THB),
        _af_req(f"B{R_COMB_TOTAL}", number_format=NF_THB, bold=True),
        # 1300 % input
        _af_req(f"A{R_1300_PCT}", bold=True, fg=C_DARK),
        _af_req(f"B{R_1300_PCT}", number_format=NF_PCT2, bold=True, bg=C_YELLOW, font_size=11),
        _af_req(f"A{R_1300_AMT}", bold=True, fg=C_DARK),
        _af_req(f"B{R_1300_AMT}", number_format=NF_THB, bold=True, fg=C_P1300H),
        _af_req(f"A{R_REM_LBL}", bold=True, fg=C_DARK),
        _af_req(f"B{R_REM_LBL}", number_format=NF_THB, bold=True, fg=C_P1200H),
        # Column headers
        _af_req(f"A{R_HDR_1300}:K{R_HDR_1300}", bold=True, fg=C_WHITE, bg=C_P1300H, halign="CENTER"),
        _af_req(f"A{R_HDR_1200}:K{R_HDR_1200}", bold=True, fg=C_WHITE, bg=C_P1200H, halign="CENTER"),
        _af_req(f"A{R_HDR_D}:G{R_HDR_D}", bold=True, fg=C_DARK, bg=C_LBLUE, halign="CENTER"),
        _af_req(f"A{R_HDR_E}:D{R_HDR_E}", bold=True, fg=C_DARK, bg=C_LBLUE, halign="CENTER"),
    ]
    # Plant 1300 machine rows
    for i, m in enumerate(machines_1300):
        r = R_1300_S + i
        bg = C_P1300A if i % 2 == 1 else C_P1300
        qty_val = wc_totals_1300.get(m["wc"][0], 0.0)
        fg = "#AAAAAA" if qty_val == 0 else C_BLACK
        fmt += [
            _af_req(f"A{r}:K{r}", fg=fg, bg=bg),
            _af_req(f"D{r}", number_format=NF_KG, halign="RIGHT", bg=bg),
            _af_req(f"E{r}", number_format=NF_PCT, halign="RIGHT", bg=bg),
            _af_req(f"F{r}", number_format=NF_THB, halign="RIGHT", bold=True, bg=bg),
        ]
    fmt += [
        _af_req(f"A{R_1300_SUB}:K{R_1300_SUB}", bold=True, bg=C_LBLUE,
                borders={"top": _solid_border(C_BLUE), "bottom": _solid_border(C_BLUE)}),
        _af_req(f"D{R_1300_SUB}", number_format=NF_KG, halign="RIGHT", bold=True, bg=C_LBLUE),
        _af_req(f"F{R_1300_SUB}", number_format=NF_THB, halign="RIGHT", bold=True, bg=C_LBLUE),
    ]
    # Plant 1200 machine rows
    for i, m in enumerate(machines_1200):
        r = R_1200_S + i
        bg = C_P1200A if i % 2 == 1 else C_P1200
        qty_val = wc_totals_1200.get(m["wc"][0], 0.0)
        fg = "#AAAAAA" if qty_val == 0 else C_BLACK
        fmt += [
            _af_req(f"A{r}:K{r}", fg=fg, bg=bg),
            _af_req(f"D{r}", number_format=NF_KG, halign="RIGHT", bg=bg),
            _af_req(f"E{r}", number_format=NF_PCT, halign="RIGHT", bg=bg),
            _af_req(f"F{r}", number_format=NF_THB, halign="RIGHT", bold=True, bg=bg),
        ]
    fmt += [
        _af_req(f"A{R_1200_SUB}:K{R_1200_SUB}", bold=True, bg=C_LBLUE,
                borders={"top": _solid_border(C_BLUE), "bottom": _solid_border(C_BLUE)}),
        _af_req(f"D{R_1200_SUB}", number_format=NF_KG, halign="RIGHT", bold=True, bg=C_LBLUE),
        _af_req(f"F{R_1200_SUB}", number_format=NF_THB, halign="RIGHT", bold=True, bg=C_LBLUE),
        # VAT + Grand Total
        _af_req(f"A{R_VAT_ROW}:K{R_VAT_ROW}", bg=C_YELLOW, italic=True),
        _af_req(f"F{R_VAT_ROW}", number_format=NF_THB, halign="RIGHT", bg=C_YELLOW),
        _af_req(f"A{R_GRAND}:K{R_GRAND}", bold=True, bg=C_GREEN_BG, fg=C_GREEN_FG,
                borders={"top": _solid_border(C_BLUE, 2), "bottom": _solid_border(C_BLUE, 2)}),
        _af_req(f"F{R_GRAND}", number_format=NF_THB, halign="RIGHT", bold=True, bg=C_GREEN_BG),
    ]
    # JE rows
    for r in range(R_JE_S, R_JE_VAT+1):
        fmt += [_af_req(f"A{r}:G{r}", bg=C_JE_DR),
                _af_req(f"B{r}", bold=True, fg="#2F5496", halign="CENTER", bg=C_JE_DR),
                _af_req(f"E{r}", number_format=NF_THB, halign="RIGHT", bg=C_JE_DR)]
    fmt += [
        _af_req(f"A{R_JE_CR}:G{R_JE_CR}", bg=C_JE_CR),
        _af_req(f"B{R_JE_CR}", bold=True, fg="#9C3600", halign="CENTER", bg=C_JE_CR),
        _af_req(f"E{R_JE_CR}", number_format=NF_THB, halign="RIGHT", bg=C_JE_CR),
    ]
    # Verification rows
    for r in [R_VE_1, R_VE_2, R_VE_3, R_VE_4]:
        fmt.append(_af_req(f"D{r}", halign="CENTER", bold=True))
    ws.batch_format(fmt)

    cond = []
    for r in [R_VE_1, R_VE_2, R_VE_3, R_VE_4]:
        cond += [
            _cond_fmt(ws, r-1, 3, r, 4, f'=$D${r}="PASS"', C_GREEN_BG, C_GREEN_FG),
            _cond_fmt(ws, r-1, 3, r, 4, f'=$D${r}="FAIL"', C_RED_BG, C_RED_FG),
        ]
    cond += [
        _cond_fmt(ws, R_GRAND-1, 10, R_GRAND, 11, f'=$K${R_GRAND}="CHECK OK"', C_GREEN_BG, C_GREEN_FG),
        _cond_fmt(ws, R_GRAND-1, 10, R_GRAND, 11, f'=$K${R_GRAND}="CHECK FAIL"', C_RED_BG, C_RED_FG),
    ]
    sh.batch_update({"requests": cond})


# ─────────────────────────── SUMMARY TAB (04.2026) ─────────────────────────

def write_summary_tab(ws, sh, wc_totals: dict[int, dict], timestamp: str) -> None:
    ws.clear()
    # Cross-tab formula shortcuts
    def _ref(tab: str, row: int, col: str = "B") -> str:
        return f"='{tab}'!{col}{row}"

    a1_excl   = _ref("A1", A1_BILL_EXCL_ROW)
    a1_vat    = _ref("A1", A1_BILL_VAT_ROW)
    a1_total  = _ref("A1", A1_BILL_TOTAL_ROW)

    a2_excl   = _ref("A2+SCG", A2SCG_COMB_EXCL_ROW)
    a2_vat    = _ref("A2+SCG", A2SCG_COMB_VAT_ROW)
    a2_total  = _ref("A2+SCG", A2SCG_COMB_TOTAL_ROW)
    a2_1300   = _ref("A2+SCG", A2SCG_1300_AMT_ROW)

    gb_excl   = _ref("Goblex", GOBLEX_COMB_EXCL_ROW)
    gb_vat    = _ref("Goblex", GOBLEX_COMB_VAT_ROW)
    gb_total  = _ref("Goblex", GOBLEX_COMB_TOTAL_ROW)
    gb_1300   = _ref("Goblex", GOBLEX_1300_AMT_ROW)

    # Summary rows
    rows: list[list] = [
        [f"ปันส่วนค่าไฟฟ้า AMC — สรุปรวม  |  {MONTH_DISPLAY}"],      # 1
        [],                                                               # 2
        ["SECTION A — Bill Summary"],                                    # 3
        ["Source", "Amount excl VAT (THB)", "VAT (THB)", "Total incl VAT (THB)"],  # 4
        ["STC",    0,      0,      0],                                   # 5
        ["A1",     a1_excl, a1_vat, a1_total],                          # 6
        ["A2+SCG", a2_excl, a2_vat, a2_total],                          # 7
        ["Goblex", gb_excl, gb_vat, gb_total],                          # 8
        ["รวมทั้งหมด",
         "=SUM(B5:B8)", "=SUM(C5:C8)", "=SUM(D5:D8)"],                 # 9
        [],                                                               # 10
        ["SECTION B — Cost by Plant (excl VAT)"],                       # 11
        ["Plant", "Source", "Amount excl VAT (THB)"],                   # 12
        ["Plant 1100", "A1",
         f"='A1'!B{A1_BILL_EXCL_ROW}"],                                 # 13
        ["Plant 1200", "A2+SCG + Goblex",
         f"=('A2+SCG'!B{A2SCG_COMB_EXCL_ROW}-'A2+SCG'!B{A2SCG_1300_AMT_ROW})"
         f"+('Goblex'!B{GOBLEX_COMB_EXCL_ROW}-'Goblex'!B{GOBLEX_1300_AMT_ROW})"],  # 14
        ["Plant 1300", "A2+SCG + Goblex",
         f"='A2+SCG'!B{A2SCG_1300_AMT_ROW}+'Goblex'!B{GOBLEX_1300_AMT_ROW}"],  # 15
        ["รวม (ต้องเท่ากับ SECTION A excl VAT)", "",
         "=SUM(C13:C15)"],                                              # 16
        [],                                                               # 17
        ["SECTION C — Verification"],                                    # 18
        ["Check", "Actual", "Expected", "Status"],                      # 19
        ["Plant total = Bill total excl VAT",
         "=TEXT(C16,\"#,##0.00\")", "=TEXT(B9,\"#,##0.00\")",
         '=IF(ABS(C16-B9)<0.01,"PASS","FAIL")'],                       # 20
        [],                                                               # 21
        ["SECTION D — PRD Source Reference"],                            # 22
        ["Plant", "Total GR Qty (kg)", "Source File"],                  # 23
        ["1100", round(sum(wc_totals.get(1100, {}).values())),
         str(PRD_PATHS[1100])],                                          # 24
        ["1200", round(sum(wc_totals.get(1200, {}).values())),
         str(PRD_PATHS[1200])],                                          # 25
        ["1300", round(sum(wc_totals.get(1300, {}).values())),
         str(PRD_PATHS[1300])],                                          # 26
        [],                                                               # 27
        ["SECTION E — Sign-off"],                                        # 28
        ["Prepared by", "Claude Code"],                                   # 29
        ["Timestamp",   timestamp],                                       # 30
        ["Status",      "Draft — Pending Review"],                        # 31
        ["Note", "Update bill amounts in each tab (A1/A2+SCG/Goblex) then enter % for Plant 1300 in B22 of A2+SCG and Goblex"],  # 32
    ]

    ws.append_rows(rows, value_input_option="USER_ENTERED")

    # Structural
    n_cols = 4
    struct = [
        _merge(ws, 0, 0, 1, n_cols),
        _merge(ws, 2, 0, 3, n_cols),
        _merge(ws, 10, 0, 11, n_cols),
        _merge(ws, 17, 0, 18, n_cols),
        _merge(ws, 21, 0, 22, n_cols),
        _merge(ws, 27, 0, 28, n_cols),
        _row_h(ws, 0, 36),
        _row_h(ws, 8, 26),
        _row_h(ws, 10, 26), _row_h(ws, 15, 22),
        _row_h(ws, 17, 26), _row_h(ws, 21, 26), _row_h(ws, 27, 26),
    ] + [_col_w(ws, i, w) for i, w in enumerate([180, 200, 200, 200])]
    sh.batch_update({"requests": [_unmerge_all(ws)] + struct})

    # Formatting
    fmt = [
        _af_req("A1", bold=True, font_size=13, fg=C_WHITE, bg=C_NAVY),
        _af_req("A3", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
        _af_req("A4:D4", bold=True, fg=C_DARK, bg=C_LBLUE, halign="CENTER"),
        _af_req("A11", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
        _af_req("A12:C12", bold=True, fg=C_DARK, bg=C_LBLUE, halign="CENTER"),
        _af_req("A18", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
        _af_req("A19:D19", bold=True, fg=C_DARK, bg=C_LBLUE, halign="CENTER"),
        _af_req("A22", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
        _af_req("A23:C23", bold=True, fg=C_DARK, bg=C_LBLUE, halign="CENTER"),
        _af_req("A28", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
    ]
    # Bill summary rows
    for r in range(5, 9):
        bg = C_ALTROW if r % 2 == 0 else C_WHITE
        fmt += [
            _af_req(f"A{r}:D{r}", fg=C_BLACK, bg=bg),
            _af_req(f"B{r}", number_format=NF_THB, halign="RIGHT", bg=bg),
            _af_req(f"C{r}", number_format=NF_THB, halign="RIGHT", bg=bg),
            _af_req(f"D{r}", number_format=NF_THB, halign="RIGHT", bg=bg),
        ]
    fmt += [
        _af_req("A9:D9", bold=True, bg=C_GREEN_BG, fg=C_GREEN_FG,
                borders={"top": _solid_border(C_BLUE, 2), "bottom": _solid_border(C_BLUE, 2)}),
        _af_req("B9", number_format=NF_THB, halign="RIGHT", bold=True, bg=C_GREEN_BG),
        _af_req("C9", number_format=NF_THB, halign="RIGHT", bold=True, bg=C_GREEN_BG),
        _af_req("D9", number_format=NF_THB, halign="RIGHT", bold=True, bg=C_GREEN_BG),
    ]
    # Plant breakdown
    for r, hc in [(13, C_P1100H), (14, C_P1200H), (15, C_P1300H)]:
        fmt += [
            _af_req(f"A{r}", bold=True, fg=C_WHITE, bg=hc),
            _af_req(f"C{r}", number_format=NF_THB, halign="RIGHT"),
        ]
    fmt += [
        _af_req("A16:C16", bold=True, bg=C_LBLUE),
        _af_req("C16", number_format=NF_THB, halign="RIGHT", bold=True, bg=C_LBLUE),
        _af_req("D20", halign="CENTER", bold=True),
    ]
    # PRD ref
    for r in [24, 25, 26]:
        fmt.append(_af_req(f"B{r}", number_format=NF_KG, halign="RIGHT"))
    ws.batch_format(fmt)

    cond = [
        _cond_fmt(ws, 19, 3, 20, 4, '=$D$20="PASS"', C_GREEN_BG, C_GREEN_FG),
        _cond_fmt(ws, 19, 3, 20, 4, '=$D$20="FAIL"', C_RED_BG, C_RED_FG),
    ]
    sh.batch_update({"requests": cond})


# ─────────────────────────── CONSOLE DRY-RUN ───────────────────────────────

def print_dry_run(wc_totals: dict[int, dict]) -> None:
    sep  = "=" * 70
    line = "-" * 70
    print(f"\n{sep}")
    print(f"  AMC Electricity Workbook v2 -- {MONTH_LABEL}  [DRY RUN]")
    print(f"{sep}")

    for plant, machines in [(1100, PLANT_1100_MACHINES), (1200, PLANT_1200_MACHINES), (1300, PLANT_1300_MACHINES)]:
        totals = wc_totals.get(plant, {})
        plant_total = sum(totals.values())
        print(f"\n{line}")
        print(f"  Plant {plant}  |  Total GR Qty: {plant_total:,.0f} kg")
        print(f"  {'WC':<10} {'GR Qty (kg)':>14}  Machine")
        print(f"  {'-'*10} {'-'*14}  {'-'*30}")
        for m in machines:
            qty = sum(totals.get(wc, 0.0) for wc in m["wc"])
            flag = "" if qty > 0 else " (no production)"
            print(f"  {m['wc'][0]:<10} {qty:>14,.0f}  {m['name']}{flag}")

    print(f"\n{sep}")
    print(f"  Tab order: PRD_1100 | PRD_1200 | PRD_1300 | STC | A1 | A2+SCG | Goblex | 04.2026")
    print(f"  After script: update bill amounts in A1/A2+SCG/Goblex tabs")
    print(f"  Then enter % for Plant 1300 in B22 of A2+SCG and Goblex tabs")
    print(f"{sep}\n")


# ─────────────────────────── MAIN ──────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="AMC Electricity Workbook v2")
    parser.add_argument("--dry-run", action="store_true", help="Console only, no Google Sheet write")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    print("[1/5] Loading KS13 Master CC...")
    ks13 = load_ks13(KS13_PATH)

    print("[2/5] Loading PRD files (actual April 2026)...")
    prd_data: dict[int, tuple[pd.DataFrame, dict]] = {}
    for plant, path in PRD_PATHS.items():
        machines = {1100: PLANT_1100_MACHINES, 1200: PLANT_1200_MACHINES, 1300: PLANT_1300_MACHINES}[plant]
        df_raw, wc_totals = load_prd(plant, path, machines)
        prd_data[plant] = (df_raw, wc_totals)

    wc_totals_all = {plant: prd_data[plant][1] for plant in PRD_PATHS}

    # Stop if any allocation plant has zero GR Qty
    for plant in [1100, 1200, 1300]:
        total = sum(wc_totals_all[plant].values())
        if total == 0:
            raise ValueError(f"Total GR Qty for Plant {plant} = 0 — cannot allocate. Check PRD file.")

    print("[3/5] Validating CC codes against KS13...")
    validate_ccs(ALL_MACHINES, ks13)

    print_dry_run(wc_totals_all)

    if args.dry_run:
        print("[5/5] --dry-run: skipping Google Sheet write.")
        return

    print("[4/5] Writing to Google Sheet...")
    gc = get_gspread_client()
    sh = gc.open_by_key(SHEET_ID)

    # Remove legacy "Sheet1" default tab if present
    try:
        default = sh.worksheet("Sheet1")
        if len(sh.worksheets()) > 1:
            sh.del_worksheet(default)
    except Exception:
        pass

    # Tab order
    tab_order = ["PRD_1100", "PRD_1200", "PRD_1300", "STC", "A1", "A2+SCG", "Goblex", "04.2026"]

    ws_map = {}
    for tab in tab_order:
        ws_map[tab] = get_or_add_worksheet(sh, tab)

    # Write PRD tabs
    for plant in [1100, 1200, 1300]:
        df_raw, wc_totals = prd_data[plant]
        machines = {1100: PLANT_1100_MACHINES, 1200: PLANT_1200_MACHINES, 1300: PLANT_1300_MACHINES}[plant]
        print(f"  Writing PRD_{plant}...")
        write_prd_tab(ws_map[f"PRD_{plant}"], sh, plant, df_raw,
                      wc_totals, machines, ks13,
                      str(PRD_PATHS[plant]), timestamp)

    print("  Writing STC...")
    write_stc_tab(ws_map["STC"], sh, timestamp)

    print("  Writing A1...")
    write_a1_tab(ws_map["A1"], sh, wc_totals_all[1100], ks13, timestamp)

    print("  Writing A2+SCG...")
    _write_dual_bill_tab(
        ws_map["A2+SCG"], sh,
        tab_label="A2+SCG", plant_label="Plant 1200 + 1300",
        bill1_label="A2", bill2_label="SCG",
        wc_totals_1200=wc_totals_all[1200],
        wc_totals_1300=wc_totals_all[1300],
        ks13=ks13, timestamp=timestamp,
        comb_excl_row=A2SCG_COMB_EXCL_ROW,
        pct_1300_row=A2SCG_1300_PCT_ROW,
        amt_1300_row=A2SCG_1300_AMT_ROW,
    )

    print("  Writing Goblex...")
    _write_dual_bill_tab(
        ws_map["Goblex"], sh,
        tab_label="Goblex", plant_label="Plant 1200 + 1300",
        bill1_label="Goblex-1", bill2_label="Goblex-2",
        wc_totals_1200=wc_totals_all[1200],
        wc_totals_1300=wc_totals_all[1300],
        ks13=ks13, timestamp=timestamp,
        comb_excl_row=GOBLEX_COMB_EXCL_ROW,
        pct_1300_row=GOBLEX_1300_PCT_ROW,
        amt_1300_row=GOBLEX_1300_AMT_ROW,
    )

    print("  Writing 04.2026 summary...")
    write_summary_tab(ws_map["04.2026"], sh, wc_totals_all, timestamp)

    # Reorder tabs in sheet
    try:
        all_ws = {ws.title: ws for ws in sh.worksheets()}
        reorder_requests = [{"updateSheetProperties": {
            "properties": {"sheetId": _sheet_id(all_ws[t]), "index": i},
            "fields": "index"}}
            for i, t in enumerate(tab_order) if t in all_ws]
        if reorder_requests:
            sh.batch_update({"requests": reorder_requests})
    except Exception as e:
        print(f"  Warning: could not reorder tabs — {e}")

    url = sh.url
    print(f"\n  Google Sheet: {url}")

    # Analytics log
    try:
        if ANALYTICS_LOG_SHEET_ID:
            log_ws = gc.open_by_key(ANALYTICS_LOG_SHEET_ID).sheet1
            append_analytics_log(log_ws, {
                "date": datetime.now().strftime("%d/%m/%Y"),
                "type": "ElectricityAlloc",
                "name": SHEET_NAME,
                "source": "PRD_1100/1200/1300 April 2026",
                "period": MONTH_LABEL,
                "output_file": url,
                "status": "Draft",
                "reviewed_by": "",
            })
    except Exception as e:
        print(f"  Warning: analytics_log failed — {e}")

    print(f"\n[5/5] Done.")
    print(f"  Sheet URL: {url}")
    print(f"  Next steps:")
    print(f"    1. Open Sheet and enter bill amounts in A1 tab (B5), A2+SCG tab (B5, B9), Goblex tab (B5, B9)")
    print(f"    2. Enter % for Plant 1300 in B22 of A2+SCG and Goblex tabs")
    print(f"    3. Verify all SECTION D/E rows show PASS / CHECK OK")


if __name__ == "__main__":
    main()
