"""
telegram_bot/utils/intent.py
=============================
Zero-cost intent detection via keyword matching.
Routes high-confidence NL messages to data handlers without calling Claude.
Only "low" confidence or "unknown" intents escalate to ai_service.

No external libraries — pure Python string matching.
"""
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntentResult:
    intent: str                   # detected domain
    params: dict = field(default_factory=dict)   # extracted parameters
    confidence: str = "high"      # "high" → use data handler; "low" → escalate to AI


# ── Keyword map ───────────────────────────────────────────────────────────────
# Each intent maps to (Thai keywords, English keywords)
KEYWORD_MAP: dict[str, list[str]] = {
    "health":   ["health", "status", "alive", "ping", "up", "down",
                 "สุขภาพ", "พร้อม", "ทำงาน", "ออนไลน์"],
    "lake":     ["lake", "duckdb", "views", "view count",
                 "เลค", "วิว"],
    "etl":      ["etl", "pipeline", "sync data", "run etl", "trigger",
                 "รัน", "ไปป์ไลน์", "อัพเดท"],
    "pnl":      ["p&l", "pnl", "profit and loss", "profit", "loss", "income statement",
                 "net income", "net profit", "ebit", "ebt", "gross profit",
                 "กำไร", "ขาดทุน", "รายได้สุทธิ", "กำไรสุทธิ", "กำไรขั้นต้น"],
    "revenue":  ["revenue", "sales revenue", "top line",
                 "รายได้", "ยอดขาย", "ยอดรายได้"],
    "sales":    ["sales summary", "monthly sales", "product sales", "sale",
                 "ยอดขาย", "สรุปยอดขาย", "ขาย"],
    "ar":       ["ar ", "a/r", "receivable", "aging", "overdue", "outstanding",
                 "ลูกหนี้", "อายุหนี้", "ค้างชำระ"],
    "gl":       ["gl ", "g/l", "general ledger", "ledger", "transaction",
                 "บัญชี", "รายการบัญชี", "แยกประเภท"],
    "kpi":      ["kpi", "ratio", "margin", "dso", "gross margin", "ebit margin",
                 "net margin", "return",
                 "อัตรา", "อัตรากำไร", "วัน"],
    "cost":     ["production cost", "cost of production", "manufacturing cost",
                 "zreport", "z-report", "cost center",
                 "ต้นทุน", "ต้นทุนการผลิต", "ต้นทุนผลิต"],
    "variance": ["variance", "variances", "driver", "explain", "reason", "why",
                 "ผันแปร", "ผลต่าง", "สาเหตุ", "เหตุผล", "ทำไม"],
    "compare":  ["compare", "vs ", "versus", "yoy", "year over year", "qoq",
                 "เปรียบเทียบ", "เทียบ", "ต่างกัน"],
    "forecast": ["forecast", "predict", "projection", "outlook", "next year",
                 "trend", "estimate", "expected",
                 "แนวโน้ม", "พยากรณ์", "คาดการณ์", "ปีหน้า", "อนาคต"],
    "report":   ["report", "export", "google sheet", "drive", "send report",
                 "รายงาน", "ส่งออก", "ดาวน์โหลด"],
}

# Analysis intents that always need AI even if high confidence
_AI_REQUIRED = {"variance", "forecast"}


def _text_lower(text: str) -> str:
    return text.lower().strip()


def detect_intent(text: str) -> IntentResult:
    """
    Detect intent from user text.
    Returns IntentResult with matched intent, extracted params, and confidence.

    High-confidence intents for data domains → route without AI.
    Low-confidence or analysis intents → escalate to Claude.
    """
    t = _text_lower(text)
    scores: dict[str, int] = {}

    for intent, keywords in KEYWORD_MAP.items():
        for kw in keywords:
            # Word boundary matching for short keywords (to avoid false positives)
            kw_lower = kw.lower()
            if len(kw_lower) <= 3:
                # Require word boundary for short English keywords
                if re.search(r"\b" + re.escape(kw_lower) + r"\b", t):
                    scores[intent] = scores.get(intent, 0) + 2
            elif kw_lower in t:
                scores[intent] = scores.get(intent, 0) + 3

    if not scores:
        return IntentResult(intent="unknown", confidence="low")

    best_intent = max(scores, key=lambda k: scores[k])
    best_score = scores[best_intent]

    # Extract common parameters
    params = {}
    years = re.findall(r"\b(20\d{2})\b", text)
    if years:
        params["years"] = [int(y) for y in years]
        params["year"] = int(years[-1])  # default to last mentioned

    months = re.findall(r"\b(0?[1-9]|1[0-2])\b", text)
    # Filter out years
    months = [int(m) for m in months if int(m) <= 12]
    if months:
        params["month"] = months[0]

    # GL account code (7 digits starting with 1-9)
    acct = re.search(r"\b([1-9]\d{6})\b", text)
    if acct:
        params["account"] = acct.group(1)

    # Low confidence if score too low
    confidence = "high" if best_score >= 3 else "low"

    # Analysis intents always need AI even if keyword-matched
    if best_intent in _AI_REQUIRED:
        return IntentResult(intent=best_intent, params=params, confidence="low")

    return IntentResult(intent=best_intent, params=params, confidence=confidence)


def extract_year(text: str, default: int = 2025) -> int:
    """Extract the most recently mentioned 4-digit year from text."""
    years = re.findall(r"\b(20\d{2})\b", text)
    return int(years[-1]) if years else default


def extract_month(text: str) -> int | None:
    """Extract month number from text (1-12)."""
    m = re.search(r"\b(0?[1-9]|1[0-2])\b", text)
    if m:
        return int(m.group(1))
    # Thai month names
    thai_months = {
        "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4,
        "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8,
        "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12,
    }
    for name, num in thai_months.items():
        if name in text:
            return num
    return None
