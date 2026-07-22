"""
script_catalog/render.py
==========================
Render the JSON catalog into the human-readable Markdown reference doc,
grouped by category (script-commands.md in the Vault).
"""
import datetime

CATEGORY_ORDER = [
    "Month-End Close",
    "Cash Flow & Treasury",
    "Cost & Production Costing",
    "FS Support / Audit Detail",
    "Reconciliation",
    "Commission",
    "Reporting & Analytics",
    "Data Pipeline / ETL",
    "Ad-hoc / One-off",
    "Shared Utilities",
]


def _script_name(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def _command_for(entry: dict) -> str:
    if entry["language"] != "py":
        return entry["path"]
    flags = " ".join(entry.get("cli_flags", []))
    command = f"python {entry['path']}"
    return f"{command} {flags}".strip()


def render_markdown(catalog: list[dict], repo_count: int) -> str:
    """Render the catalog grouped by CATEGORY_ORDER into a Markdown document."""
    active = [e for e in catalog if e.get("status") != "stale"]
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# Script Catalog (auto-generated — อย่าแก้ไฟล์นี้ตรงๆ, แก้ที่ script-catalog.json)",
        f"> Generated: {timestamp} | {repo_count} repos scanned | {len(active)} scripts",
        "",
    ]

    by_category: dict[str, list[dict]] = {cat: [] for cat in CATEGORY_ORDER}
    uncategorized: list[dict] = []
    for entry in active:
        category = entry.get("category")
        if category in by_category:
            by_category[category].append(entry)
        else:
            uncategorized.append(entry)

    for category in CATEGORY_ORDER:
        entries = sorted(by_category[category], key=lambda e: e["id"])
        if not entries:
            continue
        lines.append(f"## {category} ({len(entries)} scripts)")
        lines.append("| Script | Repo | Command | Description |")
        lines.append("|---|---|---|---|")
        for entry in entries:
            description = (entry.get("description") or "").replace("|", "-")
            lines.append(
                f"| {_script_name(entry['path'])} | {entry['repo']} | "
                f"`{_command_for(entry)}` | {description} |"
            )
        lines.append("")

    if uncategorized:
        lines.append(f"## Uncategorized / Needs Review ({len(uncategorized)} scripts)")
        lines.append("| Script | Repo | Path | Status |")
        lines.append("|---|---|---|---|")
        for entry in sorted(uncategorized, key=lambda e: e["id"]):
            lines.append(
                f"| {_script_name(entry['path'])} | {entry['repo']} | "
                f"`{entry['path']}` | {entry.get('status', '')} |"
            )
        lines.append("")

    return "\n".join(lines)
