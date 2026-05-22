"""
Finance Utility Functions — Finance Workspace
Prepared by: Claude Code
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Tuple

from config.settings import (
    RECONCILE_TOLERANCE,
    OUTLIER_STD_MULTIPLIER,
    OUTLIER_FORCE_FLAG_AMOUNT,
    MATCH_RATE_WARNING,
    LARGE_UNMATCHED_AMOUNT,
    DECIMAL_PLACES,
)


# ───────────────────────────── Reconciliation ──────────────────────────

def reconcile(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    key_cols: list[str],
    amount_col: str = "amount",
    date_col: str | None = None,
    date_tolerance_days: int = 0,
) -> dict[str, pd.DataFrame]:
    """
    Core reconciliation logic.

    Returns dict:
      matched      — รายการที่ match ทั้ง key และ amount (within tolerance)
      unmatched_a  — มีใน A ไม่มีใน B
      unmatched_b  — มีใน B ไม่มีใน A
      diff         — match key แต่ amount ต่างกัน
    """
    # ปัดทศนิยม 2 ตำแหน่ง
    df_a = df_a.copy()
    df_b = df_b.copy()
    df_a[amount_col] = df_a[amount_col].round(DECIMAL_PLACES)
    df_b[amount_col] = df_b[amount_col].round(DECIMAL_PLACES)

    # Merge บน key_cols
    merged = pd.merge(
        df_a, df_b,
        on=key_cols,
        how="outer",
        suffixes=("_A", "_B"),
        indicator=True,
    )

    left_only  = merged[merged["_merge"] == "left_only"].copy()
    right_only = merged[merged["_merge"] == "right_only"].copy()
    both       = merged[merged["_merge"] == "both"].copy()

    # Date tolerance filter (optional)
    if date_col and date_tolerance_days > 0 and f"{date_col}_A" in both.columns:
        both[f"{date_col}_A"] = pd.to_datetime(both[f"{date_col}_A"], dayfirst=True, errors="coerce")
        both[f"{date_col}_B"] = pd.to_datetime(both[f"{date_col}_B"], dayfirst=True, errors="coerce")
        date_diff = (both[f"{date_col}_A"] - both[f"{date_col}_B"]).abs()
        date_ok = date_diff <= timedelta(days=date_tolerance_days)
        # รายการที่วันต่างเกิน tolerance → ย้ายไป unmatched
        date_fail = both[~date_ok]
        both = both[date_ok]
        left_only = pd.concat([left_only, date_fail])

    # แยก Matched vs Diff
    a_amt = f"{amount_col}_A"
    b_amt = f"{amount_col}_B"
    if a_amt in both.columns and b_amt in both.columns:
        diff_mask = (both[a_amt] - both[b_amt]).abs() > RECONCILE_TOLERANCE
        diff    = both[diff_mask].copy()
        matched = both[~diff_mask].copy()
    else:
        matched = both.copy()
        diff    = pd.DataFrame()

    return {
        "matched":     matched,
        "unmatched_a": left_only,
        "unmatched_b": right_only,
        "diff":        diff,
    }


def recon_summary(result: dict[str, pd.DataFrame]) -> dict:
    """คำนวณ summary statistics จากผล reconcile"""
    n_matched     = len(result["matched"])
    n_unmatched_a = len(result["unmatched_a"])
    n_unmatched_b = len(result["unmatched_b"])
    n_diff        = len(result["diff"])
    total_a       = n_matched + n_unmatched_a + n_diff
    total_b       = n_matched + n_unmatched_b + n_diff
    match_rate    = n_matched / max(total_a, 1)

    return {
        "Total_A":    total_a,
        "Total_B":    total_b,
        "Matched":    n_matched,
        "Unmatched_A": n_unmatched_a,
        "Unmatched_B": n_unmatched_b,
        "Diff":       n_diff,
        "Match_Rate": f"{match_rate:.1%}",
        "_match_rate_float": match_rate,
    }


def check_recon_warnings(
    result: dict[str, pd.DataFrame],
    summary: dict,
    amount_col_a: str = "amount_A",
) -> list[str]:
    """
    ตรวจสอบ warning conditions — return list ของ warning messages
    """
    warnings = []
    rate = summary.get("_match_rate_float", 1.0)

    if rate < MATCH_RATE_WARNING:
        warnings.append(
            f"Match rate {rate:.1%} ต่ำกว่า {MATCH_RATE_WARNING:.0%} — กรุณาตรวจสอบก่อนดำเนินการต่อ"
        )

    # ตรวจ unmatched รายการใหญ่
    ua = result.get("unmatched_a", pd.DataFrame())
    if amount_col_a in ua.columns:
        large = ua[ua[amount_col_a].abs() >= LARGE_UNMATCHED_AMOUNT]
        if not large.empty:
            warnings.append(
                f"พบ {len(large)} รายการ Unmatched_A ที่มียอดเกิน "
                f"{LARGE_UNMATCHED_AMOUNT:,.0f} บาท — ต้องตรวจสอบก่อน"
            )

    return warnings


# ───────────────────────────── Analytics ───────────────────────────────

def detect_outliers(
    df: pd.DataFrame,
    amount_col: str = "amount",
    group_col: str | None = None,
) -> pd.DataFrame:
    """
    Flag outliers:
      - เกิน mean ± 2 std dev ในกลุ่มของตัวเอง
      - หรือยอดเกิน OUTLIER_FORCE_FLAG_AMOUNT บาท เสมอ
    """
    df = df.copy()
    df["_outlier"] = False
    df["_outlier_reason"] = ""

    groups = df.groupby(group_col)[amount_col] if group_col else [(None, df[amount_col])]

    for name, vals in groups:
        mean = vals.mean()
        std  = vals.std()
        idx  = vals.index
        stat_flag = (vals - mean).abs() > OUTLIER_STD_MULTIPLIER * std
        amt_flag  = vals.abs() >= OUTLIER_FORCE_FLAG_AMOUNT

        df.loc[idx[stat_flag], "_outlier"] = True
        df.loc[idx[stat_flag], "_outlier_reason"] = f"เกิน mean±{OUTLIER_STD_MULTIPLIER}σ"
        df.loc[idx[amt_flag], "_outlier"] = True
        df.loc[idx[amt_flag], "_outlier_reason"] = (
            df.loc[idx[amt_flag], "_outlier_reason"] + " | เกิน 500,000 บาท"
        ).str.strip(" | ")

    return df[df["_outlier"]].copy()


def moving_average_forecast(
    series: pd.Series,
    horizon: int = 3,
    window: int = 3,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Moving Average forecast
    Returns: (forecast, lower_90ci, upper_90ci)
    """
    ma = series.rolling(window=window).mean().iloc[-1]
    std = series.rolling(window=window).std().iloc[-1]
    z90 = 1.645  # 90% confidence interval

    forecast = pd.Series([ma] * horizon)
    lower    = forecast - z90 * std
    upper    = forecast + z90 * std

    return forecast.round(2), lower.round(2), upper.round(2)


def mom_change(series: pd.Series) -> pd.Series:
    """Month-over-Month % change"""
    return series.pct_change() * 100


def yoy_change(series: pd.Series) -> pd.Series:
    """Year-over-Year % change (12-period lag)"""
    return series.pct_change(periods=12) * 100
