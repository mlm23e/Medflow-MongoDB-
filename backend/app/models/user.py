from .base import Base
from .enums import UserRole


class User(Base):
    id: int
    username: str
    hashed_password: str
    first_name: str
    last_name: str
    role: UserRole
    facility_id: int | None = None