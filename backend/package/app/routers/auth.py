from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.database import next_id, to_mongo, without_mongo_id
from app.dependencies import get_current_user, get_db, require_role
from app.models import User, UserRole
from app.schema.user import Token, UserCreate, UserRead
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)) -> Token:
    username = form_data.username.strip().lower()
    user_doc = await db.users.find_one({"username": username})
    user = User.model_validate(without_mongo_id(user_doc)) if user_doc else None
    if user is None or not verify_password(user.hashed_password, form_data.password):
        raise HTTPException(
            detail="Incorrect username or password",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.username, "role": user.role.value})
    return Token(access_token=access_token, token_type="bearer")


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserCreate,
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    username = payload.username.strip().lower()
    if await db.users.find_one({"username": username}) is not None:
        raise HTTPException(status_code=400, detail=f"Username {payload.username} is already taken")
    user = to_mongo(payload.model_dump(exclude={"password"}))
    user.update(
        id=await next_id(db, "users"),
        username=username,
        hashed_password=hash_password(payload.password),
    )
    await db.users.insert_one(user)
    return user