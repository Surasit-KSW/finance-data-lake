"""
date_utils.py — Shared date/period helpers
ใช้ใน audit scripts เพื่อจัดการ fiscal periods และ date ranges
"""

import calendar
from datetime import date, datetime


MONTH_TH = {
    1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม",
    4: "เมษายน",  5: "พฤษภาคม",   6: "มิถุนายน",
    7: "กรกฎาคม", 8: "สิงหาคม",   9: "กันยายน",
    10: "ตุลาคม", 11: "พฤศจิกายน", 12: "ธันวาคม",
}

MONTH_EN_ABBR = {i: calendar.month_abbr[i] for i in range(1, 13)}
MONTH_EN_FULL = {i: calendar.month_name[i] for i in range(1, 13)}


def month_name_th(month: int) -> str:
    """คืนชื่อเดือนภาษาไทย"""
    return MONTH_TH.get(month, str(month))


def month_name_en(month: int, abbr: bool = True) -> str:
    """คืนชื่อเดือนภาษาอังกฤษ"""
    return MONTH_EN_ABBR[month] if abbr else MONTH_EN_FULL[month]


def get_month_range(year: int, month: int) -> tuple[date, date]:
    """คืน (start_date, end_date) ของเดือนนั้น"""
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)
    return start, end


def fiscal_year_months(year: int) -> list[dict]:
    """
    คืน list ของเดือนในปีงบประมาณ (Jan–Dec)
    แต่ละ item: {'month': 1, 'month_en': 'Jan', 'month_th': 'มกราคม', 'year': 2025}
    """
    return [
        {
            "month": m,
            "month_en": MONTH_EN_ABBR[m],
            "month_th": MONTH_TH[m],
            "year": year,
        }
        for m in range(1, 13)
    ]


def quarter_of_month(month: int) -> int:
    """คืน quarter (1-4) ของเดือน"""
    return (month - 1) // 3 + 1


def yoy_label(year1: int, year2: int) -> str:
    """สร้าง label เปรียบเทียบ 2 ปี เช่น '2024 vs 2025'"""
    return f"{year1} vs {year2}"


def timestamp_str(fmt: str = "%Y%m%d_%H%M%S") -> str:
    """คืน timestamp string สำหรับตั้งชื่อไฟล์"""
    return datetime.now().strftime(fmt)
