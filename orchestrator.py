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

# ── sys.path setup สำหรับ import core + ETL classes ──────────────────────────
sys.path.insert(0, str(PIPELINES_DIR))

from core.registry import CompanyRegistry
from silver_transform.etl_gl import GLTransformETL
from silver_transform.etl_sales import SalesTransformETL
from silver_transform.etl_production import ProductionTransformETL
from silver_transform.etl_ar import ARTransformETL

REGISTRY = CompanyRegistry(
    config_path=PROJECT_ROOT / "08_Config" / "company_registry.yaml",
    project_root=PROJECT_ROOT,
)

SILVER_PATH = PROJECT_ROOT / "02_Silver_Cleaned"

# Mapping: domain → ETL class
ETL_CLASSES = {
    "gl":         GLTransformETL,
    "sales":      SalesTransformETL,
    "production": ProductionTransformETL,
    "ar":         ARTransformETL,
}

# Mapping: domain → constructor kwarg name for the bronze path
BRONZE_PATH_KWARG = {
    "gl":         "bronze_gl_path",
    "sales":      "bronze_sales_path",
    "production": "bronze_prod_path",
    "ar":         "bronze_ar_path",
}

GOLD_SCRIPTS = {
    # Group 1 — no inter-gold dependencies
    "gl_summary":    PIPELINES_DIR / "gold_aggregation" / "create_gold_summary.py",
    "revenue":       PIPELINES_DIR / "gold_aggregation" / "create_gold_revenue.py",
    "gp_by_plant":   PIPELINES_DIR / "gold_aggregation" / "create_gold_gp.py",
    "ppe_schedule":  PIPELINES_DIR / "gold_aggregation" / "create_ppe_schedule.py",
    "elimination":   PIPELINES_DIR / "gold_aggregation" / "create_elimination.py",
    "related_party": PIPELINES_DIR / "gold_aggregation" / "create_related_party.py",
    # Group 2 — cashflow depends on gold_leadsheet.parquet, run AFTER leadsheet
    "leadsheet":     PIPELINES_DIR / "gold_aggregation" / "create_leadsheet.py",
    "cashflow":      PIPELINES_DIR / "gold_aggregation" / "create_cashflow.py",
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


def run_domain(company_name: str, domain: str, silver_path: Path, bronze_base: Path, year: int = None) -> tuple:
    """
    Instantiate and run a single domain's ETL class directly.

    Returns:
        (company_name, domain, result_dict, elapsed_seconds)
    """
    cfg = REGISTRY.get(company_name)
    ETLClass = ETL_CLASSES[domain]
    bronze_kwarg = BRONZE_PATH_KWARG[domain]

    kwargs = {
        "company_code": cfg["company_code"],
        "silver_path":  silver_path,
        bronze_kwarg:   bronze_base,
    }
    # ar ETL does not support year parameter
    if domain != "ar" and year is not None:
        kwargs["year"] = year

    etl = ETLClass(**kwargs)
    t0 = time.time()
    result = etl.run()
    elapsed = time.time() - t0
    return (company_name, domain, result, elapsed)


def run_silver_for_company(company_name: str, domain: str = None, year: int = None) -> list:
    """
    Run silver ETL for one company using direct ETL class imports.

    Returns list of dicts:
        {"company": name, "domain": domain, "status": ..., "rows_out": N, "elapsed": t}
    """
    try:
        company = REGISTRY.get(company_name)
    except KeyError as e:
        print(f"❌ {e}")
        return []

    domains = [domain] if domain else list(company["bronze_paths"].keys())
    results = []

    for dom in domains:
        if dom not in ETL_CLASSES:
            print(f"  ⚠  No ETL class for domain '{dom}' — skipping")
            continue
        if dom not in company["bronze_paths"]:
            print(f"  ⚠  Company '{company_name}' has no Bronze path for '{dom}' — skipping")
            continue

        bronze_path = company["bronze_paths"][dom]
        try:
            co_name, domain_run, result, elapsed = run_domain(
                company_name, dom, SILVER_PATH, bronze_path, year=year
            )
        except Exception as exc:
            print(f"  ❌ [{company_name}] {dom} — exception: {exc}")
            results.append({
                "company": company_name,
                "domain": dom,
                "status": "failed",
                "rows_out": 0,
                "elapsed": 0.0,
            })
            continue

        rows_out = result.get("rows_out", 0)
        status = result.get("status", "failed")

        if status == "skipped" or rows_out == 0:
            print(f"  [{company_name}]   {dom:<12}  ⚠  0 rows — no files found in Bronze, skipped")
        elif status == "warning":
            print(f"  [{company_name}]   {dom:<12}  ⚠  {rows_out:>7,} rows  ({elapsed:.1f}s)")
        else:
            print(f"  [{company_name}]   {dom:<12}  ✓  {rows_out:>7,} rows  ({elapsed:.1f}s)")

        results.append({
            "company": company_name,
            "domain": dom,
            "status": status,
            "rows_out": rows_out,
            "elapsed": elapsed,
        })

    return results


def print_summary(results: list):
    """
    Print final summary. Accepts both old (label, bool) tuples and new dict format.
    """
    # Support old tuple format for backward compat (used by gold/init-db results)
    def _is_ok(r):
        if isinstance(r, dict):
            return r.get("status") in ("success", "warning")
        return r[1]  # old (label, bool) tuple

    def _is_skipped(r):
        if isinstance(r, dict):
            return r.get("status") == "skipped"
        return False

    passed  = sum(1 for r in results if _is_ok(r))
    skipped = sum(1 for r in results if _is_skipped(r))
    failed  = sum(1 for r in results if not _is_ok(r) and not _is_skipped(r))
    total   = len(results)

    print("─" * 60)
    print(f"Silver: {passed}/{total} passed  |  {skipped} skipped  |  {failed} failed")


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
    parser.add_argument("--gold-only",    action="store_true",
                        help="รัน gold layer เท่านั้น ไม่รัน silver (ใช้หลัง silver ทันสมัยแล้ว)")
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

    # ── Gold Only ──────────────────────────────────────────────
    if args.gold_only:
        if any([args.company, args.domain, args.layer]):
            print("  ℹ  --gold-only: ignoring --company / --domain / --layer (gold has no per-company split)")
        print(f"\n[GOLD ONLY] รัน gold layer เท่านั้น")
        for key, script in GOLD_SCRIPTS.items():
            ok = run_script(script, label=f"[gold] {key}")
            all_results.append((f"gold_{key}", ok))
        ok = run_script(INIT_DB_SCRIPT, label="init-db")
        all_results.append(("init-db", ok))
        if all_results:
            print_summary(all_results)
        return

    # ── Silver tasks ───────────────────────────────────────────
    companies_to_run = [args.company] if args.company else REGISTRY.all_companies()

    run_silver = args.all or args.layer == "silver" or (args.domain and not args.layer)

    if run_silver:
        print(f"\n Silver layer — companies: {companies_to_run}")
        for company_name in companies_to_run:
            results = run_silver_for_company(company_name, domain=args.domain, year=args.year)
            all_results.extend(results)

    # ── Gold tasks ─────────────────────────────────────────────
    run_gold = args.all or args.layer == "gold" or args.include_gold
    if run_gold:
        print(f"\n Gold layer")
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
