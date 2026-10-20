from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.database import next_id, to_mongo, without_mongo_id
from app.dependencies import get_current_user, get_db, require_role
from app.models import OrderStatus, User, UserRole
from app.schema.user import ActiveCallsRead, UserCreate, UserRead, UserUpdate
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
async def list_users(db=Depends(get_db), _: User = Depends(require_role(UserRole.ADMIN))):
    return [without_mongo_id(item) async for item in db.users.find().sort("id", 1)]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def post_user(
    payload: UserCreate,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    username = payload.username.strip().lower()
    if await db.users.find_one({"username": username}) is not None:
        raise HTTPException(status_code=400, detail=f"Username '{payload.username}' is already taken")
    if payload.facility_id is not None and await db.hospitals.find_one({"id": payload.facility_id}) is None:
        raise HTTPException(status_code=404, detail=f"Hospital '{payload.facility_id}' not found")
    user = to_mongo(payload.model_dump(exclude={"password"}))
    user.update(
        id=await next_id(db, "users"),
        username=username,
        hashed_password=hash_password(payload.password),
    )
    await db.users.insert_one(user)
    return user


@router.get("/active-calls/{technician_id}", response_model=list[ActiveCallsRead])
async def technicians_with_active_calls(
    technician_id: int,
    db=Depends(get_db),
    _: User = Depends(get_current_user),
):
    active_statuses = {OrderStatus.PENDING.value, OrderStatus.IN_PROGRESS.value}
    results = []
    users = await db.users.find({
        "id": technician_id,
        "role": UserRole.TECHNICIAN.value,
    }).sort("id", 1).to_list(None)
    for user in users:
        if user.get("facility_id") is None:
            continue
        if await db.hospitals.find_one({"id": user["facility_id"]}) is None:
            continue
        orders = await db.work_orders.find({
            "technician_id": user["id"],
            "status": {"$in": list(active_statuses)},
        }).to_list(None)
        if orders:
            results.append(ActiveCallsRead(
                technician_id=user["id"],
                first_name=user["first_name"],
                last_name=user["last_name"],
                active_call_count=len(orders),
            ))
    return results


@router.get("/{user_id}", response_model=UserRead)
async def get_user_by_id(
    user_id: int,
    db=Depends(get_db),
    _: User = Depends(get_current_user),
):
    user = without_mongo_id(await db.users.find_one({"id": user_id}))
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found")
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    updates = to_mongo(payload.model_dump(exclude_unset=True))
    user = await db.users.find_one({"id": user_id})
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found")
    if "facility_id" in updates and updates["facility_id"] is not None:
        if await db.hospitals.find_one({"id": updates["facility_id"]}) is None:
            raise HTTPException(status_code=404, detail=f"Hospital '{updates['facility_id']}' not found")
    if "username" in updates:
        updates["username"] = updates["username"].strip().lower()
        existing = await db.users.find_one({"username": updates["username"], "id": {"$ne": user_id}})
        if existing is not None:
            raise HTTPException(status_code=400, detail="Username is already taken")
    if "password" in updates:
        updates["hashed_password"] = hash_password(updates.pop("password"))
    await db.users.update_one({"id": user_id}, {"$set": updates})
    return without_mongo_id(await db.users.find_one({"id": user_id}))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> Response:
    if await db.users.find_one({"id": user_id}) is None:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found")
    if await db.hospitals.find_one({"supervisor_id": user_id}) is not None:
        raise HTTPException(status_code=409, detail="User supervises a hospital and cannot be deleted")
    await db.work_orders.update_many({"technician_id": user_id}, {"$set": {"technician_id": None}})
    await db.users.delete_one({"id": user_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)