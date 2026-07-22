"""
render_catalog.py
===================
Render script-catalog.json into the human-readable script-commands.md
reference doc in the Vault. Run this after scan_scripts.py updates the
catalog (and after the one-time AI backfill has run).

Usage:
    python render_catalog.py
    python render_catalog.py --catalog "D:\\...\\script-catalog.json" --output "D:\\...\\script-commands.md"
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from script_catalog.render import render_markdown

DEFAULT_CATALOG = Path(
    r"D:\_Work_Workspace\03_Data_Projects\_Finance-Vault\09-AI-Memory\script-catalog.json"
)
DEFAULT_OUTPUT = Path(
    r"D:\_Work_Workspace\03_Data_Projects\_Finance-Vault\08-Context\References\script-commands.md"
)
REPO_COUNT = 7


def run_render(catalog_path: Path, output_path: Path, repo_count: int) -> str:
    """Read the JSON catalog, render it to Markdown, write it, and return the text."""
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    markdown = render_markdown(catalog, repo_count=repo_count)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Render script-catalog.json to Markdown")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    run_render(args.catalog, args.output, repo_count=REPO_COUNT)
    print(f"Rendered -> {args.output}")


if __name__ == "__main__":
    main()
