"""
models/ops.py — SQLAlchemy models for operational database (operations.db)
"""
import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from backend.core.database import Base


class ETLRun(Base):
    """ประวัติการรัน ETL pipeline แต่ละครั้ง"""
    __tablename__ = "etl_runs"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    started_at  = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status      = Column(String(20), default="running")  # running | success | failed
    domain      = Column(String(30), nullable=True)       # all | sales | production | gl | ar
    year        = Column(String(10), nullable=True)
    rows_out    = Column(Integer, nullable=True)
    error_msg   = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "started_at":   self.started_at.isoformat() if self.started_at else None,
            "finished_at":  self.finished_at.isoformat() if self.finished_at else None,
            "status":       self.status,
            "domain":       self.domain,
            "year":         self.year,
            "rows_out":     self.rows_out,
            "error_msg":    self.error_msg,
        }


class Scenario(Base):
    """P&L scenarios / forecasts บันทึกโดยผู้ใช้"""
    __tablename__ = "scenarios"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    data_json   = Column(Text, nullable=True)   # JSON string of scenario data
    created_at  = Column(DateTime, default=datetime.datetime.utcnow)

    def to_dict(self) -> dict:
        import json
        return {
            "id":           self.id,
            "name":         self.name,
            "description":  self.description,
            "data":         json.loads(self.data_json) if self.data_json else None,
            "created_at":   self.created_at.isoformat() if self.created_at else None,
        }
