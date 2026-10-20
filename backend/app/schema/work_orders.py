from pydantic import BaseModel, ConfigDict, Field

from datetime import datetime
from decimal import Decimal

from app.models import OrderPriority, OrderStatus

class OrderBase(BaseModel):
    title : str = Field(min_length=5)
    priority : OrderPriority
    status : OrderStatus
    equipment_id : int = Field(ge=1)
    technician_id : int | None = Field(default=None, ge=1)

class OrderCreate(OrderBase):
    """Shape of POST/work_orders"""

class OrderRead(BaseModel):
    id : int
    title : str
    priority : OrderPriority
    status : OrderStatus
    equipment_id : int
    technician_id : int | None
    created_at : datetime
    completed_at : datetime | None
    model_config = ConfigDict(from_attributes=True)

class OrderDiscrepancyRead(BaseModel):
    work_order_id : int
    title : str
    equipment_id : int
    equipment_facility_id : int
    technician_id : int
    technician_facility_id : int | None
    model_config = ConfigDict(from_attributes=True)

class EquipmentReliabilityRead(BaseModel):
    model : str
    total_calls : int
    completed_calls : int
    failed_calls : int
    completion_rate : Decimal = Field(ge=0, le=100)
    failure_rate : Decimal = Field(ge=0, le=100)

class OrderStatusUpdate(BaseModel):
    status : OrderStatus

class OrderUpdate(BaseModel):
    title : str | None = Field(default=None, min_length=5)
    priority : OrderPriority | None = None
    status : OrderStatus | None = None
    equipment_id : int | None = Field(default=None, ge=1)
    technician_id : int | None = Field(default=None, ge=1)
