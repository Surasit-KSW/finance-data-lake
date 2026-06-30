"""
orchestrator.py — Finance Data Lake: Config-Driven Pipeline Runner
============================================================
Replaces run_pipeline.py. Reads company_registry.yaml.

ใช้งาน:
  python orchestrator.py --help
  python orchestrator.py --all
  python orchestrator.py --company AMC --layer silver
  python orchestrator.py --company GA --domain gl --year 2026
  python orchestrator.py --domain gl --layer silver
  python orchestrator.py --init-db
  python orchestrator.py --all --include-gold
  python orchestrator.py --dashboard
"""
import sys
import os
import time
import argparse
import subprocess
from pathlib import Path

# ── UTF-8 output สำหรับ Windows console ──────────────────────────────────────
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
os.environ['PYTHONUTF8'] = '1'

PROJECT_ROOT = Path(__file__).resolve().parent
PIPELINES_DIR = PROJECT_ROOT / "04_Data_Pipelines"
PYTHON = sys.executable

# ── sys.path setup สำหรับ import core ────────────────────────────────────────
sys.path.insert(0, str(PIPELINES_DIR))
from core.registry import CompanyRegistry

REGISTRY = CompanyRegistry(
    config_path=PROJECT_ROOT / "08_Config" / "company_registry.yaml",
    project_root=PROJECT_ROOT,
)

# Mapping: domain → ETL script path
DOMAIN_SCRIPTS = {
    "gl":         PIPELINES_DIR / "silver_transform" / "etl_gl.py",
    "sales":      PIPELINES_DIR / "silver_transform" / "etl_sales.py",
    "production": PIPELINES_DIR / "silver_transform" / "etl_production.py",
    "ar":         PIPELINES_DIR / "silver_transform" / "etl_ar.py",
}

GOLD_SCRIPTS = {
    "gl_summary": PIPELINES_DIR / "gold_aggregation" / "create_gold_summary.py",
}

INIT_DB_SCRIPT = PIPELINES_DIR / "init_duckdb.py"
DASHBOARD_SCRIPT = PROJECT_ROOT / "05_Dashboards" / "app_01_audit_analytics.py"


# ── Helpers ──────────────────────────────────────────────────────────────────

def run_script(script: Path, extra_args: list = None, label: str = "") -> bool:
    """Run a Python script via subprocess. Returns True on success."""
    cmd = [PYTHON, str(script)] + (extra_args or [])
    label = label or script.name
    print(f"\n{'─'*55}")
    print(f"  ▶  {label}")
    print(f"{'─'*55}")
    start = time.time()
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    elapsed = time.time() - start
    if result.returncode == 0:
        print(f"\n  ✅ {label} — done in {elapsed:.1f}s")
        return True
    else:
        print(f"\n  ❌ {label} — failed (returncode={result.returncode})")
        return False


def run_silver_for_company(company_name: str, domain: str = None, year: int = None):
    """Run silver ETL for one company. Returns list of (label, success) tuples."""
    try:
        company = REGISTRY.get(company_name)
    except KeyError as e:
        print(f"❌ {e}")
        return []

    domains = [domain] if domain else list(company["bronze_paths"].keys())
    results = []

    for dom in domains:
        if dom not in DOMAIN_SCRIPTS:
            print(f"  ⚠️  No ETL script for domain '{dom}' — skipping")
            continue
        if dom not in company["bronze_paths"]:
            print(f"  ⚠️  Company '{company_name}' has no Bronze path for '{dom}' — skipping")
            continue

        args = ["--company", company_name]
        if year:
            args += ["--year", str(year)]

        label = f"[{company_name}] {dom}"
        ok = run_script(DOMAIN_SCRIPTS[dom], args, label)
        results.append((label, ok))

    return results


def print_summary(results: list):
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    total = len(results)
    print(f"\n{'='*55}")
    print(f"  สรุปผล: ✅ {passed}/{total} tasks สำเร็จ", end="")
    if failed:
        print(f"  ❌ {failed} พบ Error")
    else:
        print()
    print(f"{'='*55}\n")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Finance Data Lake — Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
ตัวอย่าง:
  python orchestrator.py --all
  python orchestrator.py --company AMC --layer silver
  python orchestrator.py --company GA --domain gl --year 2026
  python orchestrator.py --domain gl --layer silver
  python orchestrator.py --init-db
  python orchestrator.py --all --include-gold
""")
    parser.add_argument("--all",          action="store_true", help="รัน silver + gold + init-db ทั้งหมด")
    parser.add_argument("--init-db",      action="store_true", help="สร้าง/อัพเดต DuckDB views")
    parser.add_argument("--layer",        choices=["silver", "gold"], help="รัน layer ที่ระบุ")
    parser.add_argument("--domain",       choices=["gl", "sales", "production", "ar"], help="เฉพาะ domain นี้")
    parser.add_argument("--company",      help="เฉพาะ company นี้ เช่น AMC, GA")
    parser.add_argument("--year",         type=int, help="เฉพาะปีนี้ เช่น 2026")
    parser.add_argument("--include-gold", action="store_true", help="รัน gold layer หลัง silver")
    parser.add_argument("--dashboard",    action="store_true", help="เปิด Streamlit dashboard")
    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        return

    print(f"\n{'='*55}")
    print(f"  Finance Data Lake — Orchestrator")
    print(f"  Project: {PROJECT_ROOT}")
    print(f"{'='*55}")

    all_results = []

    # ── Dashboard ──────────────────────────────────────────────
    if args.dashboard:
        subprocess.run(["streamlit", "run", str(DASHBOARD_SCRIPT)], cwd=str(PROJECT_ROOT))
        return

    # ── Silver tasks ───────────────────────────────────────────
    companies_to_run = [args.company] if args.company else REGISTRY.all_companies()

    run_silver = args.all or args.layer == "silver" or (args.domain and not args.layer)

    if run_silver:
        print(f"\n🚀 Silver layer — companies: {companies_to_run}")
        for company_name in companies_to_run:
            results = run_silver_for_company(company_name, domain=args.domain, year=args.year)
            all_results.extend(results)

    # ── Gold tasks ─────────────────────────────────────────────
    run_gold = args.all or args.layer == "gold" or args.include_gold
    if run_gold:
        print(f"\n🚀 Gold layer")
        for key, script in GOLD_SCRIPTS.items():
            ok = run_script(script, label=f"[gold] {key}")
            all_results.append((f"gold_{key}", ok))

    # ── Init DB ────────────────────────────────────────────────
    run_init = args.all or args.init_db
    if run_init:
        ok = run_script(INIT_DB_SCRIPT, label="init-db")
        all_results.append(("init-db", ok))

    if all_results:
        print_summary(all_results)


if __name__ == "__main__":
    main()
