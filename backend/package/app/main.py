import asyncio
import os

import boto3
from botocore.config import Config

from mangum import Mangum

from fastapi import Request # day 10
from fastapi.responses import JSONResponse # day 10
from fastapi import FastAPI
from fastapi import Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware # day 7 - update
from pymongo.errors import DuplicateKeyError

from app.routers import equipment, hospitals, reports, work_orders, users, auth

from app.config import settings # day 11 update
from app.dependencies import get_db, require_role
from app.models import User, UserRole
from app.scripts.upload_report import BUCKET_NAME
FRONTEND_ORIGIN = settings.frontend_origin

HEALTH_CHECK_TIMEOUT_SECONDS = 2
S3_CHECK_TIMEOUT_SECONDS = 3

app = FastAPI(
    title="Medflow Clinical Equipment Command Center",
    description="Hospital Management API for Halcyon Health Systems",
    version="0.1.0"
)


#CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        settings.frontend_origin,
        "https://ld12s0csjxq85o6.cloudfront.net"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include our routers in our API
app.include_router(equipment.router)
app.include_router(hospitals.router)
app.include_router(reports.router)
app.include_router(work_orders.router)
app.include_router(users.router)
app.include_router(auth.router)


# Simple health endpoint to validate the application is running correctly
@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


async def database_is_available(db) -> bool:
    try:
        await asyncio.wait_for(
            db.command("ping"),
            timeout=HEALTH_CHECK_TIMEOUT_SECONDS,
        )
    except Exception:
        return False
    return True


def check_s3_bucket() -> None:
    client = boto3.client(
        "s3",
        config=Config(
            connect_timeout=1,
            read_timeout=1,
            retries={"max_attempts": 0},
        ),
    )
    client.head_bucket(Bucket=BUCKET_NAME)


async def s3_is_available() -> bool:
    try:
        await asyncio.wait_for(
            asyncio.to_thread(check_s3_bucket),
            timeout=S3_CHECK_TIMEOUT_SECONDS,
        )
    except Exception:
        return False
    return True


@app.get("/health/ready", tags=["health"])
async def readiness_check(
    db=Depends(get_db),
) -> dict[str, str]:
    if not await database_is_available(db):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "database": "unavailable"},
        )
    return {"status": "ready", "database": "reachable"}


@app.get("/health/detail", tags=["health"])
async def health_detail(
    db=Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> dict[str, dict[str, str]]:
    database_status = "ok" if await database_is_available(db) else "unavailable"
    s3_status = "ok" if await s3_is_available() else "unavailable"
    return {
        "database": {"status": database_status},
        "s3": {"status": s3_status},
    }

##Endpoint to check the version number (day 10)
@app.get("/version", tags=["health"])
async def version() -> dict[str, str]:
    return {"version": app.version}

# ---------------------------------
# BEGIN EXCEPTION HANDLING (day 10)
# ---------------------------------

# this exception handles when our database constraint (our battery_level NOT being between 0 and 100) 
# is violated. This is a common error that we want to handle gracefully
@app.exception_handler(DuplicateKeyError)
async def duplicate_key_error_handler(request: Request, exception: DuplicateKeyError):
    return JSONResponse(
        status_code=409, #CONFLICT
        content={"detail": "A database constraint was violated (e.g. a duplicate value)."}
    )

# this is a catch-all exception handler so that any unexpected failure 
# (bugs or unknown conditions) returns a constant JSON response
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exception: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred."}
    )