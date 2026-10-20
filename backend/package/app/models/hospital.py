from .base import Base
from .enums import Region


class Hospital(Base):
    id: int
    name: str
    location_region: Region
    capacity: int
    supervisor_id: int | None = None