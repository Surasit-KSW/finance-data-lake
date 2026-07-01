"""
scripts/vault_sync.py — Sync project HANDOFF.md → Finance Vault

อ่าน HANDOFF.md จากแต่ละ project → update <!-- sync:start/end --> section
ใน _Finance-Vault/08-Context/Projects/{project}.md

Usage:
    python scripts/vault_sync.py                        # sync all projects
    python scripts/vault_sync.py --project finance-data-lake
    python scripts/vault_sync.py --dry-run              # preview only
    python scripts/vault_sync.py --auto                 # silent mode (for hooks)

Pattern A ของ Vault-Project integration plan (2026-07-01)
"""
import sys
import re
import argparse
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Project registry
# ---------------------------------------------------------------------------
BASE = Path(r"D:\_Work_Workspace\03_Data_Projects")
VAULT = BASE / "_Finance-Vault"
VAULT_LOG = VAULT / "09-AI-Memory" / "session-log.md"

PROJECTS = [
    {
        "name": "finance-data-lake",
        "handoff": BASE / "_Finance_Data_Lake" / "HANDOFF.md",
        "vault_file": VAULT / "08-Context" / "Projects" / "finance-data-lake.md",
    },
    {
        "name": "fintech-command-center",
        "handoff": BASE / "active" / "fintech-command-center" / "HANDOFF.md",
        "vault_file": VAULT / "08-Context" / "Projects" / "fintech-command-center.md",
    },
    {
        "name": "sap-close-assistant",
        "handoff": BASE / "sap_gui_automation" / "HANDOFF.md",
        "vault_file": VAULT / "08-Context" / "Projects" / "sap-close-assistant.md",
    },
    {
        "name": "finance-workspace",
        "handoff": BASE / "active" / "finance-ops-workspace" / "HANDOFF.md",
        "vault_file": VAULT / "08-Context" / "Projects" / "finance-workspace.md",
    },
]


# ---------------------------------------------------------------------------
# HANDOFF.md parsing
# ---------------------------------------------------------------------------
SECTION_RE = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)


def _parse_handoff(path: Path) -> dict[str, str]:
    """Parse HANDOFF.md into {section_title: content} dict."""
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8", errors="replace")
    matches = list(SECTION_RE.finditer(text))
    sections: dict[str, str] = {}

    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[title.lower()] = text[start:end].strip()

    return sections


def _find_section(sections: dict[str, str], *candidates: str) -> str | None:
    """Return first matching section content (case-insensitive key lookup)."""
    for key in candidates:
        for skey, val in sections.items():
            if key.lower() in skey:
                return val
    return None


# ---------------------------------------------------------------------------
# Vault file update
# ---------------------------------------------------------------------------
SYNC_START = "<!-- sync:start -->"
SYNC_END = "<!-- sync:end -->"


def _build_sync_block(project_name: str, sections: dict[str, str]) -> str:
    """Build the content to put between sync markers."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    next_steps = _find_section(sections, "next step", "งานถัดไป", "todo", "upcoming")
    known_issues = _find_section(sections, "known issue", "issue", "blocker", "problem")
    progress = _find_section(sections, "progress", "what was done", "สรุป", "completed")
    goal = _find_section(sections, "goal", "objective", "เป้าหมาย")

    lines = [f"**Last HANDOFF Sync:** {now}"]

    if goal:
        lines += ["", "## Goal (from HANDOFF)", goal]

    if progress:
        # Truncate long progress sections
        prog_lines = progress.splitlines()
        if len(prog_lines) > 15:
            progress = "\n".join(prog_lines[:15]) + "\n_(truncated — see HANDOFF.md for full details)_"
        lines += ["", "## Progress (from HANDOFF)", progress]

    if next_steps:
        lines += ["", "## งานถัดไป (auto-synced)", next_steps]

    if known_issues:
        lines += ["", "## Known Issues (auto-synced)", known_issues]

    if not any([goal, progress, next_steps, known_issues]):
        lines.append("\n_(HANDOFF.md found but no recognized sections — check format)_")

    return "\n".join(lines)


def _update_vault_file(vault_file: Path, sync_content: str, dry_run: bool) -> bool:
    """Replace content between sync markers. Returns True if changed."""
    if not vault_file.exists():
        print(f"  ⚠️  Vault file not found: {vault_file}")
        return False

    text = vault_file.read_text(encoding="utf-8", errors="replace")

    if SYNC_START not in text or SYNC_END not in text:
        print(f"  ⚠️  No sync markers in {vault_file.name} — skipping")
        print(f"      Add  <!-- sync:start --> ... <!-- sync:end -->  to enable auto-sync")
        return False

    pattern = re.compile(
        re.escape(SYNC_START) + r".*?" + re.escape(SYNC_END),
        re.DOTALL,
    )
    new_block = f"{SYNC_START}\n{sync_content}\n{SYNC_END}"
    new_text, count = pattern.subn(new_block, text)

    if count == 0:
        print(f"  ⚠️  Could not replace sync block in {vault_file.name}")
        return False

    if new_text == text:
        print(f"  ✓  {vault_file.name} — no changes")
        return False

    if dry_run:
        print(f"  [DRY-RUN] Would update {vault_file.name}")
        _show_diff(text, new_text)
    else:
        vault_file.write_text(new_text, encoding="utf-8")
        print(f"  ✅ Updated {vault_file.name}")

    return True


def _show_diff(old: str, new: str) -> None:
    """Print a simple before/after for sync blocks."""
    old_start = old.find(SYNC_START)
    new_start = new.find(SYNC_START)
    old_end = old.find(SYNC_END) + len(SYNC_END)
    new_end = new.find(SYNC_END) + len(SYNC_END)

    print("  --- OLD sync block ---")
    for line in old[old_start:old_end].splitlines()[:8]:
        print(f"  - {line}")
    print("  --- NEW sync block ---")
    for line in new[new_start:new_end].splitlines()[:8]:
        print(f"  + {line}")
    print()


# ---------------------------------------------------------------------------
# Session log append
# ---------------------------------------------------------------------------
def _append_session_log(project_name: str, sections: dict[str, str], dry_run: bool) -> None:
    """Append one line to vault session-log.md."""
    summary = _find_section(sections, "progress", "what was done", "สรุป", "completed")
    if not summary:
        summary = _find_section(sections, "goal", "objective", "เป้าหมาย") or "HANDOFF synced"

    # Take first non-empty line as summary
    first_line = next(
        (ln.strip().lstrip("- ").lstrip("* ") for ln in summary.splitlines() if ln.strip()),
        "HANDOFF synced"
    )
    if len(first_line) > 120:
        first_line = first_line[:117] + "..."

    date_str = datetime.now().strftime("%Y-%m-%d")
    log_line = f"{date_str} | {project_name} | [vault_sync] {first_line}"

    if dry_run:
        print(f"  [DRY-RUN] Would append to session-log.md:")
        print(f"  {log_line}")
        return

    if VAULT_LOG.exists():
        with open(VAULT_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n{log_line}")
        print(f"  📝 Appended to session-log.md")
    else:
        print(f"  ⚠️  session-log.md not found at {VAULT_LOG}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def sync_project(project: dict, dry_run: bool, auto: bool) -> bool:
    name = project["name"]
    handoff_path = project["handoff"]
    vault_file = project["vault_file"]

    if not auto:
        print(f"\n→ {name}")

    if not handoff_path.exists():
        if not auto:
            print(f"  ⚠️  HANDOFF.md not found: {handoff_path}")
            print(f"      Run /dx:handoff in that project first")
        return False

    sections = _parse_handoff(handoff_path)
    if not sections:
        if not auto:
            print(f"  ⚠️  Could not parse HANDOFF.md (empty or unrecognized format)")
        return False

    sync_content = _build_sync_block(name, sections)
    changed = _update_vault_file(vault_file, sync_content, dry_run)

    if changed and not dry_run:
        _append_session_log(name, sections, dry_run)

    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync project HANDOFF.md → Finance Vault")
    parser.add_argument("--project", help="Sync only this project (by name)")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--auto", action="store_true", help="Silent mode for hooks (suppress most output)")
    args = parser.parse_args()

    projects = PROJECTS
    if args.project:
        projects = [p for p in PROJECTS if p["name"] == args.project]
        if not projects:
            print(f"Unknown project: {args.project}")
            print(f"Available: {[p['name'] for p in PROJECTS]}")
            sys.exit(1)

    if not args.auto:
        mode = "[DRY-RUN] " if args.dry_run else ""
        print(f"vault_sync.py {mode}— syncing {len(projects)} project(s)")
        print(f"Vault: {VAULT}")

    changed_count = 0
    for project in projects:
        if sync_project(project, args.dry_run, args.auto):
            changed_count += 1

    if not args.auto:
        print(f"\nDone — {changed_count}/{len(projects)} project(s) updated")


if __name__ == "__main__":
    main()
