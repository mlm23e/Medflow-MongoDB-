import asyncio

from app.database import client, database, initialize_database, next_id
from app.models import UserRole
from app.security import hash_password

SEED_USERS = [
    ("admin", "John", "Smith", UserRole.ADMIN, "adminpass123!"),
    ("technician", "Angie", "Paltrow", UserRole.TECHNICIAN, "technicianpass123!"),
    ("auditor", "Winston", "Church", UserRole.AUDITOR, "auditorpass123!"),
    ("admin_carrie", "Carrie", "Brown", UserRole.ADMIN, "adminpass123!"),
    ("technician_carrie", "Carrie", "McGill", UserRole.TECHNICIAN, "technicianpass123!"),
    ("auditor_mike", "Mike", "Church", UserRole.AUDITOR, "auditorpass123!"),
    ("admin_john", "John", "Mikakis", UserRole.ADMIN, "adminpass123!"),
    ("technician_james", "James", "McGill", UserRole.TECHNICIAN, "technicianpass123!"),
    ("auditor_jamie", "Jamie", "Weerasethankul", UserRole.AUDITOR, "auditorpass123!"),
    ("admin_parmy", "Parmjeet", "Larson", UserRole.ADMIN, "adminpass123!"),
    ("technician_paul", "Paul", "McHogeoan", UserRole.TECHNICIAN, "technicianpass123!"),
    ("auditor_paul", "Paul", "Atreides", UserRole.AUDITOR, "auditorpass123!"),
]


async def seed_users() -> None:
    await initialize_database()
    for username, first_name, last_name, role, password in SEED_USERS:
        if await database.users.find_one({"username": username}) is not None:
            continue
        await database.users.insert_one({
            "id": await next_id(database, "users"),
            "username": username,
            "hashed_password": hash_password(password),
            "first_name": first_name,
            "last_name": last_name,
            "role": role.value,
            "facility_id": None,
        })


async def run() -> None:
    try:
        await seed_users()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(run())