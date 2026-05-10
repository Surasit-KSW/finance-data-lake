"""
parquet_utils.py — Shared Parquet/DuckDB helpers
ใช้ร่วมกันในทุก audit/reporting script

ตัวอย่าง:
    from utils.parquet_utils import load_parquet, query_lake, get_available_years
    df_sales = load_parquet("sales")
    df = query_lake("SELECT * FROM v_sales WHERE Year = 2025")
"""

import os
import pandas as pd

# หา project root จาก utils/ folder (ถอยขึ้น 2 ชั้น)
_UTILS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(_UTILS_DIR))

SILVER = os.path.join(PROJECT_ROOT, "02_Silver_Cleaned")
GOLD   = os.path.join(PROJECT_ROOT, "03_Gold_DataMarts")
DB_PATH = os.path.join(PROJECT_ROOT, "finance_lake.duckdb")

# Mapping ชื่อ domain → Parquet file pattern
_DOMAIN_MAP = {
    "sales":        os.path.join(SILVER, "master_sales_{year}.parquet"),
    "production":   os.path.join(SILVER, "master_production_{year}.parquet"),
    "gl":           os.path.join(SILVER, "Master_GL_24_25.parquet"),
    "ar":           os.path.join(SILVER, "master_ar.parquet"),
    "gl_summary":   os.path.join(GOLD,   "Summary_GL_24_25.parquet"),
}


def load_parquet(domain: str, year: str | int | None = None) -> pd.DataFrame:
    """
    โหลด Parquet file ตาม domain และ year (ถ้าระบุ)
    domain: 'sales' | 'production' | 'gl' | 'ar' | 'gl_summary'
    year  : '2023' | '2024' | '2025' | None (=รวมทุกปี สำหรับ sales/production)
    """
    pattern = _DOMAIN_MAP.get(domain)
    if pattern is None:
        raise ValueError(f"Domain ไม่รู้จัก: '{domain}'. เลือกจาก: {list(_DOMAIN_MAP.keys())}")

    if "{year}" in pattern:
        if year is None:
            # รวมทุกปีที่มีไฟล์
            years = get_available_years(domain)
            if not years:
                raise FileNotFoundError(f"ไม่พบ Parquet สำหรับ domain='{domain}'")
            dfs = []
            for y in years:
                path = pattern.format(year=y)
                if os.path.exists(path):
                    dfs.append(pd.read_parquet(path))
            return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
        else:
            path = pattern.format(year=str(year))
    else:
        path = pattern

    if not os.path.exists(path):
        raise FileNotFoundError(f"ไม่พบไฟล์: {path}")

    return pd.read_parquet(path)


def get_available_years(domain: str) -> list[str]:
    """คืน list ของปีที่มี Parquet file สำหรับ domain นั้น (scan จาก filesystem จริง)"""
    pattern = _DOMAIN_MAP.get(domain, "")
    if "{year}" not in pattern:
        return []

    # Derive prefix/suffix จาก pattern เพื่อ scan folder จริง
    # เช่น pattern = ".../master_sales_{year}.parquet"
    folder = os.path.dirname(pattern)
    basename_template = os.path.basename(pattern)  # "master_sales_{year}.parquet"
    prefix, suffix = basename_template.split("{year}")

    years = []
    if os.path.isdir(folder):
        for fname in os.listdir(folder):
            if fname.startswith(prefix) and fname.endswith(suffix):
                candidate = fname[len(prefix): len(fname) - len(suffix)]
                if candidate.isdigit() and len(candidate) == 4:
                    years.append(candidate)
    return sorted(years)


def query_lake(sql: str) -> pd.DataFrame:
    """
    รัน SQL query ผ่าน DuckDB (finance_lake.duckdb)
    ต้องรัน init_duckdb.py ก่อนเพื่อสร้าง views

    ตัวอย่าง:
        df = query_lake("SELECT Year, SUM(Net_Amount) as total FROM v_sales GROUP BY Year")
    """
    import duckdb

    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"ไม่พบ finance_lake.duckdb\nรัน: python 04_Data_Pipelines/init_duckdb.py ก่อน"
        )

    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        return con.execute(sql).df()
    finally:
        con.close()


def save_parquet(df: pd.DataFrame, path: str) -> None:
    """บันทึก DataFrame เป็น Parquet"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, engine="pyarrow", index=False)
    print(f"💾 บันทึก Parquet: {path} ({len(df):,} rows)")
