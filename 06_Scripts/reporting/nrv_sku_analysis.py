"""
NRV Analysis: Match Stock vs Selling Price by SKU + Grade (Month 1-4 2026)
─────────────────────────────────────────────────────────────────────────────
Logic:
  10*  (Raw Material)  → NRV = avg FG Grade-A price × yield 98% − conversion 2.85 − selling_exp 0.3255
  20*, 30*, 40* (FG)   → NRV = (actual sale → SO → mat_group+grade avg) − selling_exp 0.3255
  อื่น ๆ               → ตัดออก (SP Parts, Supplies, Equipment ฯลฯ)
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

# ── Parameters ───────────────────────────────────────────────────────────────
CONVERSION_COST = 2.85      # THB/KG  (ค่า conversion RM → FG)
SELLING_EXP     = 0.3255    # THB/KG  (ค่าใช้จ่ายในการขาย หักทุกรายการ)
YIELD           = 0.98      # 98%     (yield การผลิต RM → FG)

# RM mat_group keyword → FG mat_group keywords สำหรับดึงราคา FG Grade A
RM_FG_MAP = {
    "GIM": ["GIM", "GI"],
    "GI":  ["GI"],
    "HR":  ["HR"],
    "CR":  ["CR"],
    "GA":  ["GA"],
    "EG":  ["EG"],
    "GL":  ["GL"],
    "PO":  ["PO"],
}

def get_rm_type(mat_group):
    """หา RM type keyword จาก mat_group (GIM ก่อน GI)"""
    for key in ["GIM", "GI", "HR", "CR", "GA", "EG", "GL", "PO"]:
        if key in str(mat_group):
            return key
    return None


# ── 1. โหลด Stock ─────────────────────────────────────────────────────────────
_BASE_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STOCK_FILE = os.path.join(_BASE_DIR, "01_Bronze_Raw", "inventory", "amc", "mb52_nrv_audit_202603.xlsx")

stock_raw = pd.read_excel(STOCK_FILE, sheet_name="Ending InventoryYE'26", header=0)
stock_raw.columns = stock_raw.iloc[0]
stock = stock_raw.iloc[1:].copy()
stock.columns = stock.columns.str.strip()

available = list(stock.columns)

def find_col(keyword, exact=False):
    for c in available:
        if exact  and str(c).strip() == keyword: return c
        if not exact and keyword in str(c):       return c
    return None

rename_map = {
    find_col("Material",       exact=True): "sku",
    find_col("Description (EN)",exact=True):"description",
    find_col("Mat Group Name"):              "mat_group",
    find_col("Grade",          exact=True): "grade",
    find_col("Quantity",       exact=True): "stock_qty_kg",
    find_col("Amount Actual",  exact=True): "stock_amt",
    find_col("Price",          exact=True): "stock_price",
}
rename_map = {k: v for k, v in rename_map.items() if k is not None}

stock = stock[list(rename_map.keys())].rename(columns=rename_map)
stock["sku"]          = stock["sku"].astype(str).str.strip()
stock["grade"]        = stock["grade"].astype(str).str.strip().replace("nan", np.nan)
stock["stock_qty_kg"] = pd.to_numeric(stock["stock_qty_kg"], errors="coerce")
stock["stock_amt"]    = pd.to_numeric(stock["stock_amt"],    errors="coerce")
stock["stock_price"]  = pd.to_numeric(stock["stock_price"],  errors="coerce")

stock = stock[stock["sku"].notna() & (stock["sku"] != "nan")].copy()
stock = stock[stock["stock_qty_kg"] > 0].copy()

# กำหนด SKU prefix / sku_type
stock["sku_prefix"] = stock["sku"].str[:2]
stock["sku_type"]   = np.where(stock["sku_prefix"] == "10", "RM",
                      np.where(stock["sku_prefix"].isin(["20","30","40"]), "FG", "OTHER"))

stock_all = stock.copy()
stock     = stock[stock["sku_type"] != "OTHER"].copy()

print(f"✅ Stock loaded (all):   {len(stock_all):,} SKUs | {stock_all['stock_amt'].sum():,.0f} THB")
print(f"   ▸ RM  (10*):         {(stock['sku_type']=='RM').sum():,} SKUs")
print(f"   ▸ FG  (20*/30*/40*): {(stock['sku_type']=='FG').sum():,} SKUs")
print(f"   ▸ ตัดออก:            {(stock_all['sku_type']=='OTHER').sum():,} SKUs")
print(f"   วิเคราะห์:           {len(stock):,} SKUs | {stock['stock_amt'].sum():,.0f} THB")

# Grade distribution ใน stock ที่วิเคราะห์
gd = stock.groupby(["sku_type","grade"])["stock_qty_kg"].sum().reset_index()
print(f"\n   Grade breakdown (Qty KG):")
print(gd.to_string(index=False))


# ── 2. โหลด Sale M1–M4 ───────────────────────────────────────────────────────
_SALES_DIR = os.path.join(_BASE_DIR, "01_Bronze_Raw", "sales", "amc", "2026")
SALE_FILES = {1: os.path.join(_SALES_DIR, "vf05_202601.xlsx"),
              2: os.path.join(_SALES_DIR, "vf05_202602.xlsx"),
              3: os.path.join(_SALES_DIR, "vf05_202603.xlsx"),
              4: os.path.join(_SALES_DIR, "vf05_202604.xlsx")}

all_sales = []
for month, fpath in SALE_FILES.items():
    df = pd.read_excel(fpath, sheet_name="Sheet1")
    df = df[df["Cancelled"].isna()].copy()
    df["month"] = month
    all_sales.append(df)
    print(f"✅ Sale {month:02d}: {len(df):,} rows | {df['Material'].nunique():,} SKUs", flush=True)

sales = pd.concat(all_sales, ignore_index=True)
sales["Material"]       = sales["Material"].astype(str).str.strip()
sales["Grade"]          = sales["Grade"].astype(str).str.strip()
sales["Mat Group Des."] = sales["Mat Group Des."].astype(str).str.strip()
sales["Net Weight"]     = pd.to_numeric(sales["Net Weight"],     errors="coerce")
sales["Net Value(THB)"] = pd.to_numeric(sales["Net Value(THB)"], errors="coerce")


# ── 3. ราคาขาย SKU-level รายเดือน ─────────────────────────────────────────────
monthly = (
    sales.groupby(["Material", "month"])
    .agg(sale_qty_kg=("Net Weight","sum"), sale_value=("Net Value(THB)","sum"))
    .reset_index()
)
monthly["avg_price"] = monthly["sale_value"] / monthly["sale_qty_kg"]

price_pivot = monthly.pivot_table(index="Material", columns="month", values="avg_price",   aggfunc="mean").reset_index()
qty_pivot   = monthly.pivot_table(index="Material", columns="month", values="sale_qty_kg", aggfunc="sum" ).reset_index()
val_pivot   = monthly.pivot_table(index="Material", columns="month", values="sale_value",  aggfunc="sum" ).reset_index()

# รับประกัน 4 คอลัมน์เดือนครบ
for piv, base in [(price_pivot,"price"), (qty_pivot,"qty"), (val_pivot,"val")]:
    piv.columns = ["sku"] + [f"{base}_m{c}" for c in piv.columns[1:]]
    for m in [1,2,3,4]:
        col = f"{base}_m{m}"
        if col not in piv.columns:
            piv[col] = np.nan

sale_summary = (price_pivot
    .merge(qty_pivot, on="sku", how="outer")
    .merge(val_pivot,  on="sku", how="outer"))


# ── 4. Mat Group + Grade avg price (Weighted) จาก sale → Fallback สำหรับ FG ──
grp_sale = (
    sales.groupby(["Mat Group Des.", "Grade"])
    .agg(grp_qty=("Net Weight","sum"), grp_val=("Net Value(THB)","sum"))
    .reset_index()
)
grp_sale["grp_avg_price"] = grp_sale["grp_val"] / grp_sale["grp_qty"]
grp_sale = grp_sale.rename(columns={"Mat Group Des.":"mat_group","Grade":"grade"})


# ── 5. FG avg Grade-A price by rm_type (สำหรับ RM NRV) ───────────────────────
fg_gradeA = grp_sale[grp_sale["grade"] == "A"].copy()

fg_price_by_type = {}   # rm_type → weighted avg Grade-A FG price
for rm_type, fg_keywords in RM_FG_MAP.items():
    mask = fg_gradeA["mat_group"].apply(
        lambda g: any(kw in str(g) for kw in fg_keywords)
                  and not any(x in str(g) for x in ["Coil","Slab","Ingot","Roller"])
    )
    subset = fg_gradeA[mask]
    if len(subset) > 0 and subset["grp_qty"].sum() > 0:
        fg_price_by_type[rm_type] = subset["grp_val"].sum() / subset["grp_qty"].sum()
    else:
        fg_price_by_type[rm_type] = np.nan

print(f"\n📋 FG Grade-A avg price by RM type (NRV = × {YIELD} − {CONVERSION_COST} − {SELLING_EXP}):")
for t, p in fg_price_by_type.items():
    if pd.notna(p):
        nrv = p * YIELD - CONVERSION_COST - SELLING_EXP
        print(f"   {t:<5} FG={p:.4f}  →  NRV={nrv:.4f} THB/KG")
    else:
        print(f"   {t:<5} → No data")


# ── 6. โหลด SO ค้างส่ง ───────────────────────────────────────────────────────
SO_FILE = os.path.join(_BASE_DIR, "01_Bronze_Raw", "inventory", "amc", "so_bl_20260422.xlsx")

so_raw = pd.read_excel(SO_FILE, sheet_name="SO_BL")
so_raw["Material"]               = so_raw["Material"].astype(str).str.strip()
so_raw["Grade"]                  = so_raw["Grade"].astype(str).str.strip()
so_raw["Cal_Price"]              = pd.to_numeric(so_raw["Cal_Price"],               errors="coerce")
so_raw["SO Item Balance(KG)"]    = pd.to_numeric(so_raw["SO Item Balance(KG)"],     errors="coerce")
so_raw["SO Item Balance(Value)"] = pd.to_numeric(so_raw["SO Item Balance(Value)"],  errors="coerce")

so_valid = so_raw[
    so_raw["Material"].notna() & (so_raw["Material"] != "nan") &
    (so_raw["SO Item Balance(KG)"] > 0) & so_raw["Cal_Price"].notna()
].copy()

so_summary = (
    so_valid.groupby("Material")
    .apply(lambda g: pd.Series({
        "so_price":    (g["Cal_Price"] * g["SO Item Balance(KG)"]).sum() / g["SO Item Balance(KG)"].sum(),
        "so_qty_kg":   g["SO Item Balance(KG)"].sum(),
        "so_value":    g["SO Item Balance(Value)"].sum(),
        "so_so_count": g["Sales Document"].nunique() if "Sales Document" in g.columns else len(g),
    }), include_groups=False)
    .reset_index()
    .rename(columns={"Material":"sku"})
)
print(f"\n✅ SO loaded: {len(so_valid):,} rows | {so_summary['sku'].nunique():,} unique SKUs")


# ── 7. Merge ทั้งหมด ──────────────────────────────────────────────────────────
result = (stock
    .merge(sale_summary,                                          on="sku",                   how="left")
    .merge(so_summary,                                            on="sku",                   how="left")
    .merge(grp_sale[["mat_group","grade","grp_avg_price"]],       on=["mat_group","grade"],   how="left")
)

qty_cols = ["qty_m1","qty_m2","qty_m3","qty_m4"]
val_cols = ["val_m1","val_m2","val_m3","val_m4"]

result["total_qty_sold"] = result[qty_cols].sum(axis=1, min_count=1)
result["total_val_sold"] = result[val_cols].sum(axis=1, min_count=1)
result["avg_price_4m"]   = np.where(
    result["total_qty_sold"] > 0,
    result["total_val_sold"] / result["total_qty_sold"],
    np.nan
)


# ── 8. NRV Calculation ────────────────────────────────────────────────────────
def calc_nrv(row):
    if row["sku_type"] == "RM":
        rm_type  = get_rm_type(row["mat_group"])
        fg_price = fg_price_by_type.get(rm_type, np.nan) if rm_type else np.nan
        if pd.notna(fg_price):
            nrv = fg_price * YIELD - CONVERSION_COST - SELLING_EXP
            return nrv, f"RM→FG({rm_type})"
        return np.nan, "RM No FG Data"

    # FG: actual → SO → mat_group+grade avg
    if pd.notna(row["avg_price_4m"]):
        return row["avg_price_4m"] - SELLING_EXP, "Actual Sale M1-M4"
    if pd.notna(row["so_price"]):
        return row["so_price"] - SELLING_EXP, "SO Backlog"
    if pd.notna(row["grp_avg_price"]):
        return row["grp_avg_price"] - SELLING_EXP, "MatGroup+Grade Avg"
    return np.nan, "No Data"

nrv_results                 = result.apply(calc_nrv, axis=1)
result["nrv_price"]         = nrv_results.apply(lambda x: x[0])
result["nrv_source"]        = nrv_results.apply(lambda x: x[1])
result["cost_price"]        = result["stock_price"]
result["price_diff"]        = result["nrv_price"] - result["cost_price"]
result["write_down_per_kg"] = result["price_diff"].clip(upper=0)
result["write_down_amt"]    = result["write_down_per_kg"] * result["stock_qty_kg"]


# ── 9. Trend (FG only) ────────────────────────────────────────────────────────
def price_slope(row):
    prices = [row.get(f"price_m{i}") for i in range(1,5)]
    prices = [p for p in prices if pd.notna(p)]
    if len(prices) < 2: return np.nan
    return np.polyfit(np.arange(len(prices)), prices, 1)[0]

def trend_label(s):
    if pd.isna(s):    return "No Data"
    if s >  0.3:      return "↑ Rising"
    if s < -0.3:      return "↓ Falling"
    return "→ Stable"

result["price_slope"]   = result.apply(price_slope, axis=1)
result["trend"]         = result["price_slope"].apply(trend_label)
result["price_chg_pct"] = np.where(
    result["price_m1"].notna() & result["price_m4"].notna() & (result["price_m1"] > 0),
    (result["price_m4"] - result["price_m1"]) / result["price_m1"] * 100,
    np.nan,
)


# ── 10. Export ────────────────────────────────────────────────────────────────
out_cols = [
    "sku","description","mat_group","grade","sku_type",
    "stock_qty_kg","stock_price","stock_amt",
    "price_m1","qty_m1","val_m1",
    "price_m2","qty_m2","val_m2",
    "price_m3","qty_m3","val_m3",
    "price_m4","qty_m4","val_m4",
    "avg_price_4m",
    "so_price","so_qty_kg","so_value",
    "grp_avg_price",
    "nrv_price","nrv_source","cost_price","price_diff",
    "write_down_per_kg","write_down_amt",
    "price_slope","price_chg_pct","trend",
]
output = result[[c for c in out_cols if c in result.columns]].copy()
output[output.select_dtypes("float").columns] = output.select_dtypes("float").round(4)

output_file = os.path.join(_BASE_DIR, "01_Bronze_Raw", "inventory", "amc", "nrv_sku_202603.xlsx")

with pd.ExcelWriter(output_file, engine="openpyxl") as writer:

    # Sheet 1: SKU Detail ทั้งหมด
    output.to_excel(writer, sheet_name="SKU_Detail", index=False)

    # Sheet 2: Write-down Required
    wd = output[output["write_down_amt"] < 0].sort_values("write_down_amt")
    wd.to_excel(writer, sheet_name="WriteDown_Required", index=False)

    # Sheet 3: Summary by Mat Group + Grade
    grp_out = (
        output.groupby(["sku_type","mat_group","grade"])
        .agg(
            sku_count        =("sku",           "count"),
            stock_qty        =("stock_qty_kg",  "sum"),
            stock_amt        =("stock_amt",     "sum"),
            avg_cost         =("stock_price",   "mean"),
            avg_nrv_price    =("nrv_price",     "mean"),
            total_write_down =("write_down_amt","sum"),
            sku_writedown    =("write_down_amt", lambda x: (x < 0).sum()),
        )
        .reset_index()
        .sort_values(["sku_type","total_write_down"])
    )
    grp_out.to_excel(writer, sheet_name="Summary_MatGroup_Grade", index=False)

    # Sheet 4: Summary by Grade (รวมทุก group)
    grade_out = (
        output.groupby(["sku_type","grade"])
        .agg(
            sku_count        =("sku",           "count"),
            stock_qty        =("stock_qty_kg",  "sum"),
            stock_amt        =("stock_amt",     "sum"),
            avg_cost         =("stock_price",   "mean"),
            avg_nrv_price    =("nrv_price",     "mean"),
            total_write_down =("write_down_amt","sum"),
            sku_writedown    =("write_down_amt", lambda x: (x < 0).sum()),
        )
        .reset_index()
        .sort_values(["sku_type","total_write_down"])
    )
    grade_out.to_excel(writer, sheet_name="Summary_by_Grade", index=False)

    # Sheet 5: NRV Source Summary
    src_sum = (
        output.groupby("nrv_source")
        .agg(
            sku_count        =("sku",           "count"),
            stock_qty        =("stock_qty_kg",  "sum"),
            stock_amt        =("stock_amt",     "sum"),
            total_write_down =("write_down_amt","sum"),
            sku_writedown    =("write_down_amt", lambda x: (x < 0).sum()),
        )
        .reset_index()
        .sort_values("total_write_down")
    )
    src_sum.to_excel(writer, sheet_name="NRV_Source_Summary", index=False)

    # Sheet 6: FG Trend Summary (แยก Grade)
    trend_sum = (
        output[output["sku_type"] == "FG"]
        .groupby(["grade","trend"])
        .agg(
            sku_count     =("sku",           "count"),
            stock_qty     =("stock_qty_kg",  "sum"),
            stock_amt     =("stock_amt",     "sum"),
            avg_price_chg =("price_chg_pct", "mean"),
        )
        .reset_index()
    )
    trend_sum.to_excel(writer, sheet_name="Trend_by_Grade", index=False)

    # Sheet 7: RM Detail
    rm_out = output[output["sku_type"] == "RM"].sort_values("write_down_amt")
    rm_out.to_excel(writer, sheet_name="RM_Detail", index=False)

    # Sheet 8: รายการที่ตัดออก
    excluded = stock_all[stock_all["sku_type"] == "OTHER"][
        ["sku","description","mat_group","grade","stock_qty_kg","stock_amt"]
    ]
    excluded.to_excel(writer, sheet_name="Excluded_OTHER", index=False)

print(f"\n✅ Output saved: {output_file}")


# ── 11. Print Summary ─────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("  NRV ANALYSIS SUMMARY — Q1 2026 (Month 1-4) | By Grade")
print("=" * 65)

print(f"\n📦 Stock วิเคราะห์: {len(output):,} SKUs  |  {output['stock_amt'].sum():,.0f} THB")
print(f"   ✂️  ตัดออก:       {(stock_all['sku_type']=='OTHER').sum():,} SKUs  |  {stock_all[stock_all['sku_type']=='OTHER']['stock_amt'].sum():,.0f} THB")

wd_total = output[output["write_down_amt"] < 0]
print(f"\n⚠️  รวม Write-down: {len(wd_total):,} SKUs  |  {wd_total['write_down_amt'].sum():,.2f} THB")

print(f"\n📊 Write-down แยก SKU Type × Grade:")
wg = (wd_total.groupby(["sku_type","grade"])
      .agg(sku_count=("sku","count"), write_down=("write_down_amt","sum"))
      .reset_index().sort_values(["sku_type","write_down"]))
print(wg.to_string(index=False))

print(f"\n📋 NRV Source Breakdown:")
for _, row in src_sum.iterrows():
    print(f"   {row['nrv_source']:<25}  {int(row['sku_count']):>5} SKUs  |  WD: {row['total_write_down']:>13,.2f} THB")

print(f"\n📊 Top 15 Worst Write-down (All Grades):")
top_wd = wd_total.nsmallest(15, "write_down_amt")[
    ["sku","description","sku_type","grade","stock_qty_kg","cost_price","nrv_price","nrv_source","write_down_amt"]
].copy()
top_wd.columns = ["SKU","Description","Type","Grade","Qty(KG)","Cost","NRV","Source","Write-down"]
print(top_wd.to_string(index=False))

print(f"\n📊 Grade Summary (FG only):")
print(grade_out[grade_out["sku_type"]=="FG"].to_string(index=False))

print(f"\n📊 Grade Summary (RM only):")
print(grade_out[grade_out["sku_type"]=="RM"].to_string(index=False))
