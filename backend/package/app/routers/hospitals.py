from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.database import next_id, to_mongo, without_mongo_id
from app.dependencies import get_current_user, get_db, require_role
from app.models import User, UserRole
from app.schema.hospitals import HospitalCreate, HospitalRead, HospitalUpdate, MaintenanceFlagRead

router = APIRouter(prefix="/hospitals", tags=["hospitals"])


@router.get("", response_model=list[HospitalRead])
async def list_hospitals(db=Depends(get_db), _: User = Depends(get_current_user)):
    return [without_mongo_id(item) async for item in db.hospitals.find().sort("id", 1)]


@router.post("", response_model=HospitalRead, status_code=status.HTTP_201_CREATED)
async def post_hospital(
    payload: HospitalCreate,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    if payload.supervisor_id is not None and await db.users.find_one({"id": payload.supervisor_id}) is None:
        raise HTTPException(status_code=404, detail=f"User '{payload.supervisor_id}' not found")
    hospital = to_mongo(payload.model_dump())
    hospital["id"] = await next_id(db, "hospitals")
    await db.hospitals.insert_one(hospital)
    return hospital


@router.get("/maintenance-flags", response_model=list[MaintenanceFlagRead])
async def hospitals_with_maintenance_flags(
    db=Depends(get_db),
    _: User = Depends(get_current_user),
):
    results = []
    hospitals = [without_mongo_id(item) async for item in db.hospitals.find().sort("id", 1)]
    for hospital in hospitals:
        equipment = await db.equipment.find({"facility_id": hospital["id"]}).to_list(None)
        total = len(equipment)
        maintenance = sum(item.get("status") == "Maintenance" for item in equipment)
        rate = maintenance * 100 / total if total else 0
        if total and rate > 30:
            results.append(MaintenanceFlagRead(
                id=hospital["id"],
                name=hospital["name"],
                equipment_total=total,
                maintenance_total=maintenance,
                maintenance_rate=Decimal(str(rate)),
            ))
    return results


@router.get("/{hospital_id}", response_model=HospitalRead)
async def get_hospital_by_id(
    hospital_id: int,
    db=Depends(get_db),
    _: User = Depends(get_current_user),
):
    hospital = without_mongo_id(await db.hospitals.find_one({"id": hospital_id}))
    if hospital is None:
        raise HTTPException(status_code=404, detail=f"Hospital '{hospital_id}' not found")
    return hospital


@router.patch("/{hospital_id}", response_model=HospitalRead)
async def update_hospital(
    hospital_id: int,
    payload: HospitalUpdate,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    updates = to_mongo(payload.model_dump(exclude_unset=True))
    if "supervisor_id" in updates and updates["supervisor_id"] is not None:
        if await db.users.find_one({"id": updates["supervisor_id"]}) is None:
            raise HTTPException(status_code=404, detail=f"User '{updates['supervisor_id']}' not found")
    result = await db.hospitals.update_one({"id": hospital_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Hospital '{hospital_id}' not found")
    return without_mongo_id(await db.hospitals.find_one({"id": hospital_id}))


@router.delete("/{hospital_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hospital(
    hospital_id: int,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> Response:
    if await db.hospitals.find_one({"id": hospital_id}) is None:
        raise HTTPException(status_code=404, detail=f"Hospital '{hospital_id}' not found")
    equipment = await db.equipment.find({"facility_id": hospital_id}, {"id": 1}).to_list(None)
    equipment_ids = [item["id"] for item in equipment]
    orders = await db.work_orders.find({"equipment_id": {"$in": equipment_ids}}, {"id": 1}).to_list(None)
    order_ids = [item["id"] for item in orders]
    await db.reports.delete_many({"work_order_id": {"$in": order_ids}})
    await db.work_orders.delete_many({"equipment_id": {"$in": equipment_ids}})
    await db.equipment.delete_many({"facility_id": hospital_id})
    await db.users.update_many({"facility_id": hospital_id}, {"$set": {"facility_id": None}})
    await db.hospitals.delete_one({"id": hospital_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)