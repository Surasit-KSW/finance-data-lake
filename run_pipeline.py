"""
run_pipeline.py — Finance Data Lake: Master Pipeline Runner
============================================================
ใช้งาน:
  python run_pipeline.py --help
  python run_pipeline.py --all
  python run_pipeline.py --init-db
  python run_pipeline.py --layer silver --domain sales
  python run_pipeline.py --layer silver --domain production --year 2025
  python run_pipeline.py --layer gold
  python run_pipeline.py --dashboard

ตัวเลือก:
  --all                    รันทุก layer ตามลำดับ (silver → gold → init-db)
  --init-db                สร้าง/อัพเดต DuckDB views
  --layer [silver|gold]    รัน ETL layer ที่ระบุ
  --domain [sales|production|gl|ar]   เฉพาะ domain นี้ (ใช้กับ --layer silver)
  --year YYYY              เฉพาะปีนี้ (ใช้กับ --domain sales หรือ production)
  --dashboard              เปิด Streamlit dashboard
"""

import argparse
import subprocess
import sys
import os
import time

# ── UTF-8 output สำหรับ Windows console (cp874 ไม่รองรับ emoji/box chars) ──
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
# ส่ง PYTHONUTF8=1 ไปยัง subprocess ทั้งหมดด้วย
os.environ['PYTHONUTF8'] = '1'

# ============================================================
# Config
# ============================================================
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

PIPELINES = os.path.join(PROJECT_ROOT, "04_Data_Pipelines")

SCRIPTS = {
    "init_db":          os.path.join(PIPELINES, "init_duckdb.py"),

    # Silver transforms
    "silver_sales":     os.path.join(PIPELINES, "silver_transform", "etl_sales.py"),
    "silver_production": os.path.join(PIPELINES, "silver_transform", "etl_production.py"),
    "silver_gl":        os.path.join(PIPELINES, "silver_transform", "etl_gl.py"),
    "silver_ar":        os.path.join(PIPELINES, "silver_transform", "etl_ar.py"),

    # Gold aggregations
    "gold_gl_summary":  os.path.join(PIPELINES, "gold_aggregation", "create_gold_summary.py"),

    # Dashboard
    "dashboard":        os.path.join(PROJECT_ROOT, "05_Dashboards", "app_01_audit_analytics.py"),
}

# ============================================================
# Helpers
# ============================================================
def run(script_key: str, extra_args: list = None) -> bool:
    script_path = SCRIPTS.get(script_key)
    if not script_path or not os.path.exists(script_path):
        print(f"  ⚠️  Script ไม่พบ: {script_path}")
        return False

    cmd = [PYTHON, script_path] + (extra_args or [])
    print(f"\n{'─'*55}")
    print(f"  ▶  {script_key}")
    print(f"     {' '.join(cmd)}")
    print(f"{'─'*55}")

    start = time.time()
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    elapsed = time.time() - start

    if result.returncode == 0:
        print(f"\n  ✅ เสร็จสิ้นใน {elapsed:.1f}s")
        return True
    else:
        print(f"\n  ❌ พบ Error (returncode={result.returncode})")
        return False


def run_dashboard():
    script_path = SCRIPTS["dashboard"]
    print(f"\n🖥️  เปิด Streamlit dashboard...")
    print(f"   streamlit run {script_path}")
    subprocess.run(["streamlit", "run", script_path], cwd=PROJECT_ROOT)


# ============================================================
# Main
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Finance Data Lake — Master Pipeline Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
ตัวอย่าง:
  python run_pipeline.py --all
  python run_pipeline.py --init-db
  python run_pipeline.py --layer silver
  python run_pipeline.py --layer silver --domain sales --year 2025
  python run_pipeline.py --layer gold
  python run_pipeline.py --dashboard
""")
    parser.add_argument("--all",      action="store_true", help="รัน silver + gold + init-db ทั้งหมด")
    parser.add_argument("--init-db",  action="store_true", help="สร้าง/อัพเดต DuckDB views")
    parser.add_argument("--layer",    choices=["silver", "gold"], help="รัน ETL layer ที่ระบุ")
    parser.add_argument("--domain",   choices=["sales", "production", "gl", "ar"], help="เฉพาะ domain")
    parser.add_argument("--year",     type=str, help="เฉพาะปีนี้ เช่น 2025")
    parser.add_argument("--dashboard", action="store_true", help="เปิด Streamlit dashboard")

    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        return

    print(f"\n{'='*55}")
    print(f"  Finance Data Lake — Pipeline Runner")
    print(f"  Project: {PROJECT_ROOT}")
    print(f"{'='*55}")

    success_count = 0
    fail_count = 0

    def track(ok: bool):
        nonlocal success_count, fail_count
        if ok:
            success_count += 1
        else:
            fail_count += 1

    # ── Dashboard ──────────────────────────────────────────
    if args.dashboard:
        run_dashboard()
        return

    # ── All ────────────────────────────────────────────────
    if args.all:
        print("\n🚀 โหมด --all: รัน Silver → Gold → DuckDB")
        for key in ["silver_sales", "silver_production", "silver_gl", "silver_ar"]:
            track(run(key))
        track(run("gold_gl_summary"))
        track(run("init_db"))

    # ── Layer ──────────────────────────────────────────────
    elif args.layer:
        year_args = [args.year] if args.year else []

        if args.layer == "silver":
            if args.domain:
                key = f"silver_{args.domain}"
                track(run(key, year_args))
            else:
                print("\n🚀 รัน Silver layer ทั้งหมด")
                for key in ["silver_sales", "silver_production", "silver_gl", "silver_ar"]:
                    track(run(key, year_args if key in ["silver_sales", "silver_production"] else []))

        elif args.layer == "gold":
            print("\n🚀 รัน Gold layer ทั้งหมด")
            track(run("gold_gl_summary"))

    # ── Init DB ────────────────────────────────────────────
    elif args.init_db:
        track(run("init_db"))

    # ── Summary ────────────────────────────────────────────
    total = success_count + fail_count
    if total > 0:
        print(f"\n{'='*55}")
        print(f"  สรุปผล: ✅ {success_count}/{total} steps สำเร็จ", end="")
        if fail_count:
            print(f"  ❌ {fail_count} พบ Error")
        else:
            print()
        print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
