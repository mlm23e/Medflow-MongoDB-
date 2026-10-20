from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.database import next_id, to_mongo, without_mongo_id
from app.dependencies import get_current_user, get_db, require_role
from app.models import User, UserRole
from app.schema.reports import ReportCreate, ReportRead, ReportUpdate

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=list[ReportRead])
async def list_reports(db=Depends(get_db), _: User = Depends(get_current_user)):
    return [without_mongo_id(item) async for item in db.reports.find().sort("id", 1)]


@router.post("", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def post_report(
    payload: ReportCreate,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN, UserRole.TECHNICIAN)),
):
    if await db.work_orders.find_one({"id": payload.work_order_id}) is None:
        raise HTTPException(status_code=404, detail=f"WorkOrder '{payload.work_order_id}' not found")
    report = to_mongo(payload.model_dump())
    report.update(id=await next_id(db, "reports"), timestamp=datetime.now())
    await db.reports.insert_one(report)
    return report


@router.get("/{id}", response_model=ReportRead)
async def get_report_by_id(id: int, db=Depends(get_db), _: User = Depends(get_current_user)):
    report = without_mongo_id(await db.reports.find_one({"id": id}))
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report '{id}' not found")
    return report


@router.patch("/{id}", response_model=ReportRead)
async def update_report(
    id: int,
    payload: ReportUpdate,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN, UserRole.TECHNICIAN)),
):
    updates = to_mongo(payload.model_dump(exclude_unset=True))
    if "work_order_id" in updates:
        if await db.work_orders.find_one({"id": updates["work_order_id"]}) is None:
            raise HTTPException(status_code=404, detail=f"WorkOrder '{updates['work_order_id']}' not found")
    result = await db.reports.update_one({"id": id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Report Log '{id}' not found")
    return without_mongo_id(await db.reports.find_one({"id": id}))


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    id: int,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> Response:
    result = await db.reports.delete_one({"id": id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Report Log '{id}' not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)