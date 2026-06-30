"""
core/validators.py — Data quality checks at the Silver layer boundary.
Warnings are logged but do NOT stop the pipeline.
"""
import pandas as pd


REQUIRED_COLUMNS = {
    "gl":         ["company_code", "Year", "Month", "GL_Account", "Net_Amount"],
    "sales":      ["company_code", "Year", "Month", "Net_Value_THB"],
    "production": ["company_code", "Year", "Month", "Plant", "GR_Qty"],
    "ar":         ["company_code", "GL_Account", "Net_Amount"],
}

KEY_COLUMNS = {
    "gl":         ["company_code", "Year", "Month"],
    "sales":      ["company_code", "Year", "Month"],
    "production": ["company_code", "Year", "Month"],
    "ar":         ["company_code"],
}


class SilverValidator:
    """
    Validates a cleaned DataFrame before it is written to Silver Parquet.
    Returns a list of warning strings. Empty list = valid.
    """

    def validate(self, df: pd.DataFrame, domain: str) -> list:
        warnings = []
        warnings += self._check_row_count(df)
        if df.empty:
            return warnings
        warnings += self._check_required_columns(df, domain)
        warnings += self._check_no_null_keys(df, domain)
        return warnings

    def _check_row_count(self, df: pd.DataFrame, min_rows: int = 1) -> list:
        if len(df) < min_rows:
            return [f"Row count {len(df)} is below minimum {min_rows}"]
        return []

    def _check_required_columns(self, df: pd.DataFrame, domain: str) -> list:
        required = REQUIRED_COLUMNS.get(domain, [])
        missing = [c for c in required if c not in df.columns]
        if missing:
            return [f"Missing required columns for domain '{domain}': {missing}"]
        return []

    def _check_no_null_keys(self, df: pd.DataFrame, domain: str) -> list:
        key_cols = KEY_COLUMNS.get(domain, [])
        warnings = []
        for col in key_cols:
            if col in df.columns and df[col].isna().any():
                null_count = df[col].isna().sum()
                warnings.append(f"Null values in key column '{col}': {null_count} rows")
        return warnings
