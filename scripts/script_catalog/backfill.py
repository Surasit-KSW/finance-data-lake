"""
script_catalog/backfill.py
============================
Apply AI-generated description/category summaries (produced by the
one-time subagent backfill pass, see the implementation plan Task 10)
into the catalog, flipping status from "needs_description" to "active".
"""


def apply_backfill(catalog: list[dict], backfill: dict[str, dict]) -> list[dict]:
    """
    `backfill` maps entry id -> {"description": str, "category": str}.
    Matched entries get description/category set and status flipped to
    "active". Unmatched entries are returned unchanged.
    """
    updated = []
    for entry in catalog:
        if entry["id"] in backfill:
            new_entry = dict(entry)
            new_entry["description"] = backfill[entry["id"]]["description"]
            new_entry["category"] = backfill[entry["id"]]["category"]
            new_entry["status"] = "active"
            updated.append(new_entry)
        else:
            updated.append(entry)
    return updated
