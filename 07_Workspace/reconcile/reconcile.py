"""
Workflow 1 — Reconciliation Runner
Prepared by: Claude Code

Usage:
    python scripts/reconcile.py \
        --name "AP_vs_Bank" \
        --sheet-a "SHEET_ID_A" \
        --sheet-b "SHEET_ID_B" \
        --keys "invoice_number,amount" \
        --date-col "doc_date" \
        --date-tol 3

    หรือ import ใช้ใน script อื่น:
        from scripts.reconcile import run_reconciliation
"""

import sys
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from utils import (
    get_gspread_client,
    open_or_create_sheet, setup_recon_sheet,
    clear_and_write, write_summary_tab,
    append_recon_log,
    reconcile, recon_summary, check_recon_warnings,
    fmt_number, fmt_date,
)
from config.settings import (
    DRIVE_FOLDERS,
    RECON_LOG_SHEET_ID,
    DEFAULT_MATCH_KEYS,
)

PREPARED_BY = "Claude Code"


def load_sheet_to_df(gc, sheet_id: str) -> pd.DataFrame:
    """โหลด Google Sheet → DataFrame (ใช้ row แรกเป็น header)"""
    sh = gc.open_by_key(sheet_id)
    ws = sh.sheet1
    data = ws.get_all_records()
    return pd.DataFrame(data)


def run_reconciliation(
    name: str,
    sheet_id_a: str,
    sheet_id_b: str,
    key_cols: list[str],
    amount_col: str = "amount",
    date_col: str | None = None,
    date_tolerance_days: int = 0,
    dry_run: bool = False,
) -> dict:
    """
    Main reconciliation runner.
    Returns summary dict.
    """
    gc = get_gspread_client()
    timestamp = datetime.now()
    output_name = f"RECON_{timestamp.strftime('%Y%m%d')}_{name}"

    print(f"\n{'='*60}")
    print(f"Reconciliation: {name}")
    print(f"Timestamp: {fmt_date(timestamp)}")
    print(f"{'='*60}")

    # 1. โหลดข้อมูล
    print("\n[1/6] Loading Source A...")
    df_a = load_sheet_to_df(gc, sheet_id_a)
    print(f"      → {len(df_a):,} records")

    print("[2/6] Loading Source B...")
    df_b = load_sheet_to_df(gc, sheet_id_b)
    print(f"      → {len(df_b):,} records")

    # 2. ตรวจสอบ duplicate keys
    for label, df in [("A", df_a), ("B", df_b)]:
        dups = df.duplicated(subset=key_cols, keep=False)
        if dups.any():
            print(f"\nWARNING: พบ duplicate key ใน Source {label} ({dups.sum()} records)")
            print("กรุณาตรวจสอบก่อนดำเนินการต่อ")
            return {"error": f"duplicate_key_source_{label}"}

    # 3. Reconcile
    print("[3/6] Running reconciliation...")
    result = reconcile(
        df_a, df_b,
        key_cols=key_cols,
        amount_col=amount_col,
        date_col=date_col,
        date_tolerance_days=date_tolerance_days,
    )
    summary = recon_summary(result)

    print(f"\n      Match Rate: {summary['Match_Rate']}")
    print(f"      Matched:     {summary['Matched']:,}")
    print(f"      Unmatched_A: {summary['Unmatched_A']:,}")
    print(f"      Unmatched_B: {summary['Unmatched_B']:,}")
    print(f"      Diff:        {summary['Diff']:,}")

    # 4. ตรวจ warnings
    warnings = check_recon_warnings(result, summary)
    if warnings:
        print("\n>>> WARNINGS <<<")
        for w in warnings:
            print(f"    ! {w}")
        print("\nหยุดดำเนินการ — กรุณาตรวจสอบและยืนยันก่อน")
        return {"warnings": warnings, "summary": summary}

    if dry_run:
        print("\n[DRY RUN] ไม่ได้เขียนผลลงใน Google Sheets")
        return {"summary": summary, "result": result}

    # 5. เขียนผลลงใน Google Sheets
    print("[4/6] Creating output sheet...")
    sh = open_or_create_sheet(gc, output_name, folder_id=DRIVE_FOLDERS.get("working"))
    tabs = setup_recon_sheet(sh)

    def df_to_rows(df: pd.DataFrame) -> list:
        return df.values.tolist()

    print("[5/6] Writing data to tabs...")
    # Source_A
    clear_and_write(tabs["Source_A"], list(df_a.columns), df_to_rows(df_a))
    # Source_B
    clear_and_write(tabs["Source_B"], list(df_b.columns), df_to_rows(df_b))
    # Matched
    m = result["matched"]
    clear_and_write(tabs["Matched"], list(m.columns), df_to_rows(m))
    # Unmatched_A
    ua = result["unmatched_a"]
    clear_and_write(tabs["Unmatched_A"], list(ua.columns), df_to_rows(ua))
    # Unmatched_B
    ub = result["unmatched_b"]
    clear_and_write(tabs["Unmatched_B"], list(ub.columns), df_to_rows(ub))
    # Diff
    d = result["diff"]
    clear_and_write(tabs["Diff"], list(d.columns), df_to_rows(d))
    # Summary
    narrative = (
        f"ผลการ Reconcile: {name}\n"
        f"Match Rate {summary['Match_Rate']} "
        f"({summary['Matched']:,} จาก {summary['Total_A']:,} รายการ)\n"
        f"รายการที่ไม่ match: {summary['Unmatched_A']:,} (ฝั่ง A) | "
        f"{summary['Unmatched_B']:,} (ฝั่ง B)\n"
        f"รายการที่ตัวเลขต่าง: {summary['Diff']:,}"
    )
    write_summary_tab(tabs["Summary"], f"Reconciliation: {name}", summary, narrative)

    print(f"      Output: {output_name}")
    print(f"      URL: {sh.url}")

    # 6. Update log
    print("[6/6] Updating reconciliation log...")
    if RECON_LOG_SHEET_ID:
        try:
            log_sh = gc.open_by_key(RECON_LOG_SHEET_ID)
            log_ws = log_sh.sheet1
            append_recon_log(log_ws, {
                "date": fmt_date(timestamp),
                "source_a": sheet_id_a,
                "source_b": sheet_id_b,
                "output_file": output_name,
                "total_a": summary["Total_A"],
                "total_b": summary["Total_B"],
                "matched": summary["Matched"],
                "unmatched": summary["Unmatched_A"],
                "diff": summary["Diff"],
                "match_rate": summary["Match_Rate"],
                "status": "Draft",
            })
        except Exception as e:
            print(f"      Warning: ไม่สามารถอัพเดท log ได้ — {e}")

    print(f"\n{'='*60}")
    print("DONE — Status: Draft (รอ human review)")
    print(f"{'='*60}\n")

    return {"summary": summary, "output_name": output_name, "url": sh.url}


# ───────────────────────── CLI Entry Point ─────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Finance Workspace — Reconciliation Runner")
    parser.add_argument("--name",      required=True,  help="ชื่องาน (ใช้ใน output filename)")
    parser.add_argument("--sheet-a",   required=True,  help="Google Sheet ID ของ Source A")
    parser.add_argument("--sheet-b",   required=True,  help="Google Sheet ID ของ Source B")
    parser.add_argument("--keys",      required=True,  help="match key columns คั่นด้วย comma")
    parser.add_argument("--amount",    default="amount", help="ชื่อ column amount (default: amount)")
    parser.add_argument("--date-col",  default=None,   help="ชื่อ column วันที่ (optional)")
    parser.add_argument("--date-tol",  default=0, type=int, help="date tolerance (วัน)")
    parser.add_argument("--dry-run",   action="store_true", help="ทดสอบโดยไม่เขียนลง Sheets")
    args = parser.parse_args()

    run_reconciliation(
        name=args.name,
        sheet_id_a=args.sheet_a,
        sheet_id_b=args.sheet_b,
        key_cols=args.keys.split(","),
        amount_col=args.amount,
        date_col=args.date_col,
        date_tolerance_days=args.date_tol,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
