from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.database import next_id, to_mongo, without_mongo_id
from app.dependencies import get_current_user, get_db, require_role
from app.models import EquipStatus, User, UserRole
from app.schema.equipment import EquipmentCreate, EquipmentRead, EquipmentUpdate

router = APIRouter(prefix="/equipment", tags=["equipment"])


@router.get("", response_model=list[EquipmentRead])
async def list_equipment(
    max_charge: Decimal | None = Query(default=None, ge=0, le=100),
    db=Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = {"charge_level": {"$lt": float(max_charge)}} if max_charge is not None else {}
    cursor = db.equipment.find(query).sort("id", 1)
    return [without_mongo_id(item) async for item in cursor]


@router.post("", response_model=EquipmentRead, status_code=status.HTTP_201_CREATED)
async def post_equipment(
    payload: EquipmentCreate,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    if await db.hospitals.find_one({"id": payload.facility_id}) is None:
        raise HTTPException(status_code=404, detail=f"Facility '{payload.facility_id}' not found")
    equipment = to_mongo(payload.model_dump())
    equipment["id"] = await next_id(db, "equipment")
    await db.equipment.insert_one(equipment)
    return equipment


@router.get("/{equipment_id}", response_model=EquipmentRead)
async def get_equipment(
    equipment_id: int,
    db=Depends(get_db),
    _: User = Depends(get_current_user),
):
    equipment = without_mongo_id(await db.equipment.find_one({"id": equipment_id}))
    if equipment is None:
        raise HTTPException(status_code=404, detail=f"Equipment '{equipment_id}' not found")
    return equipment


@router.patch("/{equipment_id}", response_model=EquipmentRead)
async def update_equipment(
    equipment_id: int,
    payload: EquipmentUpdate,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    updates = to_mongo(payload.model_dump(exclude_unset=True))
    if "facility_id" in updates and await db.hospitals.find_one({"id": updates["facility_id"]}) is None:
        raise HTTPException(status_code=404, detail=f"Facility '{updates['facility_id']}' not found")
    result = await db.equipment.update_one({"id": equipment_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Equipment '{equipment_id}' not found")
    return without_mongo_id(await db.equipment.find_one({"id": equipment_id}))


@router.delete("/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_equipment(
    equipment_id: int,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> Response:
    if await db.equipment.find_one({"id": equipment_id}) is None:
        raise HTTPException(status_code=404, detail=f"Equipment '{equipment_id}' not found")
    work_orders = await db.work_orders.find({"equipment_id": equipment_id}, {"id": 1}).to_list(None)
    order_ids = [work_order["id"] for work_order in work_orders]
    await db.reports.delete_many({"work_order_id": {"$in": order_ids}})
    await db.work_orders.delete_many({"equipment_id": equipment_id})
    await db.equipment.delete_one({"id": equipment_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)