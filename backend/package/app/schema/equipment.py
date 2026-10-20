from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict
from app.models import EquipStatus

class EquipmentBase(BaseModel):
    serial_number : str = Field(min_length=1, max_length=100)
    model : str = Field(min_length=1, max_length=100)
    status : EquipStatus = EquipStatus.AVAILABLE
    charge_level : Decimal = Field(ge=0, le=100)
    facility_id : int

class EquipmentCreate(EquipmentBase):
    """Shape of POST/equipment"""

class EquipmentRead(EquipmentBase):
    id : int
    model_config = ConfigDict(from_attributes=True)

class EquipmentUpdate(BaseModel):
    serial_number : str | None = Field(default=None, min_length=0, max_length=100)
    model : str | None = Field(default=None, min_length=0, max_length=100)
    status : EquipStatus | None = None
    charge_level : Decimal | None = Field(default=None, ge=0, le=100)
    facility_id : int | None = None