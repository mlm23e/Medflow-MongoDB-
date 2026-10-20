from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.database import next_id, to_mongo, without_mongo_id
from app.dependencies import get_current_user, get_db, require_role
from app.models import Equipment, OrderPriority, OrderStatus, User, UserRole
from app.schema.work_orders import (
    EquipmentReliabilityRead,
    OrderCreate,
    OrderDiscrepancyRead,
    OrderRead,
    OrderStatusUpdate,
    OrderUpdate,
)

router = APIRouter(prefix="/work_orders", tags=["work_orders"])


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def post_work_order(
    payload: OrderCreate,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN, UserRole.TECHNICIAN)),
):
    if await db.equipment.find_one({"id": payload.equipment_id}) is None:
        raise HTTPException(status_code=404, detail=f"Equipment '{payload.equipment_id}' not found")
    if payload.technician_id is not None and await db.users.find_one({"id": payload.technician_id}) is None:
        raise HTTPException(status_code=404, detail=f"User '{payload.technician_id}' not found")
    order = to_mongo(payload.model_dump())
    order.update(id=await next_id(db, "work_orders"), created_at=datetime.now(), completed_at=None)
    await db.work_orders.insert_one(order)
    return order


@router.get("", response_model=list[OrderRead])
async def list_work_orders(db=Depends(get_db), _: User = Depends(get_current_user)):
    return [without_mongo_id(item) async for item in db.work_orders.find().sort("id", 1)]


@router.get("/reliability", response_model=list[EquipmentReliabilityRead])
async def atm_reliability_metric(db=Depends(get_db), _: User = Depends(get_current_user)):
    equipment = await db.equipment.find().to_list(None)
    equipment_models = {item["id"]: item["model"] for item in equipment}
    grouped = {}
    for order in await db.work_orders.find().to_list(None):
        model = equipment_models.get(order["equipment_id"])
        if model is None:
            continue
        metrics = grouped.setdefault(model, {"total_calls": 0, "completed_calls": 0, "failed_calls": 0})
        metrics["total_calls"] += 1
        metrics["completed_calls"] += order["status"] == OrderStatus.COMPLETED.value
        metrics["failed_calls"] += order["status"] == OrderStatus.FAILED.value
    results = []
    for model, metrics in sorted(grouped.items()):
        resolved = metrics["completed_calls"] + metrics["failed_calls"]
        results.append(EquipmentReliabilityRead(
            model=model,
            **metrics,
            completion_rate=metrics["completed_calls"] / resolved * 100 if resolved else 0,
            failure_rate=metrics["failed_calls"] / resolved * 100 if resolved else 0,
        ))
    return results


@router.get("/discrepancies", response_model=list[OrderDiscrepancyRead])
async def list_colocation_discrepancies(
    priority: OrderPriority | None = Query(default=None),
    db=Depends(get_db),
    _: User = Depends(get_current_user),
):
    equipment = {item["id"]: item for item in await db.equipment.find().to_list(None)}
    users = {item["id"]: item for item in await db.users.find().to_list(None)}
    results = []
    query = {"priority": priority.value} if priority is not None else {}
    for order in await db.work_orders.find(query).sort("id", 1).to_list(None):
        item = equipment.get(order["equipment_id"])
        technician = users.get(order.get("technician_id"))
        if (
            item is None
            or technician is None
            or technician.get("facility_id") is None
            or item["facility_id"] == technician["facility_id"]
        ):
            continue
        results.append(OrderDiscrepancyRead(
            work_order_id=order["id"],
            title=order["title"],
            equipment_id=item["id"],
            equipment_facility_id=item["facility_id"],
            technician_id=technician["id"],
            technician_facility_id=technician["facility_id"],
        ))
    return results


@router.get("/{work_order_id}", response_model=OrderRead)
async def get_work_order_by_id(
    work_order_id: int,
    db=Depends(get_db),
    _: User = Depends(get_current_user),
):
    order = without_mongo_id(await db.work_orders.find_one({"id": work_order_id}))
    if order is None:
        raise HTTPException(status_code=404, detail=f"WorkOrder '{work_order_id}' not found")
    return order


@router.patch("/{work_order_id}", response_model=OrderRead)
async def update_work_order(
    work_order_id: int,
    payload: OrderUpdate,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN, UserRole.TECHNICIAN)),
):
    updates = to_mongo(payload.model_dump(exclude_unset=True))
    if await db.work_orders.find_one({"id": work_order_id}) is None:
        raise HTTPException(status_code=404, detail=f"WorkOrder '{work_order_id}' not found")
    if "equipment_id" in updates and await db.equipment.find_one({"id": updates["equipment_id"]}) is None:
        raise HTTPException(status_code=404, detail=f"Equipment '{updates['equipment_id']}' not found")
    if "technician_id" in updates and updates["technician_id"] is not None:
        if await db.users.find_one({"id": updates["technician_id"]}) is None:
            raise HTTPException(status_code=404, detail=f"User '{updates['technician_id']}' not found")
    await db.work_orders.update_one({"id": work_order_id}, {"$set": updates})
    return without_mongo_id(await db.work_orders.find_one({"id": work_order_id}))


@router.patch("/{work_order_id}/status", response_model=OrderRead)
async def update_work_order_status(
    work_order_id: int,
    payload: OrderStatusUpdate,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN, UserRole.TECHNICIAN)),
):
    order = await db.work_orders.find_one({"id": work_order_id})
    if order is None:
        raise HTTPException(status_code=404, detail=f"Work Order '{work_order_id}' not found")
    completed_at = datetime.now() if payload.status == OrderStatus.COMPLETED else None
    await db.work_orders.update_one(
        {"id": work_order_id},
        {"$set": {"status": payload.status.value, "completed_at": completed_at}},
    )
    return without_mongo_id(await db.work_orders.find_one({"id": work_order_id}))


@router.delete("/{work_order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_work_order(
    work_order_id: int,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN, UserRole.TECHNICIAN)),
) -> Response:
    if await db.work_orders.find_one({"id": work_order_id}) is None:
        raise HTTPException(status_code=404, detail=f"Work Order '{work_order_id}' not found")
    await db.reports.delete_many({"work_order_id": work_order_id})
    await db.work_orders.delete_one({"id": work_order_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)