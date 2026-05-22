"""
Electricity Cost Allocation — GA Plant 2200, Asia Grand
Version 2 — same concept as electricity_alloc_amc_v2.py

Tab structure:
  PRD_2200  — WC Summary (SUMIFS live) + Raw Data section
  04.2026   — Allocation: INPUT cell for bill amount + VLOOKUP GR Qty

Usage:
    python scripts/electricity_alloc_ga_v2.py           # write to Google Sheet
    python scripts/electricity_alloc_ga_v2.py --dry-run # console preview only
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

SHEET_NAME  = "ปันส่วนค่าไฟฟ้า GA 2026"
SHEET_ID    = ""          # ใส่ Sheet ID จริงถ้ามี — ถ้าว่างจะ lookup ด้วยชื่อ

BASE        = Path(__file__).parent.parent.parent / "01_Bronze_Raw"
KS13_PATH   = BASE / "Master" / "KS13_Master.XLSX"
PRD_PATH    = BASE / "PRD_GI" / "GA_2200_04.2026.XLSX"

MONTH_LABEL   = "04.2026"
MONTH_DISPLAY = "เมษายน 2026"

COMBINED_WC_MAP = {
    "SL01, EU01": ["SL01", "EU01"],   # Slitter S1 + Eye Up E1 running together
}

GL_INPUT_TAX = "1540101"
GL_AP_TRADE  = "2110101"

# Machine definitions (PK order determines row sequence)
# wc: [] = no PRD data — machine exists but not recorded in SAP PRD
MACHINES = [
    {"pk":  1, "name": "S1 — Slitter",          "wc": ["SL01"], "cc": "2287101", "gl": "5611010"},
    {"pk":  2, "name": "L1 — Rotary Shear L1",  "wc": ["SE01"], "cc": "2287201", "gl": "5611010"},
    {"pk":  3, "name": "L2 — Rotary Shear L2",  "wc": ["SE02"], "cc": "2287202", "gl": "5611010"},
    {"pk":  4, "name": "L3 — Rotary Shear L3",  "wc": [],       "cc": "2287203", "gl": "5611010"},
    {"pk":  5, "name": "E1 — Eye Up E1",         "wc": ["EU01"], "cc": "2287103", "gl": "5611010"},
    {"pk":  6, "name": "M1 — Mini Rotary M1",    "wc": ["SE05"], "cc": "2287205", "gl": "5611010"},
    {"pk":  7, "name": "D1 — Down Shear D1",     "wc": ["SE07"], "cc": "2287207", "gl": "5611010"},
    {"pk":  8, "name": "D2 — Down Shear D2",     "wc": ["SE08"], "cc": "2287208", "gl": "5611010"},
    {"pk":  9, "name": "D3 — Down Shear D3",     "wc": [],       "cc": "2287209", "gl": "5611010"},
    {"pk": 10, "name": "D4 — Down Shear D4",     "wc": [],       "cc": "2287210", "gl": "5611010"},
    {"pk": 11, "name": "X1 — Mini Slitter",      "wc": [],       "cc": "2287102", "gl": "5611010"},
]


# ─────────────────────────── COLORS & FORMATS ──────────────────────────────

def _rgb(h: str) -> dict:
    h = h.lstrip("#")
    return {"red": round(int(h[0:2], 16) / 255, 4),
            "green": round(int(h[2:4], 16) / 255, 4),
            "blue": round(int(h[4:6], 16) / 255, 4)}

C_NAVY    = "#1F3864"; C_BLUE  = "#2F5496"; C_LBLUE = "#D9E1F2"
C_WHITE   = "#FFFFFF"; C_BLACK = "#000000"; C_DARK  = "#1F3864"
C_ALTROW  = "#F0F4FB"; C_YELLOW = "#FFF2CC"
C_GREEN_BG = "#E2EFDA"; C_GREEN_FG = "#375623"
C_RED_BG   = "#FFE2E2"; C_RED_FG   = "#9C0006"
C_JE_DR    = "#EBF3FB"; C_JE_CR    = "#FDE9D9"
C_GA_H     = "#7030A0"   # GA accent — purple
C_GA       = "#F3EAFA"   # GA machine row light
C_GA_A     = "#E8D5F7"   # GA machine row alternate

NF_THB  = {"type": "NUMBER", "pattern": "#,##0.00"}
NF_KG   = {"type": "NUMBER", "pattern": "#,##0"}
NF_PCT  = {"type": "NUMBER", "pattern": "0.0000%"}
NF_PCT2 = {"type": "NUMBER", "pattern": "0.00%"}


def _solid_border(color: str = "#BFBFBF", width: int = 1) -> dict:
    return {"style": "SOLID", "width": width, "color": _rgb(color)}


def _sheet_id(ws) -> int:
    return ws._properties["sheetId"]


def _af_req(rng: str, *, bold=False, italic=False, font_size=10,
            fg=C_BLACK, bg=None, halign=None, number_format=None,
            borders=None) -> dict:
    fmt: dict = {
        "textFormat": {"bold": bold, "italic": italic, "fontSize": font_size,
                       "foregroundColor": _rgb(fg)},
        "wrapStrategy": "OVERFLOW_CELL",
    }
    if bg:           fmt["backgroundColor"] = _rgb(bg)
    if halign:       fmt["horizontalAlignment"] = halign
    if number_format: fmt["numberFormat"] = number_format
    if borders:      fmt["borders"] = borders
    return {"range": rng, "format": fmt}


def _merge(ws, r1, c1, r2, c2) -> dict:
    return {"mergeCells": {"range": {"sheetId": _sheet_id(ws),
        "startRowIndex": r1, "endRowIndex": r2,
        "startColumnIndex": c1, "endColumnIndex": c2}, "mergeType": "MERGE_ALL"}}


def _freeze(ws, rows=0, cols=0) -> dict:
    return {"updateSheetProperties": {"properties": {"sheetId": _sheet_id(ws),
        "gridProperties": {"frozenRowCount": rows, "frozenColumnCount": cols}},
        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}}


def _col_w(ws, col, px) -> dict:
    return {"updateDimensionProperties": {"range": {"sheetId": _sheet_id(ws),
        "dimension": "COLUMNS", "startIndex": col, "endIndex": col + 1},
        "properties": {"pixelSize": px}, "fields": "pixelSize"}}


def _row_h(ws, row, px) -> dict:
    return {"updateDimensionProperties": {"range": {"sheetId": _sheet_id(ws),
        "dimension": "ROWS", "startIndex": row, "endIndex": row + 1},
        "properties": {"pixelSize": px}, "fields": "pixelSize"}}


def _cond_fmt(ws, r1, c1, r2, c2, formula, bg, fg) -> dict:
    return {"addConditionalFormatRule": {"rule": {
        "ranges": [{"sheetId": _sheet_id(ws),
                    "startRowIndex": r1, "endRowIndex": r2,
                    "startColumnIndex": c1, "endColumnIndex": c2}],
        "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": formula}]},
            "format": {"backgroundColor": _rgb(bg),
                       "textFormat": {"foregroundColor": _rgb(fg), "bold": True}},
        }}, "index": 0}}


def _unmerge_all(ws) -> dict:
    return {"unmergeCells": {"range": {"sheetId": _sheet_id(ws),
        "startRowIndex": 0, "endRowIndex": 500,
        "startColumnIndex": 0, "endColumnIndex": 20}}}


# ─────────────────────────── DATA LOADING ──────────────────────────────────

def load_ks13(path: Path) -> dict[str, str]:
    """Load KS13 Master → {cc_str: cc_name}. Returns {} if file not found."""
    if not path.exists():
        print(f"  KS13 not found at {path} — CC validation skipped")
        return {}
    df = pd.read_excel(str(path), header=0)
    df.columns = [str(c).strip() for c in df.columns]
    cc_col   = next((c for c in df.columns if "cost" in c.lower() and "center" in c.lower()), None)
    name_col = next((c for c in df.columns if "name" in c.lower() or "description" in c.lower()), None)
    if not cc_col or not name_col:
        print(f"  KS13: cannot find CC/Name columns — validation skipped")
        return {}
    result = {}
    for _, row in df.iterrows():
        cc   = str(row[cc_col]).strip()
        name = str(row[name_col]).strip()
        if cc and cc != "nan":
            result[cc] = name
    print(f"  KS13: {len(result)} cost centers loaded")
    return result


def load_prd(path: Path) -> tuple[pd.DataFrame, dict[str, float]]:
    """
    Load PRD Excel for GA Plant 2200.
    Returns (df_raw_key_cols, wc_totals {wc: qty}).
    Handles COMBINED_WC_MAP expansion.
    """
    if not path.exists():
        raise FileNotFoundError(f"PRD not found: {path}")
    df = pd.read_excel(str(path), header=0)
    for col in ("Work Center", "Actual GR QTY"):
        if col not in df.columns:
            raise ValueError(f"PRD GA: missing column '{col}'")

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

    machine_wcs: set[str] = {wc for m in MACHINES for wc in m["wc"]}
    wc_totals: dict[str, float] = {}
    unknown: set[str] = set()

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
            unknown.add(wc_raw)

    if unknown:
        print(f"  GA PRD WCs not in machine list (skipped): {sorted(unknown)}")

    key_cols = ["Work Center", "Order", "Material", "Description (EN)",
                "Actual GR QTY", "Actual ByProduct Scrap QTY",
                "Actual ByProduct Grade B QTY", "Actual ByProduct Grade C QTY",
                "Actual GR Unit", "Status"]
    avail    = [c for c in key_cols if c in df.columns]
    df_raw   = df[df["_total_qty"] > 0][avail].reset_index(drop=True)

    total = sum(wc_totals.values())
    print(f"  GA Plant 2200: {len(wc_totals)} WCs | total Qty = {total:,.0f} kg | {len(df_raw)} raw rows")
    return df_raw, wc_totals


def validate_ccs(ks13: dict[str, str]) -> None:
    if not ks13:
        return
    missing = [m for m in MACHINES if m["cc"] not in ks13]
    if missing:
        print(f"  WARNING: {len(missing)} CC codes not found in KS13 (GA uses 228xxxx range):")
        for m in missing:
            print(f"    {m['cc']} ({m['name']})")
    else:
        print(f"  All {len(MACHINES)} CC codes validated in KS13.")


def _last_nonzero_idx(wc_totals: dict[str, float]) -> int:
    """0-based index of the last machine with GR Qty > 0."""
    idx = -1
    for i, m in enumerate(MACHINES):
        if any(wc_totals.get(wc, 0) > 0 for wc in m["wc"]):
            idx = i
    return idx


# ─────────────────────────── PRD_2200 TAB ──────────────────────────────────

def write_prd_tab(ws, sh, df_raw: pd.DataFrame, wc_totals: dict[str, float],
                  ks13: dict[str, str], source_path: str, timestamp: str) -> None:
    ws.clear()

    # Combined WC reverse lookup: wc → [combined keys that include it]
    combined_addons: dict[str, list[str]] = {}
    for combined_key, parts in COMBINED_WC_MAP.items():
        for part in parts:
            combined_addons.setdefault(part, []).append(combined_key)

    # Pre-compute row constants
    WC_HDR_ROW     = 5
    # Only include machines that have WC (skip empty-wc machines in summary)
    wc_machines    = [m for m in MACHINES if m["wc"]]
    n_wc_rows      = len(wc_machines)        # one row per WC (GA has 1 WC per machine max)
    D_WC_S         = WC_HDR_ROW + 1
    D_WC_E         = WC_HDR_ROW + n_wc_rows
    TOTAL_ROW_NUM  = D_WC_E + 1
    RAW_HDR_ROW    = TOTAL_ROW_NUM + 2
    RAW_DATA_START = RAW_HDR_ROW + 2

    def _gr_formula(wc: str, r: int) -> str:
        # Sum GR QTY + ByProduct Scrap + Grade B + Grade C (cols E,F,G,H in raw data)
        rng_a    = f"$A${RAW_DATA_START}:$A$9999"
        criteria = [f"A{r}"] + [f'"{key}"' for key in combined_addons.get(wc, [])]
        parts    = [
            f"SUMIFS(${c}${RAW_DATA_START}:${c}$9999,{rng_a},{crit})"
            for c in ("E", "F", "G", "H") for crit in criteria
        ]
        return "=" + "+".join(parts)

    rows: list[list] = [
        [f"PRD Report — GA Plant 2200  |  {MONTH_DISPLAY}"],            # 1
        [f"Source: {source_path}", "", "", "Loaded:", timestamp],        # 2
        [],                                                               # 3
        ["WC Summary — GR Qty by Work Center (Allocation Basis)"],       # 4
        ["Work Center", "Cost Center", "CC Name", "Total Qty (kg)", "% of Plant"],  # 5
    ]

    for m in wc_machines:
        wc      = m["wc"][0]
        r       = len(rows) + 1
        cc_name = ks13.get(m["cc"], "—")
        rows.append([wc, m["cc"], cc_name, _gr_formula(wc, r), f"=IFERROR(D{r}/D{TOTAL_ROW_NUM},0)"])

    rows.append(["Total", "", "",
                 f"=SUM(D{D_WC_S}:D{D_WC_E})",
                 f"=IF(D{TOTAL_ROW_NUM}>0,1,0)"])
    rows.append([])

    rows.append([f"Raw Data — PRD GA Plant 2200  (rows with Total Qty > 0)"])
    if not df_raw.empty:
        rows.append(list(df_raw.columns))
        for _, row in df_raw.iterrows():
            rows.append([None if pd.isna(v) else v for v in row.values])
    else:
        rows.append(["No data"])

    ws.append_rows(rows, value_input_option="USER_ENTERED")

    # Structural
    n_cols = 5
    struct = [
        _freeze(ws, rows=WC_HDR_ROW, cols=0),
        _merge(ws, 0, 0, 1, n_cols),
        _merge(ws, 3, 0, 4, n_cols),
        _merge(ws, RAW_HDR_ROW - 1, 0, RAW_HDR_ROW, n_cols),
        _row_h(ws, 0, 32), _row_h(ws, 3, 26),
        _row_h(ws, WC_HDR_ROW - 1, 22),
        _row_h(ws, RAW_HDR_ROW - 1, 26),
    ] + [_col_w(ws, i, w) for i, w in enumerate([100, 100, 200, 120, 80])]
    sh.batch_update({"requests": [_unmerge_all(ws)] + struct})

    # Formatting
    fmt = [
        _af_req("A1", bold=True, font_size=12, fg=C_WHITE, bg=C_GA_H),
        _af_req("A4", bold=True, font_size=10, fg=C_WHITE, bg=C_NAVY),
        _af_req(f"A{WC_HDR_ROW}:E{WC_HDR_ROW}", bold=True, fg=C_DARK, bg=C_LBLUE, halign="CENTER"),
    ]
    for i in range(n_wc_rows):
        r  = WC_HDR_ROW + 1 + i
        bg = C_GA_A if i % 2 == 1 else C_GA
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


# ─────────────────────────── ALLOC TAB (04.2026) ───────────────────────────

def write_alloc_tab(ws, sh, wc_totals: dict[str, float],
                    ks13: dict[str, str], timestamp: str) -> None:
    ws.clear()

    nonzero_idx = _last_nonzero_idx(wc_totals)

    # ── Row constants ──────────────────────────────────────────────────────
    R_TITLE   = 1
    R_SEC_A   = 3
    R_REF     = 4
    R_EXCL    = 5    # ← INPUT CELL (yellow)
    R_VAT     = 6
    R_TOTAL   = 7
    R_METER   = 8
    R_PLANT   = 9
    R_PREPBY  = 10
    R_TS      = 11
    R_STATUS  = 12
                     # 13 blank
    R_SEC_B   = 14
    R_COL_HDR = 15
    R_DATA_S  = 16
    N_MACH    = len(MACHINES)
    R_DATA_E  = R_DATA_S + N_MACH - 1    # = 26
    R_SUB     = R_DATA_E + 1             # = 27
                     # 28 blank
    R_VAT_ROW = 29
    R_GRAND   = 30
                     # 31 blank
    R_SEC_C   = 32
    R_HDR_C   = 33
    R_JE_S    = 34

    denom = f"SUM($D${R_DATA_S}:$D${R_DATA_E})"
    COL_H = ["PK", "Machine Name", "Work Center", "GR Qty (kg)",
             "Alloc %", "Amount Excl.VAT (THB)", "Cost Center", "CC Name",
             "GL Account", "Tax", "Description (JE)"]
    n_cols = len(COL_H)   # 11

    rows: list[list] = [
        [f"ปันส่วนค่าไฟฟ้า GA — Asia Grand Plant 2200  |  {MONTH_DISPLAY}"],  # 1
        [],                                                                       # 2
        ["SECTION A — Bill Information"],                                         # 3
        ["Bill Ref",              "GA 04.26"],                                   # 4
        ["Amount excl VAT (THB)", 0.00],                                         # 5 ← INPUT
        ["VAT 7%",                f"=ROUND(B{R_EXCL}*0.07,2)"],                 # 6
        ["Total incl VAT",        f"=B{R_EXCL}+B{R_VAT}"],                      # 7
        ["Meter",                 "GRAND (WH4) — 22-33KV TOU"],                 # 8
        ["Plant",                 "GA 2200"],                                    # 9
        ["Prepared by",           "Claude Code"],                                # 10
        ["Timestamp",             timestamp],                                    # 11
        ["Status",                "Draft — Pending Review"],                     # 12
        [],                                                                       # 13
        [f"SECTION B — Machine Allocation by GR Qty (kg)  |  {MONTH_DISPLAY}"], # 14
        COL_H,                                                                    # 15
    ]

    for i, m in enumerate(MACHINES):
        r       = R_DATA_S + i
        qty_val = sum(wc_totals.get(wc, 0.0) for wc in m["wc"])
        wc_code = m["wc"][0] if m["wc"] else ""
        # VLOOKUP from PRD_2200 WC Summary — live cross-check
        qty = f"=IFERROR(VLOOKUP(C{r},'PRD_2200'!$A:$D,4,0),0)" if wc_code else 0
        cc_name = ks13.get(m["cc"], "—")
        is_last = (i == nonzero_idx)

        if qty_val == 0:
            amt = 0
        elif is_last:
            amt = f"=ROUND(B{R_EXCL},2)-SUM(F{R_DATA_S}:F{r-1})"
        else:
            amt = f"=IF(D{r}=0,0,ROUND($B${R_EXCL}*E{r},2))"

        alloc_f = f"=IF(D{r}=0,0,D{r}/{denom})"
        rows.append([
            m["pk"], m["name"], wc_code, qty,
            alloc_f, amt,
            m["cc"], cc_name, m["gl"], "V7",
            f"Elec {MONTH_LABEL} {m['name']}",
        ])

    # Subtotal
    rows.append(["", "Subtotal GA 2200", "",
                 f"=SUM(D{R_DATA_S}:D{R_DATA_E})",
                 f"=SUM(E{R_DATA_S}:E{R_DATA_E})",
                 f"=SUM(F{R_DATA_S}:F{R_DATA_E})",
                 "", "", "", "", ""])
    rows.append([])    # 28 blank

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
    rows.append([])    # 31 blank

    # Section C — JE
    rows.append([f"SECTION C — Journal Entry (SAP FB50)  |  {MONTH_LABEL}"])
    rows.append(["Itm", "D/C", "GL Account", "Cost Center", "Amount (THB)", "Tax Code", "Description"])

    itm = 1
    nonzero_machines = [(i, m) for i, m in enumerate(MACHINES)
                        if any(wc_totals.get(wc, 0) > 0 for wc in m["wc"])]
    for i, m in nonzero_machines:
        rows.append([itm, "Dr", m["gl"], m["cc"],
                     f"=F{R_DATA_S + i}", "V7",
                     f"Elec {MONTH_LABEL} {m['name']}"])
        itm += 1

    R_JE_VAT = R_JE_S + len(nonzero_machines)
    R_JE_CR  = R_JE_VAT + 1
    R_JE_BAL = R_JE_CR + 1

    rows.append([itm,     "Dr", GL_INPUT_TAX, "", f"=B{R_VAT}", "V7",
                 f"VAT Input Tax {MONTH_LABEL}"])
    rows.append([itm + 1, "Cr", GL_AP_TRADE,  "", f"=B{R_TOTAL}", "",
                 f"AP Elec GA {MONTH_LABEL}"])
    dr_range = f"E{R_JE_S}:E{R_JE_VAT}"
    rows.append(["", "Balance", "", "",
                 f"=SUM({dr_range})-E{R_JE_CR}", "",
                 f'=IF(ABS(SUM({dr_range})-E{R_JE_CR})<0.01,"BALANCED","ERROR")'])
    rows.append([])

    # Section D — Verification
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

    # ── Structural ────────────────────────────────────────────────────────
    struct = [
        _freeze(ws, rows=R_COL_HDR, cols=0),
        _merge(ws, R_TITLE - 1, 0, R_TITLE, n_cols),
        _merge(ws, R_SEC_A - 1, 0, R_SEC_A, n_cols),
        _merge(ws, R_SEC_B - 1, 0, R_SEC_B, n_cols),
        _merge(ws, R_SEC_C - 1, 0, R_SEC_C, 7),
        _merge(ws, R_SEC_D - 1, 0, R_SEC_D, n_cols),
        _row_h(ws, R_TITLE - 1, 36),
        _row_h(ws, R_SEC_A - 1, 26), _row_h(ws, R_SEC_B - 1, 26),
        _row_h(ws, R_COL_HDR - 1, 24), _row_h(ws, R_SUB - 1, 22),
        _row_h(ws, R_GRAND - 1, 26), _row_h(ws, R_SEC_C - 1, 26),
    ] + [_col_w(ws, i, w) for i, w in enumerate([35, 200, 80, 110, 85, 145, 80, 140, 80, 45, 240])]
    sh.batch_update({"requests": [_unmerge_all(ws)] + struct})

    # ── Cell formatting ───────────────────────────────────────────────────
    fmt = [
        _af_req(f"A{R_TITLE}", bold=True, font_size=12, fg=C_WHITE, bg=C_GA_H),
        _af_req(f"A{R_SEC_A}", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
        _af_req(f"A{R_SEC_B}", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
        _af_req(f"A{R_SEC_C}", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
        _af_req(f"A{R_SEC_D}", bold=True, font_size=10, fg=C_WHITE, bg=C_BLUE),
        _af_req(f"A{R_COL_HDR}:K{R_COL_HDR}", bold=True, fg=C_DARK, bg=C_LBLUE, halign="CENTER",
                borders={"bottom": _solid_border(C_BLUE, 2)}),
        *[_af_req(f"A{r}", bold=True, fg=C_DARK)
          for r in [R_REF, R_EXCL, R_VAT, R_TOTAL, R_METER, R_PLANT, R_PREPBY, R_TS, R_STATUS]],
        _af_req(f"B{R_EXCL}", number_format=NF_THB, bold=True, font_size=11,
                fg=C_NAVY, bg=C_YELLOW),
        _af_req(f"B{R_VAT}",   number_format=NF_THB),
        _af_req(f"B{R_TOTAL}", number_format=NF_THB, bold=True),
    ]

    for i, m in enumerate(MACHINES):
        r       = R_DATA_S + i
        bg      = C_GA_A if i % 2 == 1 else C_GA
        qty_val = sum(wc_totals.get(wc, 0.0) for wc in m["wc"])
        row_fg  = "#AAAAAA" if qty_val == 0 else C_BLACK
        fmt += [
            _af_req(f"A{r}:K{r}", fg=row_fg, bg=bg),
            _af_req(f"D{r}", number_format=NF_KG, halign="RIGHT", bg=bg),
            _af_req(f"E{r}", number_format=NF_PCT, halign="RIGHT", bg=bg),
            _af_req(f"F{r}", number_format=NF_THB, halign="RIGHT", bold=True,
                    fg=C_DARK if qty_val > 0 else "#AAAAAA", bg=bg),
        ]

    fmt += [
        _af_req(f"A{R_SUB}:K{R_SUB}", bold=True, bg=C_LBLUE, fg=C_DARK,
                borders={"top": _solid_border(C_BLUE), "bottom": _solid_border(C_BLUE)}),
        _af_req(f"D{R_SUB}", number_format=NF_KG, halign="RIGHT", bold=True, bg=C_LBLUE),
        _af_req(f"E{R_SUB}", number_format=NF_PCT, halign="RIGHT", bold=True, bg=C_LBLUE),
        _af_req(f"F{R_SUB}", number_format=NF_THB, halign="RIGHT", bold=True, bg=C_LBLUE),
        _af_req(f"A{R_VAT_ROW}:K{R_VAT_ROW}", bg=C_YELLOW, italic=True),
        _af_req(f"F{R_VAT_ROW}", number_format=NF_THB, halign="RIGHT", bg=C_YELLOW),
        _af_req(f"A{R_GRAND}:K{R_GRAND}", bold=True, bg=C_GREEN_BG, fg=C_GREEN_FG,
                borders={"top": _solid_border(C_BLUE, 2), "bottom": _solid_border(C_BLUE, 2)}),
        _af_req(f"F{R_GRAND}", number_format=NF_THB, halign="RIGHT", bold=True, bg=C_GREEN_BG),
        _af_req(f"A{R_HDR_C}:G{R_HDR_C}", bold=True, fg=C_DARK, bg=C_LBLUE, halign="CENTER"),
    ]

    for r in range(R_JE_S, R_JE_VAT + 1):
        fmt += [_af_req(f"A{r}:G{r}", bg=C_JE_DR),
                _af_req(f"B{r}", bold=True, fg="#2F5496", halign="CENTER", bg=C_JE_DR),
                _af_req(f"E{r}", number_format=NF_THB, halign="RIGHT", bg=C_JE_DR)]
    fmt += [
        _af_req(f"A{R_JE_CR}:G{R_JE_CR}", bg=C_JE_CR),
        _af_req(f"B{R_JE_CR}", bold=True, fg="#9C3600", halign="CENTER", bg=C_JE_CR),
        _af_req(f"E{R_JE_CR}", number_format=NF_THB, halign="RIGHT", bg=C_JE_CR),
        _af_req(f"A{R_HDR_D}:D{R_HDR_D}", bold=True, fg=C_DARK, bg=C_LBLUE, halign="CENTER"),
    ]
    for r in [R_VER_1, R_VER_2, R_VER_3]:
        fmt.append(_af_req(f"D{r}", halign="CENTER", bold=True))
    ws.batch_format(fmt)

    # ── Conditional formatting ────────────────────────────────────────────
    cond = []
    for r in [R_VER_1, R_VER_2, R_VER_3]:
        cond += [
            _cond_fmt(ws, r - 1, 3, r, 4, f'=$D${r}="PASS"', C_GREEN_BG, C_GREEN_FG),
            _cond_fmt(ws, r - 1, 3, r, 4, f'=$D${r}="FAIL"', C_RED_BG, C_RED_FG),
        ]
    cond += [
        _cond_fmt(ws, R_GRAND - 1, 10, R_GRAND, 11,
                  f'=$K${R_GRAND}="CHECK OK"', C_GREEN_BG, C_GREEN_FG),
        _cond_fmt(ws, R_GRAND - 1, 10, R_GRAND, 11,
                  f'=$K${R_GRAND}="CHECK FAIL"', C_RED_BG, C_RED_FG),
    ]
    sh.batch_update({"requests": cond})


# ─────────────────────────── DRY RUN CONSOLE ───────────────────────────────

def print_dry_run(wc_totals: dict[str, float]) -> None:
    total_qty = sum(wc_totals.values())
    sep = "=" * 70
    line = "-" * 70
    print(f"\n{sep}")
    print(f"  GA Electricity Workbook v2 -- {MONTH_LABEL}  [DRY RUN]")
    print(f"{sep}")
    print(f"\n{line}")
    print(f"  GA Plant 2200  |  Total GR Qty: {total_qty:,.0f} kg")
    print(f"  {'WC':<10} {'GR Qty (kg)':>14}  Machine")
    print(f"  {'-'*10} {'-'*14}  {'-'*30}")
    for m in MACHINES:
        qty = sum(wc_totals.get(wc, 0.0) for wc in m["wc"])
        wc_display = m["wc"][0] if m["wc"] else "(no WC)"
        note = " (no production)" if qty == 0 and m["wc"] else (" (no SAP WC)" if not m["wc"] else "")
        print(f"  {wc_display:<10} {qty:>14,.0f}  {m['name']}{note}")
    print(f"\n{sep}")
    print(f"  Tab order: PRD_2200 | {MONTH_LABEL}")
    print(f"  After script: enter bill amount excl VAT in B5 of {MONTH_LABEL} tab")
    print(f"{sep}\n")


# ─────────────────────────── MAIN ──────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="ปันส่วนค่าไฟฟ้า GA v2")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only — do not write to Google Sheet")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    print("[1/4] Loading KS13 Master CC...")
    ks13 = load_ks13(KS13_PATH)

    print("[2/4] Loading PRD file...")
    df_raw, wc_totals = load_prd(PRD_PATH)

    print("[3/4] Validating CC codes...")
    validate_ccs(ks13)

    print_dry_run(wc_totals)

    if args.dry_run:
        print("[4/4] --dry-run — skipped Google Sheet write.")
        return

    print("[4/4] Writing to Google Sheet...")
    gc = get_gspread_client()
    sh = (gc.open_by_key(SHEET_ID) if SHEET_ID
          else open_or_create_sheet(gc, SHEET_NAME, folder_id=DRIVE_FOLDERS.get("working")))

    # Ensure tab order: PRD_2200 first, then month tab
    ws_prd   = get_or_add_worksheet(sh, "PRD_2200")
    ws_alloc = get_or_add_worksheet(sh, MONTH_LABEL)

    print("  Writing PRD_2200...")
    write_prd_tab(ws_prd, sh, df_raw, wc_totals, ks13,
                  str(PRD_PATH), timestamp)

    print(f"  Writing {MONTH_LABEL}...")
    write_alloc_tab(ws_alloc, sh, wc_totals, ks13, timestamp)

    url = sh.url
    print(f"\n  Google Sheet: {url}")

    # Analytics log
    try:
        if ANALYTICS_LOG_SHEET_ID:
            log_sh = gc.open_by_key(ANALYTICS_LOG_SHEET_ID)
            from utils import append_analytics_log
            append_analytics_log(log_sh.sheet1, {
                "date": datetime.now().strftime("%d/%m/%Y"),
                "type": "ElectricityAlloc",
                "name": SHEET_NAME,
                "source": PRD_PATH.name,
                "period": MONTH_LABEL,
                "output_file": url,
                "status": "Draft",
            })
    except Exception as e:
        print(f"  Warning: analytics_log — {e}")

    print("\n[5/4] Done.")
    print(f"  Sheet URL: {url}")
    print("  Next steps:")
    print(f"    1. Open Sheet and enter bill amount excl VAT in {MONTH_LABEL} tab B5")
    print(f"    2. Verify SECTION D rows show PASS / CHECK OK")


if __name__ == "__main__":
    main()
