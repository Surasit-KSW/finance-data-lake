"""
etl_cashflow_plan.py — Bronze Excel → Silver Parquet: Manual Cashflow Plan
Source:  01_Bronze_Raw/cashflow_plan/cashflow_plan_YYYY.xlsx
Output:  02_Silver_Cleaned/cashflow_plan_YYYY.parquet

Template columns (row 1 = header):
  date (DD/MM/YYYY) | type (receipt/payment) | amount | note

Rules:
- date must parse as DD/MM/YYYY → stored as YYYY-MM-DD string
- type must be "receipt" or "payment" (case-insensitive)
- amount is positive THB value; payment rows are stored as negative
- invalid rows (bad date / bad type / non-numeric amount) are skipped with warning
"""
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class CashflowPlanETL:
    def __init__(self, bronze_path: Path, silver_path: Path, year: int):
        self.bronze_path = Path(bronze_path)
        self.silver_path = Path(silver_path)
        self.year = year

    def _bronze_file(self) -> Path | None:
        for ext in (".xlsx", ".XLSX"):
            p = self.bronze_path / f"cashflow_plan_{self.year}{ext}"
            if p.exists():
                return p
        return None

    def run(self) -> dict:
        src = self._bronze_file()
        if src is None:
            print(f"  SKIP  cashflow_plan_{self.year}.xlsx not found in {self.bronze_path}")
            return {"status": "skipped", "rows": 0}

        print(f"  READ  {src.name}")
        raw = pd.read_excel(src)

        # Normalise column names: lowercase + strip
        raw.columns = [c.strip().lower() for c in raw.columns]
        required = {"date", "type", "amount", "note"}
        missing = required - set(raw.columns)
        if missing:
            raise ValueError(f"Excel missing columns: {missing}")

        rows = []
        skipped = 0
        for _, r in raw.iterrows():
            # Parse date
            try:
                d = datetime.strptime(str(r["date"]).strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
            except ValueError:
                print(f"  WARN  skipping row — bad date: {r['date']!r}")
                skipped += 1
                continue

            # Parse type
            t = str(r["type"]).strip().lower()
            if t not in ("receipt", "payment"):
                print(f"  WARN  skipping row — bad type: {r['type']!r}")
                skipped += 1
                continue

            # Parse amount
            try:
                amt = float(str(r["amount"]).replace(",", ""))
                if amt != amt:   # NaN
                    raise ValueError("NaN")
            except (ValueError, TypeError):
                print(f"  WARN  skipping row — bad amount: {r['amount']!r}")
                skipped += 1
                continue

            amount_thb = amt if t == "receipt" else -abs(amt)
            note = str(r.get("note", "")).strip() if pd.notna(r.get("note")) else ""

            rows.append({
                "date":       d,
                "type":       t,
                "amount_thb": round(amount_thb, 2),
                "note":       note,
                "year":       self.year,
            })

        df = pd.DataFrame(rows, columns=["date", "type", "amount_thb", "note", "year"])
        self.silver_path.mkdir(parents=True, exist_ok=True)
        out = self.silver_path / f"cashflow_plan_{self.year}.parquet"
        df.to_parquet(out, index=False)
        print(f"  OK    {len(df)} rows → {out.name}  ({skipped} skipped)")
        return {"status": "ok", "rows": len(df)}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()

    lake = Path(__file__).resolve().parents[3]
    etl = CashflowPlanETL(
        bronze_path=lake / "01_Bronze_Raw" / "cashflow_plan",
        silver_path=lake / "02_Silver_Cleaned",
        year=args.year,
    )
    result = etl.run()
    sys.exit(0 if result["status"] in ("ok", "skipped") else 1)


if __name__ == "__main__":
    main()
