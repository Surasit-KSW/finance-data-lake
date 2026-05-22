"""
map_clearing_data.py
--------------------
Maps Clearing Document + Clearing Date from source → target.

Join key: Document Number + Document Date (ป้องกันแมพผิดเมื่อ doc เลขเดิมมีหลาย version)
"""

import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SOURCE_FILE = "other deposit_all.XLSX"
TARGET_FILE = "deposit_Q4'2025.xlsx"
OUTPUT_FILE = "deposit_Q4'2025_updated.xlsx"


# ── 1. Load files ──────────────────────────────────────────────────────────────

print("Loading source file...")
df_src = pd.read_excel(SOURCE_FILE)

print("Loading target file...")
df_tgt = pd.read_excel(TARGET_FILE)

print(f"  Source rows : {len(df_src):,}")
print(f"  Target rows : {len(df_tgt):,}")
print()


# ── 2. Prepare source lookup ───────────────────────────────────────────────────

src_cols = ["Document Number", "Document Date", "Clearing Document", "Clearing Date"]
df_src_clean = df_src[src_cols].dropna(subset=["Clearing Document", "Clearing Date"]).copy()

df_src_clean["Document Number"]   = df_src_clean["Document Number"].astype("Int64")
df_src_clean["Clearing Document"] = df_src_clean["Clearing Document"].astype("Int64")
df_src_clean["Document Date"]     = pd.to_datetime(df_src_clean["Document Date"], errors="coerce").dt.normalize()

# Deduplicate by (Document Number, Document Date) — keep latest clearing date
df_src_clean = (
    df_src_clean
    .sort_values("Clearing Date", ascending=False)
    .drop_duplicates(subset=["Document Number", "Document Date"], keep="first")
    .reset_index(drop=True)
)

print(f"Source lookup rows (deduped by doc+date): {len(df_src_clean):,}")
print()


# ── 3. Normalise target key columns ───────────────────────────────────────────

df_tgt["Document Number"] = df_tgt["Document Number"].astype("Int64")
df_tgt["_tgt_doc_date"]   = pd.to_datetime(df_tgt["Document Date"], dayfirst=False, errors="coerce").dt.normalize()


# ── 4. Merge on Document Number + Document Date ────────────────────────────────

df_merged = df_tgt.merge(
    df_src_clean.rename(columns={
        "Clearing Document": "_src_clearing_doc",
        "Clearing Date":     "_src_clearing_date",
    }).assign(**{"_tgt_doc_date": lambda x: x["Document Date"]})[
        ["Document Number", "_tgt_doc_date", "_src_clearing_doc", "_src_clearing_date"]
    ],
    on=["Document Number", "_tgt_doc_date"],
    how="left",
)

matched_strict = df_merged["_src_clearing_doc"].notna().sum()
print(f"Rows matched (doc number + date): {matched_strict} / {len(df_merged)}")


# ── 5. Fallback: match by Document Number only ────────────────────────────────
# ใช้เฉพาะกรณีที่ doc number ไม่มีใน source เลย
# ถ้า doc number มีใน source แต่ date ไม่ตรง = open item จริง → ไม่ fallback

src_all_docnums = set(df_src["Document Number"].dropna().astype("Int64").unique())
unmatched_mask  = df_merged["_src_clearing_doc"].isna()
can_fallback    = unmatched_mask & ~df_merged["Document Number"].isin(src_all_docnums)

if can_fallback.sum() > 0:
    src_fallback = (
        df_src[["Document Number", "Clearing Document", "Clearing Date"]]
        .dropna(subset=["Clearing Document", "Clearing Date"])
        .copy()
    )
    src_fallback["Document Number"]   = src_fallback["Document Number"].astype("Int64")
    src_fallback["Clearing Document"] = src_fallback["Clearing Document"].astype("Int64")
    src_fallback = (
        src_fallback
        .sort_values("Clearing Date", ascending=False)
        .drop_duplicates(subset=["Document Number"], keep="first")
        .rename(columns={"Clearing Document": "_fb_clearing_doc", "Clearing Date": "_fb_clearing_date"})
    )

    df_merged = df_merged.merge(src_fallback, on="Document Number", how="left")

    apply_fb = df_merged["_src_clearing_doc"].isna() & df_merged["_fb_clearing_doc"].notna()
    df_merged.loc[apply_fb, "_src_clearing_doc"]  = df_merged.loc[apply_fb, "_fb_clearing_doc"]
    df_merged.loc[apply_fb, "_src_clearing_date"] = df_merged.loc[apply_fb, "_fb_clearing_date"]
    df_merged.drop(columns=["_fb_clearing_doc", "_fb_clearing_date"], inplace=True)

matched_total = df_merged["_src_clearing_doc"].notna().sum()
print(f"Rows matched after fallback     : {matched_total} / {len(df_merged)}")
print()


# ── 6. Fill Clearing Doc + Clearing Date ──────────────────────────────────────

mask = df_merged["_src_clearing_doc"].notna()
df_merged.loc[mask, "Clearing Doc"]  = df_merged.loc[mask, "_src_clearing_doc"]
df_merged.loc[mask, "Clearing Date"] = df_merged.loc[mask, "_src_clearing_date"]


# ── 7. Drop helper columns & save ─────────────────────────────────────────────

df_final = df_merged.drop(columns=["_src_clearing_doc", "_src_clearing_date", "_tgt_doc_date"])

filled   = df_final["Clearing Doc"].notna().sum()
unfilled = df_final["Clearing Doc"].isna().sum()
print(f"Clearing Doc filled : {filled}")
print(f"Still empty         : {unfilled}")
print(f"Total rows          : {len(df_final)}")
print()

df_final.to_excel(OUTPUT_FILE, index=False)
print(f"Saved → {OUTPUT_FILE}")
