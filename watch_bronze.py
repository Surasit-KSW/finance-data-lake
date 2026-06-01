"""
watch_bronze.py — Bronze Folder File Watcher
============================================
Monitor 01_Bronze_Raw/ สำหรับไฟล์ใหม่หรือไฟล์ที่ถูกแก้ไข
เมื่อตรวจพบ → trigger ETL pipeline ผ่าน POST /api/etl/run
แล้ว poll จนกว่า pipeline จะเสร็จ

Usage:
    python watch_bronze.py              # monitor all domains
    python watch_bronze.py --api http://localhost:8000
    python watch_bronze.py --domain gl  # force specific domain

Dependencies:
    pip install watchdog requests
"""

import argparse
import logging
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

BRONZE_ROOT = Path(__file__).parent / "01_Bronze_Raw"
LOG_FILE    = Path(__file__).parent / "logs" / "watch_bronze.log"

# Map Bronze subfolder → ETL domain
FOLDER_TO_DOMAIN = {
    "GL_Transactions":   "gl",
    "AR_Data":           "ar",
    "AP_Data":           "ar",   # AP ยังไม่มี ETL แยก → fallback ไป ar
    "Sales_Reports":     "sales",
    "Production":        "production",
    "monthend":          "gl",   # KSB1 cost center → ใช้ gl ETL
    "Inventory_RollStock": "gl", # Trial Balance → gl ETL
}

# ไฟล์ที่ไม่ต้อง trigger (temp files, locks, etc.)
IGNORE_PATTERNS = {".tmp", ".lock", "~$", ".DS_Store"}

# รอ N วินาทีหลังไฟล์เปลี่ยน ก่อน trigger (ป้องกัน trigger ซ้ำระหว่าง copy)
DEBOUNCE_SECONDS = 10

# Poll interval ตรวจ ETL status
POLL_INTERVAL_SECONDS = 5

# Timeout รอ ETL เสร็จ (วินาที)
ETL_TIMEOUT_SECONDS = 600  # 10 นาที


# ---------------------------------------------------------------------------
# Logging setup
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
# ETL trigger + poll
# ---------------------------------------------------------------------------

def trigger_etl(api_url: str, domain: str, year: str | None = None) -> int | None:
    """POST /api/etl/run → return run_id หรือ None ถ้า error"""
    params = {"domain": domain}
    if year:
        params["year"] = year

    try:
        resp = requests.post(f"{api_url}/api/etl/run", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        run_id = data.get("run_id")
        log.info(f"ETL triggered: domain={domain} year={year} → run_id={run_id}")
        return run_id
    except requests.exceptions.ConnectionError:
        log.warning(f"API ไม่ได้รัน ({api_url}) — ข้าม ETL trigger สำหรับ domain={domain}")
        return None
    except Exception as e:
        log.error(f"trigger_etl error: {e}")
        return None


def poll_etl(api_url: str, run_id: int) -> str:
    """Poll GET /api/etl/runs/{run_id} จนเสร็จ → return final status"""
    deadline = time.time() + ETL_TIMEOUT_SECONDS
    log.info(f"Polling ETL run_id={run_id} ...")

    while time.time() < deadline:
        try:
            resp = requests.get(f"{api_url}/api/etl/runs/{run_id}", timeout=10)
            resp.raise_for_status()
            run = resp.json().get("data", {})
            status = run.get("status", "running")

            if status == "success":
                finished = run.get("finished_at", "")
                log.info(f"ETL run_id={run_id} SUCCESS ✓ (finished: {finished})")
                return "success"
            elif status == "failed":
                err = run.get("error_msg", "")
                log.error(f"ETL run_id={run_id} FAILED ✗\n{err}")
                return "failed"
            else:
                log.info(f"  ... still running (status={status})")
                time.sleep(POLL_INTERVAL_SECONDS)

        except Exception as e:
            log.warning(f"poll error: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)

    log.error(f"ETL run_id={run_id} TIMEOUT after {ETL_TIMEOUT_SECONDS}s")
    return "timeout"


# ---------------------------------------------------------------------------
# File watcher
# ---------------------------------------------------------------------------

class BronzeHandler(FileSystemEventHandler):
    """Handle file events ใน 01_Bronze_Raw/"""

    def __init__(self, api_url: str, force_domain: str | None = None):
        self.api_url      = api_url
        self.force_domain = force_domain
        self._pending: dict[str, float] = {}  # path → scheduled trigger time

    def _should_ignore(self, path: str) -> bool:
        p = Path(path)
        if not p.suffix.lower() in {".xlsx", ".xls", ".csv", ".parquet"}:
            return True
        if any(pat in p.name for pat in IGNORE_PATTERNS):
            return True
        return False

    def _detect_domain(self, file_path: Path) -> str | None:
        """หา domain จากชื่อ subfolder ของไฟล์"""
        if self.force_domain:
            return self.force_domain

        # หา relative parts จาก BRONZE_ROOT
        try:
            rel = file_path.relative_to(BRONZE_ROOT)
            top_folder = rel.parts[0] if rel.parts else ""
            return FOLDER_TO_DOMAIN.get(top_folder)
        except ValueError:
            return None

    def _schedule(self, path: str) -> None:
        """Debounce: บันทึก path พร้อม trigger time"""
        self._pending[path] = time.time() + DEBOUNCE_SECONDS

    def _process_pending(self) -> None:
        """เรียกใช้จาก main loop — trigger ETL สำหรับ path ที่ถึงเวลาแล้ว"""
        now = time.time()
        to_fire = [p for p, t in self._pending.items() if t <= now]

        # Group by domain เพื่อไม่ trigger ซ้ำถ้ามีหลายไฟล์ใน domain เดียว
        domains_to_fire: dict[str, str | None] = {}  # domain → year
        for path in to_fire:
            del self._pending[path]
            domain = self._detect_domain(Path(path))
            if not domain:
                log.warning(f"ไม่รู้จัก domain สำหรับ: {path} — ข้าม")
                continue

            # ตรวจ year จากชื่อไฟล์ (เช่น sale_2026_05.XLSX → 2026)
            year = _extract_year(Path(path).name)
            if domain not in domains_to_fire:
                domains_to_fire[domain] = year

        for domain, year in domains_to_fire.items():
            log.info(f"📂 ตรวจพบไฟล์ใหม่ → trigger ETL (domain={domain} year={year})")
            run_id = trigger_etl(self.api_url, domain=domain, year=year)
            if run_id:
                final = poll_etl(self.api_url, run_id)
                if final == "success":
                    log.info(f"✅ Dashboard พร้อมแสดงข้อมูลใหม่ [{domain}]")
                else:
                    log.warning(f"⚠️  ETL {final} [{domain}] — ตรวจสอบ logs/pipeline.log")

    # -- Watchdog event handlers --

    def on_created(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        log.info(f"  [NEW] {event.src_path}")
        self._schedule(event.src_path)

    def on_modified(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        log.info(f"  [MOD] {event.src_path}")
        self._schedule(event.src_path)

    def on_moved(self, event):
        if event.is_directory or self._should_ignore(event.dest_path):
            return
        log.info(f"  [MOVE] {event.dest_path}")
        self._schedule(event.dest_path)


def _extract_year(filename: str) -> str | None:
    """พยายามหาปี 4 หลักจากชื่อไฟล์ เช่น sale_2026_05.XLSX → '2026'"""
    import re
    m = re.search(r"(20\d{2})", filename)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Bronze folder file watcher → auto ETL trigger")
    parser.add_argument("--api",    default="http://localhost:8000", help="Data Lake API URL")
    parser.add_argument("--domain", default=None, help="Force ETL domain (all | gl | sales | production | ar)")
    args = parser.parse_args()

    setup_logging()

    if not BRONZE_ROOT.exists():
        log.error(f"Bronze root ไม่พบ: {BRONZE_ROOT}")
        sys.exit(1)

    log.info("=" * 60)
    log.info(f"🔍 Bronze Watcher เริ่มทำงาน")
    log.info(f"   Watching : {BRONZE_ROOT}")
    log.info(f"   API      : {args.api}")
    log.info(f"   Domain   : {args.domain or 'auto-detect'}")
    log.info(f"   Debounce : {DEBOUNCE_SECONDS}s")
    log.info("=" * 60)

    handler  = BronzeHandler(api_url=args.api, force_domain=args.domain)
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
