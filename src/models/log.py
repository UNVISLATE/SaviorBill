from sqlalchemy import Column, Integer, String, JSON, DateTime

from src.utils.datetime_utils import utc_now
from . import Base

class ApiLogModel(Base):
    __tablename__ = "api_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    tenant_id = Column(Integer, nullable=True)
    profile_id = Column(Integer, nullable=True)

    action = Column(String(100), nullable=False)
    meta = Column(JSON, default=dict, nullable=False)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)