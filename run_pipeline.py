"""
run_pipeline.py — DEPRECATED

This script has been superseded by orchestrator.py which provides
multi-company support, Gold layer automation, and --gold-only flag.

All arguments are forwarded to orchestrator.py unchanged, so existing
scripts and habits continue to work.

Use directly:
  python orchestrator.py --all
  python orchestrator.py --all --include-gold
  python orchestrator.py --gold-only
  python orchestrator.py --company AMC --layer silver --domain gl
  python orchestrator.py --init-db
"""
import sys
import os
import subprocess

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("[DEPRECATED] run_pipeline.py -> ใช้ orchestrator.py แทน")
print(f"  Forwarding: python orchestrator.py {' '.join(sys.argv[1:])}\n")

result = subprocess.run(
    [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'orchestrator.py')]
    + sys.argv[1:]
)
sys.exit(result.returncode)
