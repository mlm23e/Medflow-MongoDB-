import os
from enum import Enum
from decimal import Decimal

from pymongo import AsyncMongoClient, ReturnDocument

from app.config import settings

client = AsyncMongoClient(settings.mongodb_url)
database = client[settings.mongodb_database]
_indexes_initialized = False


async def initialize_database() -> None:
    global _indexes_initialized
    if _indexes_initialized:
        return
    await database.users.create_index("username", unique=True)
    await database.equipment.create_index("serial_number", unique=True)
    for collection_name in ("users", "hospitals", "equipment", "work_orders", "reports"):
        collection = database[collection_name]
        await collection.create_index("id", unique=True)
        highest = await collection.find_one({}, sort=[("id", -1)])
        await database.counters.update_one(
            {"_id": collection_name},
            {"$max": {"value": highest["id"] if highest else 0}},
            upsert=True,
        )
    _indexes_initialized = True


async def next_id(db, collection_name: str) -> int:
    counter = await db.counters.find_one_and_update(
        {"_id": collection_name},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return counter["value"]


def without_mongo_id(document: dict | None) -> dict | None:
    if document is None:
        return None
    return {key: value for key, value in document.items() if key != "_id"}


def to_mongo(value):
    if isinstance(value, dict):
        return {key: to_mongo(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_mongo(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value)
    return value