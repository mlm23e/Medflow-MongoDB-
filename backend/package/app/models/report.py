from datetime import datetime

from pydantic import Field

from .base import Base


class Report(Base):
    id: int
    work_order_id: int
    file_url: str
    notes: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)