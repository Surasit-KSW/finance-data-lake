"""
Workflow 3 — Analytics Runner
Prepared by: Claude Code

Supports:
  - trend      : Trend Analysis (MoM, YoY, peak/trough)
  - pattern    : Outlier/Pattern Detection
  - dashboard  : KPI Dashboard
  - forecast   : Moving Average Forecast
"""

import sys
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from utils import (
    get_gspread_client,
    open_or_create_sheet, get_or_add_worksheet,
    clear_and_write, write_summary_tab,
    append_analytics_log,
    detect_outliers, moving_average_forecast,
    mom_change, yoy_change,
    fmt_number, fmt_date,
)
from config.settings import (
    DRIVE_FOLDERS,
    ANALYTICS_LOG_SHEET_ID,
    FORECAST_DEFAULT_HORIZON,
    FORECAST_MIN_MONTHS_MA,
    FORECAST_MIN_MONTHS_LINEAR,
)

PREPARED_BY = "Claude Code"


def load_sheet_to_df(gc, sheet_id: str, tab_name: str | None = None) -> pd.DataFrame:
    sh = gc.open_by_key(sheet_id)
    ws = sh.worksheet(tab_name) if tab_name else sh.sheet1
    return pd.DataFrame(ws.get_all_records())


# ─────────────────────── Trend Analysis ───────────────────────────────

def run_trend(
    gc,
    name: str,
    sheet_id: str,
    date_col: str,
    amount_col: str,
    period: str,
) -> dict:
    timestamp = datetime.now()
    output_name = f"TREND_{timestamp.strftime('%Y%m%d')}_{name}"

    df = load_sheet_to_df(gc, sheet_id)
    df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")
    df[amount_col] = pd.to_numeric(df[amount_col], errors="coerce").round(2)
    df = df.dropna(subset=[date_col, amount_col])

    # Check minimum data
    months_count = df[date_col].dt.to_period("M").nunique()
    if months_count < 6:
        print(f"WARNING: มีข้อมูลเพียง {months_count} เดือน (ต้องการอย่างน้อย 6 เดือน)")
        print("จะดำเนินการต่อไหม? (y/n)")
        if input().strip().lower() != "y":
            return {"error": "insufficient_data"}

    # Monthly aggregate
    monthly = (
        df.set_index(date_col)
        .resample("ME")[amount_col]
        .sum()
        .round(2)
        .rename("amount")
    )
    monthly_df = monthly.reset_index()
    monthly_df["MoM_%"] = mom_change(monthly).values.round(2)
    monthly_df["YoY_%"] = yoy_change(monthly).values.round(2)

    # Peak / Trough
    peak_idx   = monthly.idxmax()
    trough_idx = monthly.idxmin()
    narrative = (
        f"วิเคราะห์ Trend: {name} | ช่วงเวลา: {period}\n"
        f"Peak: {peak_idx.strftime('%m/%Y')} ({fmt_number(monthly[peak_idx])} บาท)\n"
        f"Trough: {trough_idx.strftime('%m/%Y')} ({fmt_number(monthly[trough_idx])} บาท)\n"
        f"MoM เฉลี่ย: {monthly_df['MoM_%'].mean():.1f}%\n"
        f"YoY เฉลี่ย: {monthly_df['YoY_%'].mean():.1f}%"
    )

    # Write to Sheets
    sh = open_or_create_sheet(gc, output_name, folder_id=DRIVE_FOLDERS.get("working"))
    for tab, headers, rows in [
        ("Raw_Data", list(df.columns), df.values.tolist()),
        ("Monthly", list(monthly_df.columns), monthly_df.values.tolist()),
    ]:
        ws = get_or_add_worksheet(sh, tab)
        clear_and_write(ws, headers, rows)

    summary_ws = get_or_add_worksheet(sh, "Summary")
    stats = {
        "ช่วงเวลา": period,
        "จำนวนเดือน": months_count,
        "Peak": f"{peak_idx.strftime('%m/%Y')} | {fmt_number(monthly[peak_idx])} บาท",
        "Trough": f"{trough_idx.strftime('%m/%Y')} | {fmt_number(monthly[trough_idx])} บาท",
        "MoM เฉลี่ย": f"{monthly_df['MoM_%'].mean():.1f}%",
    }
    write_summary_tab(summary_ws, f"Trend Analysis: {name}", stats, narrative)

    _log_analytics(gc, "Trend", name, sheet_id, period, output_name, timestamp)
    print(f"TREND output: {sh.url}")
    return {"output_name": output_name, "url": sh.url}


# ─────────────────────── Pattern Detection ────────────────────────────

def run_pattern(
    gc,
    name: str,
    sheet_id: str,
    amount_col: str,
    group_col: str | None,
    period: str,
) -> dict:
    timestamp = datetime.now()
    output_name = f"PATTERN_{timestamp.strftime('%Y%m%d')}_{name}"

    df = load_sheet_to_df(gc, sheet_id)
    df[amount_col] = pd.to_numeric(df[amount_col], errors="coerce").round(2)

    outliers = detect_outliers(df, amount_col=amount_col, group_col=group_col)

    # Check if outliers > 30%
    if len(outliers) > len(df) * 0.30:
        print(f"WARNING: outlier {len(outliers)/len(df):.0%} ของข้อมูล อาจมีปัญหาข้อมูล — จะดำเนินการต่อไหม? (y/n)")
        if input().strip().lower() != "y":
            return {"error": "too_many_outliers"}

    # Stats per group
    if group_col:
        stats_df = df.groupby(group_col)[amount_col].agg(
            ["mean", "median", "std", "min", "max", "count"]
        ).round(2).reset_index()
    else:
        stats_df = pd.DataFrame([{
            "mean":   df[amount_col].mean(),
            "median": df[amount_col].median(),
            "std":    df[amount_col].std(),
            "min":    df[amount_col].min(),
            "max":    df[amount_col].max(),
            "count":  len(df),
        }]).round(2)

    sh = open_or_create_sheet(gc, output_name, folder_id=DRIVE_FOLDERS.get("working"))
    for tab, headers, rows in [
        ("Raw_Data", list(df.columns), df.values.tolist()),
        ("Stats", list(stats_df.columns), stats_df.values.tolist()),
        ("Outliers", list(outliers.columns), outliers.values.tolist()),
    ]:
        ws = get_or_add_worksheet(sh, tab)
        clear_and_write(ws, headers, rows)

    summary_ws = get_or_add_worksheet(sh, "Summary")
    narrative = (
        f"Pattern Detection: {name}\n"
        f"พบ {len(outliers):,} outlier จากทั้งหมด {len(df):,} รายการ ({len(outliers)/len(df):.1%})\n"
        f"outlier สูงสุด: {fmt_number(outliers[amount_col].max())} บาท"
    )
    write_summary_tab(summary_ws, f"Pattern: {name}", {"Outliers": len(outliers)}, narrative)

    _log_analytics(gc, "Pattern", name, sheet_id, period, output_name, timestamp)
    print(f"PATTERN output: {sh.url}")
    return {"output_name": output_name, "url": sh.url}


# ─────────────────────── Forecast ─────────────────────────────────────

def run_forecast(
    gc,
    name: str,
    sheet_id: str,
    date_col: str,
    amount_col: str,
    horizon: int,
    period: str,
) -> dict:
    timestamp = datetime.now()
    output_name = f"FORECAST_{timestamp.strftime('%Y%m%d')}_{name}"

    df = load_sheet_to_df(gc, sheet_id)
    df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")
    df[amount_col] = pd.to_numeric(df[amount_col], errors="coerce").round(2)
    df = df.dropna(subset=[date_col, amount_col])

    monthly = df.set_index(date_col).resample("ME")[amount_col].sum().round(2)
    n_months = len(monthly)

    if n_months < FORECAST_MIN_MONTHS_MA:
        print(f"WARNING: ข้อมูลเพียง {n_months} เดือน ต้องการอย่างน้อย {FORECAST_MIN_MONTHS_MA} เดือน")
        return {"error": "insufficient_data"}

    # เลือก method
    window = 3 if n_months < FORECAST_MIN_MONTHS_LINEAR else 6
    method_desc = f"Moving Average ({window} เดือน)"

    fc, fc_lower, fc_upper = moving_average_forecast(monthly, horizon=horizon, window=window)

    # สร้าง forecast dates
    last_date = monthly.index[-1]
    fc_dates  = pd.date_range(start=last_date, periods=horizon + 1, freq="ME")[1:]
    fc_df = pd.DataFrame({
        "Month":     fc_dates.strftime("%m/%Y"),
        "Forecast":  fc.values,
        "Lower_90%": fc_lower.values,
        "Upper_90%": fc_upper.values,
    })

    sh = open_or_create_sheet(gc, output_name, folder_id=DRIVE_FOLDERS.get("working"))
    for tab, headers, rows in [
        ("Historical", list(monthly.reset_index().rename(columns={date_col: "Month"}).columns),
         monthly.reset_index().values.tolist()),
        ("Forecast", list(fc_df.columns), fc_df.values.tolist()),
    ]:
        ws = get_or_add_worksheet(sh, tab)
        clear_and_write(ws, headers, rows)

    summary_ws = get_or_add_worksheet(sh, "Summary")
    narrative = (
        f"Forecast: {name}\n"
        f"Method: {method_desc}\n"
        f"ข้อมูลย้อนหลัง: {n_months} เดือน\n"
        f"Forecast ถัดไป {horizon} เดือน\n\n"
        f"Assumption: ไม่มี seasonality / ไม่มี structural break\n"
        f"Confidence interval: 90%\n\n"
        "Forecast เพื่อประกอบการตัดสินใจ ไม่ใช่ตัวเลขแน่นอน"
    )
    write_summary_tab(summary_ws, f"Forecast: {name}", {"Method": method_desc, "Horizon": f"{horizon} เดือน"}, narrative)

    _log_analytics(gc, "Forecast", name, sheet_id, period, output_name, timestamp)
    print(f"FORECAST output: {sh.url}")
    return {"output_name": output_name, "url": sh.url}


# ─────────────────────── Log Helper ───────────────────────────────────

def _log_analytics(gc, typ, name, source, period, output_file, timestamp):
    if not ANALYTICS_LOG_SHEET_ID:
        return
    try:
        sh = gc.open_by_key(ANALYTICS_LOG_SHEET_ID)
        append_analytics_log(sh.sheet1, {
            "date": fmt_date(timestamp),
            "type": typ,
            "name": name,
            "source": source,
            "period": period,
            "output_file": output_file,
            "status": "Draft",
        })
    except Exception as e:
        print(f"Warning: ไม่สามารถอัพเดท analytics log ได้ — {e}")


# ─────────────────────── CLI ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Finance Workspace — Analytics Runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # trend
    t = sub.add_parser("trend")
    t.add_argument("--name",     required=True)
    t.add_argument("--sheet",    required=True)
    t.add_argument("--date-col", default="date")
    t.add_argument("--amount",   default="amount")
    t.add_argument("--period",   default="")

    # pattern
    p = sub.add_parser("pattern")
    p.add_argument("--name",      required=True)
    p.add_argument("--sheet",     required=True)
    p.add_argument("--amount",    default="amount")
    p.add_argument("--group-col", default=None)
    p.add_argument("--period",    default="")

    # forecast
    f = sub.add_parser("forecast")
    f.add_argument("--name",     required=True)
    f.add_argument("--sheet",    required=True)
    f.add_argument("--date-col", default="date")
    f.add_argument("--amount",   default="amount")
    f.add_argument("--horizon",  default=FORECAST_DEFAULT_HORIZON, type=int)
    f.add_argument("--period",   default="")

    args = parser.parse_args()
    gc = get_gspread_client()

    if args.cmd == "trend":
        run_trend(gc, args.name, args.sheet, args.date_col, args.amount, args.period)
    elif args.cmd == "pattern":
        run_pattern(gc, args.name, args.sheet, args.amount, args.group_col, args.period)
    elif args.cmd == "forecast":
        run_forecast(gc, args.name, args.sheet, args.date_col, args.amount, args.horizon, args.period)


if __name__ == "__main__":
    main()
