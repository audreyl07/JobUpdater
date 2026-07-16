from enum import Enum

from sqlalchemy import Column, Integer, String, DateTime

from app.database.base import Base


class ScanStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ScanHistory(Base):
    __tablename__ = "scan_history"

    id = Column(Integer, primary_key=True)

    company_id = Column(Integer, nullable=False)

    status = Column(String, nullable=False)

    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    jobs_found = Column(Integer, default=0)
    jobs_added = Column(Integer, default=0)
    jobs_updated = Column(Integer, default=0)
    jobs_removed = Column(Integer, default=0)

    error_message = Column(String, nullable=True)