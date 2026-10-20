from datetime import datetime

from pydantic import Field

from .base import Base
from .enums import OrderPriority, OrderStatus


class WorkOrder(Base):
    id: int
    title: str
    priority: OrderPriority
    status: OrderStatus = OrderStatus.PENDING
    equipment_id: int
    technician_id: int | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None