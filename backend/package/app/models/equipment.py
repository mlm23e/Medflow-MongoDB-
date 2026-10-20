from decimal import Decimal

from .base import Base
from .enums import EquipStatus


class Equipment(Base):
    id: int
    serial_number: str
    model: str
    status: EquipStatus = EquipStatus.AVAILABLE
    charge_level: Decimal = Decimal("100")
    facility_id: int