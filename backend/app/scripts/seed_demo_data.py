import argparse
import asyncio
from datetime import datetime

from app.database import client, database, initialize_database, next_id
from app.models import EquipStatus, OrderPriority, OrderStatus, Region
from app.scripts.seed_users import seed_users

HOSPITALS = [
    ("Ascension - Florida - Pensacola", Region.SOUTH, 5, "admin"),
    ("Cedars - New York - Poughkeepsie", Region.NORTHEAST, 10, "admin_carrie"),
    ("Shriners - Wisconsin - Madison", Region.MIDWEST, 7, "admin_john"),
    ("Community Health - Montana - Great Falls", Region.WEST, 3, "admin_parmy"),
]

EQUIPMENT = [
    ("RXA-7821", "Halo II", "Ascension - Florida - Pensacola", 100, EquipStatus.AVAILABLE),
    ("FJ1-3420", "Force", "Ascension - Florida - Pensacola", 45.34, EquipStatus.IN_USE),
    ("FJ1-3421", "Force", "Cedars - New York - Poughkeepsie", 12.33, EquipStatus.AVAILABLE),
    ("FJ1-3422", "Force", "Cedars - New York - Poughkeepsie", 19.23, EquipStatus.IN_USE),
    ("FJ1-5643", "Force", "Cedars - New York - Poughkeepsie", 20, EquipStatus.AVAILABLE),
    ("FJ1-4564", "Force", "Shriners - Wisconsin - Madison", 72.73, EquipStatus.AVAILABLE),
    ("RXA-1234", "Halo II", "Shriners - Wisconsin - Madison", 65, EquipStatus.MAINTENANCE),
    ("RXA-3421", "Halo II", "Community Health - Montana - Great Falls", 34, EquipStatus.AVAILABLE),
    ("FJ1-2341", "Force", "Community Health - Montana - Great Falls", 32.22, EquipStatus.AVAILABLE),
]

WORK_ORDERS = [
    ("Broken Battery", OrderPriority.CRITICAL, OrderStatus.IN_PROGRESS, "FJ1-3420", "technician"),
    ("Need New Defibralator", OrderPriority.CRITICAL, OrderStatus.COMPLETED, "FJ1-3421", "technician_carrie"),
    ("Sensors Malfunctioning", OrderPriority.MEDIUM, OrderStatus.PENDING, "FJ1-2341", "technician_james"),
    ("Partially Damaged Screen", OrderPriority.LOW, OrderStatus.FAILED, "RXA-7821", "technician"),
    ("Vandalized Console", OrderPriority.MEDIUM, OrderStatus.IN_PROGRESS, "RXA-3421", "technician_paul"),
    ("Force Calibration Failure", OrderPriority.MEDIUM, OrderStatus.FAILED, "FJ1-3420", "technician"),
    ("Halo II Inspection Complete", OrderPriority.LOW, OrderStatus.COMPLETED, "RXA-3421", "technician_paul"),
]


async def upsert_document(collection, id_collection: str, key: str, values: dict) -> dict:
    existing = await collection.find_one({key: values[key]})
    if existing is not None:
        await collection.update_one({"_id": existing["_id"]}, {"$set": values})
        existing.update(values)
        return existing
    document = {"id": await next_id(database, id_collection), **values}
    await collection.insert_one(document)
    return document


async def clear_demo_data() -> None:
    hospital_names = [record[0] for record in HOSPITALS]
    hospitals = await database.hospitals.find({"name": {"$in": hospital_names}}, {"id": 1}).to_list(None)
    hospital_ids = [item["id"] for item in hospitals]
    equipment = await database.equipment.find({"facility_id": {"$in": hospital_ids}}, {"id": 1}).to_list(None)
    equipment_ids = [item["id"] for item in equipment]
    orders = await database.work_orders.find({"equipment_id": {"$in": equipment_ids}}, {"id": 1}).to_list(None)
    order_ids = [item["id"] for item in orders]
    await database.reports.delete_many({"work_order_id": {"$in": order_ids}})
    await database.work_orders.delete_many({"equipment_id": {"$in": equipment_ids}})
    await database.equipment.delete_many({"facility_id": {"$in": hospital_ids}})
    await database.hospitals.delete_many({"id": {"$in": hospital_ids}})
    await database.users.update_many({"facility_id": {"$in": hospital_ids}}, {"$set": {"facility_id": None}})


async def seed_demo_data(reset: bool = False) -> None:
    await database.command("ping")
    await initialize_database()
    if reset:
        await clear_demo_data()
    await seed_users()

    users = {item["username"]: item for item in await database.users.find().to_list(None)}
    hospitals = {}
    for name, region, capacity, supervisor_username in HOSPITALS:
        hospital = await upsert_document(database.hospitals, "hospitals", "name", {
            "name": name,
            "location_region": region.value,
            "capacity": capacity,
            "supervisor_id": users[supervisor_username]["id"],
        })
        hospitals[name] = hospital

    for username, hospital_name in {
        "admin": HOSPITALS[0][0], "technician": HOSPITALS[0][0], "auditor": HOSPITALS[0][0],
        "admin_carrie": HOSPITALS[1][0], "technician_carrie": HOSPITALS[1][0], "auditor_mike": HOSPITALS[1][0],
        "admin_john": HOSPITALS[2][0], "technician_james": HOSPITALS[2][0], "auditor_jamie": HOSPITALS[2][0],
        "admin_parmy": HOSPITALS[3][0], "technician_paul": HOSPITALS[3][0], "auditor_paul": HOSPITALS[3][0],
    }.items():
        await database.users.update_one(
            {"id": users[username]["id"]},
            {"$set": {"facility_id": hospitals[hospital_name]["id"]}},
        )

    equipment_by_serial = {}
    for serial, model, hospital_name, charge, equip_status in EQUIPMENT:
        equipment_by_serial[serial] = await upsert_document(database.equipment, "equipment", "serial_number", {
            "serial_number": serial,
            "model": model,
            "facility_id": hospitals[hospital_name]["id"],
            "charge_level": charge,
            "status": equip_status.value,
        })

    order_by_title = {}
    for title, priority, order_status, serial, technician_username in WORK_ORDERS:
        order_by_title[title] = await upsert_document(database.work_orders, "work_orders", "title", {
            "title": title,
            "priority": priority.value,
            "status": order_status.value,
            "equipment_id": equipment_by_serial[serial]["id"],
            "technician_id": users[technician_username]["id"],
            "created_at": datetime.now(),
            "completed_at": datetime.now() if order_status == OrderStatus.COMPLETED else None,
        })

    await upsert_document(database.reports, "reports", "file_url", {
        "work_order_id": order_by_title["Need New Defibralator"]["id"],
        "file_url": "s3://medflow-diagnostics/FJ1-3421-001.txt",
        "notes": "Defib Replaced",
        "timestamp": datetime.now(),
    })


async def run(reset: bool) -> None:
    try:
        await seed_demo_data(reset=reset)
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    options = parser.parse_args()
    asyncio.run(run(reset=options.reset))
