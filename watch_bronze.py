"""
watch_bronze.py — Bronze Folder File Watcher
============================================
Monitor 01_Bronze_Raw/ สำหรับไฟล์ใหม่หรือไฟล์ที่ถูกแก้ไข
เมื่อตรวจพบ → trigger ETL pipeline

Mode การทำงาน (เลือกอัตโนมัติ):
  1. API mode   — POST /api/etl/run (ถ้า localhost:8000 รันอยู่)
  2. Direct mode — รัน ETL scripts โดยตรง (fallback ถ้า API ไม่ได้รัน)

Usage:
    python watch_bronze.py                    # auto-detect mode
    python watch_bronze.py --direct           # บังคับ direct mode
    python watch_bronze.py --api http://...   # บังคับ API mode

Dependencies:
    pip install watchdog requests
"""

import argparse
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent
BRONZE_ROOT  = PROJECT_ROOT / "01_Bronze_Raw"
SILVER_DIR   = PROJECT_ROOT / "04_Data_Pipelines" / "silver_transform"
GOLD_DIR     = PROJECT_ROOT / "04_Data_Pipelines" / "gold_aggregation"
LOG_FILE     = PROJECT_ROOT / "logs" / "watch_bronze.log"

# Bronze subfolder → ETL script (relative to SILVER_DIR)
# ไฟล์ที่ map → None จะถูก skip (ไม่มี ETL รองรับ)
FOLDER_TO_ETL: dict[str, str | None] = {
    "gl":                "etl_gl.py",
    "cost_center":       "etl_ksb1.py",
    "tb_snapshots":      "etl_tb.py",
    "material_docs":     "etl_mb51.py",
    "production_orders": "etl_prd.py",
    "zcor001":           "etl_prd.py",
    "sales":             "etl_sales.py",
    "ar":                "etl_ar.py",
    "inventory":         None,   # ยังไม่มี ETL
    "master_data":       None,
    "month_end":         None,
}

# folder ที่ต้อง re-run Gold summary หลัง Silver (GL และ cost center ส่งผลต่อ v_gl_summary)
NEEDS_GOLD = {"gl", "cost_center"}

# ไฟล์ที่ไม่ต้อง trigger
IGNORE_PATTERNS = {".tmp", ".lock", "~$", ".DS_Store", "_tmp_"}

DEBOUNCE_SECONDS     = 10
POLL_INTERVAL_SECONDS = 5
ETL_TIMEOUT_SECONDS  = 600


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# API mode
# ---------------------------------------------------------------------------

def api_is_alive(api_url: str) -> bool:
    try:
        r = requests.get(f"{api_url}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def trigger_etl_api(api_url: str, domain: str, year: str | None) -> int | None:
    params = {"domain": domain}
    if year:
        params["year"] = year
    try:
        resp = requests.post(f"{api_url}/api/etl/run", params=params, timeout=10)
        resp.raise_for_status()
        run_id = resp.json().get("run_id")
        log.info(f"[API] ETL triggered: domain={domain} year={year} → run_id={run_id}")
        return run_id
    except Exception as e:
        log.error(f"[API] trigger error: {e}")
        return None


def poll_etl_api(api_url: str, run_id: int) -> str:
    deadline = time.time() + ETL_TIMEOUT_SECONDS
    log.info(f"[API] Polling run_id={run_id} ...")
    while time.time() < deadline:
        try:
            resp = requests.get(f"{api_url}/api/etl/runs/{run_id}", timeout=10)
            resp.raise_for_status()
            run   = resp.json().get("data", {})
            status = run.get("status", "running")
            if status == "success":
                log.info(f"[API] run_id={run_id} ✅ SUCCESS")
                return "success"
            elif status == "failed":
                log.error(f"[API] run_id={run_id} ❌ FAILED: {run.get('error_msg','')}")
                return "failed"
            time.sleep(POLL_INTERVAL_SECONDS)
        except Exception as e:
            log.warning(f"[API] poll error: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)
    log.error(f"[API] run_id={run_id} TIMEOUT")
    return "timeout"


# ---------------------------------------------------------------------------
# Direct mode
# ---------------------------------------------------------------------------

def _run(script: Path, extra_args: list[str] = None) -> bool:
    """รัน Python script แล้ว log output — return True ถ้าสำเร็จ"""
    cmd = [sys.executable, "-X", "utf8", str(script)] + (extra_args or [])
    log.info(f"[DIRECT] รัน: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    for line in result.stdout.splitlines():
        log.info(f"  {line}")
    if result.returncode != 0:
        for line in result.stderr.splitlines():
            log.error(f"  {line}")
        log.error(f"[DIRECT] ❌ exit code {result.returncode}")
        return False
    log.info(f"[DIRECT] ✅ สำเร็จ")
    return True


def run_direct(folder: str, year: str | None, file_path: Path | None = None) -> bool:
    """
    รัน Silver ETL ที่ตรงกับ folder → (ถ้าต้องการ) Gold → init_duckdb → Neon upsert
    ถ้ามี file_path: upsert เฉพาะไฟล์นั้น (เร็วกว่า rebuild ทั้งหมด)
    Return True ถ้าทุก step สำเร็จ
    """
    etl_script = FOLDER_TO_ETL.get(folder)

    if etl_script is None:
        log.warning(f"[DIRECT] ไม่มี ETL script สำหรับ folder '{folder}' — ข้าม")
        return False

    script_path = SILVER_DIR / etl_script
    if not script_path.exists():
        log.error(f"[DIRECT] ไม่พบ script: {script_path}")
        return False

    # Silver ETL — upsert เฉพาะไฟล์ที่เปลี่ยน ถ้าระบุมา
    if file_path and file_path.exists():
        log.info(f"[DIRECT] upsert mode: {file_path.name}")
        etl_args = ["--file", str(file_path)]
    else:
        log.info(f"[DIRECT] rebuild mode: year={year}")
        etl_args = ["--year", year] if year else []

    ok = _run(script_path, etl_args)
    if not ok:
        return False

    # Gold summary (เฉพาะ folder ที่ส่งผลต่อ P&L / GL summary)
    if folder in NEEDS_GOLD:
        gold_script = GOLD_DIR / "create_gold_summary.py"
        if gold_script.exists():
            ok = _run(gold_script)
            if not ok:
                log.warning("[DIRECT] Gold ETL ล้มเหลว — ข้าม init_duckdb")
                return False

    # Refresh DuckDB views
    init_script = PROJECT_ROOT / "04_Data_Pipelines" / "init_duckdb.py"
    if init_script.exists():
        _run(init_script)

    # Neon upsert — extract month จาก filename ถ้าทำได้
    neon_script = PROJECT_ROOT / "upload_to_neon.py"
    if neon_script.exists():
        month = _extract_month(file_path.name) if file_path else None
        if month and year:
            neon_args = ["--domain", "all", "--month", month, "--year", year]
            log.info(f"[NEON] upsert month={month}/{year}")
        else:
            neon_args = ["--domain", "all"]
            log.info("[NEON] full rebuild")
        _run(neon_script, neon_args)

    return True


# ---------------------------------------------------------------------------
# File watcher
# ---------------------------------------------------------------------------

def _extract_year(filename: str) -> str | None:
    import re
    m = re.search(r"(20\d{2})", filename)
    return m.group(1) if m else None


def _extract_month(filename: str) -> str | None:
    """หาเดือน 2 หลักจากชื่อไฟล์ เช่น gl_202606.XLSX → '6'"""
    import re
    m = re.search(r"20\d{2}(\d{2})", filename)
    return str(int(m.group(1))) if m else None


class BronzeHandler(FileSystemEventHandler):

    def __init__(self, api_url: str, force_direct: bool = False):
        self.api_url      = api_url
        self.force_direct = force_direct
        self._pending: dict[str, float] = {}

    def _should_ignore(self, path: str) -> bool:
        p = Path(path)
        if p.suffix.lower() not in {".xlsx", ".xls", ".csv", ".parquet"}:
            return True
        if any(pat in p.name for pat in IGNORE_PATTERNS):
            return True
        return False

    def _detect_folder(self, file_path: Path) -> str | None:
        try:
            rel = file_path.relative_to(BRONZE_ROOT)
            return rel.parts[0] if rel.parts else None
        except ValueError:
            return None

    def _schedule(self, path: str) -> None:
        self._pending[path] = time.time() + DEBOUNCE_SECONDS

    def _process_pending(self) -> None:
        now     = time.time()
        to_fire = [p for p, t in self._pending.items() if t <= now]

        for path in to_fire:
            del self._pending[path]
            file_path = Path(path)
            folder = self._detect_folder(file_path)
            if not folder:
                continue
            year = _extract_year(file_path.name)
            log.info(f"📂 ตรวจพบ: {file_path.name}  (folder={folder} year={year})")
            self._dispatch(folder, year, file_path)

    def _dispatch(self, folder: str, year: str | None, file_path: Path | None = None) -> None:
        """เลือก mode: API (ถ้าเปิดอยู่) → fallback Direct"""
        use_direct = self.force_direct

        if not use_direct:
            if api_is_alive(self.api_url):
                log.info(f"[MODE] API mode → {self.api_url}")
                domain_map = {
                    "gl": "gl", "cost_center": "gl", "tb_snapshots": "gl",
                    "inventory": "gl", "sales": "sales",
                    "production_orders": "production", "zcor001": "production",
                    "material_docs": "production", "ar": "ar",
                }
                domain = domain_map.get(folder)
                if not domain:
                    log.warning(f"[API] ไม่รู้จัก domain สำหรับ folder '{folder}' — fallback direct")
                    use_direct = True
                else:
                    run_id = trigger_etl_api(self.api_url, domain, year)
                    if run_id:
                        final = poll_etl_api(self.api_url, run_id)
                        if final == "success":
                            log.info(f"✅ [{folder}] ETL เสร็จแล้ว")
                        else:
                            log.warning(f"⚠️  [{folder}] ETL {final} — fallback direct")
                            use_direct = True
                    else:
                        use_direct = True
            else:
                log.info(f"[MODE] API ไม่ได้รัน → Direct mode")
                use_direct = True

        if use_direct:
            ok = run_direct(folder, year, file_path=file_path)
            if ok:
                log.info(f"✅ [{folder}] ETL + DuckDB refresh เสร็จแล้ว")
            else:
                log.error(f"❌ [{folder}] ETL ล้มเหลว — ตรวจสอบ logs/watch_bronze.log")

    # -- Watchdog event handlers --

    def on_created(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        log.info(f"  [NEW] {Path(event.src_path).name}")
        self._schedule(event.src_path)

    def on_modified(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        log.info(f"  [MOD] {Path(event.src_path).name}")
        self._schedule(event.src_path)

    def on_moved(self, event):
        if event.is_directory or self._should_ignore(event.dest_path):
            return
        log.info(f"  [MOVE] {Path(event.dest_path).name}")
        self._schedule(event.dest_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Bronze folder watcher → auto ETL (API or Direct)")
    parser.add_argument("--api",    default="http://localhost:8000", help="Data Lake API URL")
    parser.add_argument("--direct", action="store_true", help="บังคับ direct mode (ไม่ใช้ API)")
    args = parser.parse_args()

    setup_logging()

    if not BRONZE_ROOT.exists():
        log.error(f"Bronze root ไม่พบ: {BRONZE_ROOT}")
        sys.exit(1)

    mode = "DIRECT (forced)" if args.direct else f"AUTO (API={args.api} → fallback direct)"

    log.info("=" * 60)
    log.info("🔍 Bronze Watcher เริ่มทำงาน")
    log.info(f"   Watching : {BRONZE_ROOT}")
    log.info(f"   Mode     : {mode}")
    log.info(f"   Debounce : {DEBOUNCE_SECONDS}s")
    log.info("=" * 60)

    handler  = BronzeHandler(api_url=args.api, force_direct=args.direct)
    observer = Observer()
    observer.schedule(handler, str(BRONZE_ROOT), recursive=True)
    observer.start()

    try:
        while True:
            handler._process_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("หยุด watcher (Ctrl+C)")
    finally:
        observer.stop()
        observer.join()
        log.info("Watcher ปิดแล้ว")


if __name__ == "__main__":
    main()
