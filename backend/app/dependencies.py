import jwt

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.database import database, initialize_database, without_mongo_id
from app.models import User, UserRole

from app.security import decode_access_token

# We need to create a dependency that will extract the current user from the JWT access token 
# provided in the authorization header of the request
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

async def get_db():
    await initialize_database()
    yield database


async def get_current_user(
        token : str = Depends(oauth2_scheme),
        db = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail = "Could not validate credentials",
        headers={"WWW-Authenticate" : "Bearer"}
    )
    try:
        payload = decode_access_token(token)
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception

    user = await db.users.find_one({"username": username})
    if user is None:
        raise credentials_exception
    return User.model_validate(without_mongo_id(user))

def require_role(*allowed_role : UserRole):
    async def role_checker(current_user : User = Depends(get_current_user))-> User:
        print("DEBUG CURRENT_USER:", type(current_user), current_user) # <-- Check this output
        if current_user.role not in allowed_role:
            raise HTTPException(
                status_code= status.HTTP_403_FORBIDDEN,
                detail=(f"Role {current_user.role.value} is not permitted to perform this action")
            )
        return current_user
    return role_checker

