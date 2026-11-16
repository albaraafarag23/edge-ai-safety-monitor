"""User management (admins only) and changing your own password."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

import alert_settings
import auth
from models import SessionLocal, User

Role = Literal["manager", "supervisor", "viewer"]


class UserIn(BaseModel):
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+$")
    name: str = Field(min_length=1, max_length=100)
    role: Role = "supervisor"
    password: str


class UserPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    role: Role | None = None
    active: bool | None = None


class PasswordReset(BaseModel):
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(auth.require_manager)])
account = APIRouter(prefix="/auth", tags=["auth"])


async def _active_managers(session) -> int:
    return await session.scalar(
        select(func.count()).select_from(User).where(User.role == "manager", User.active.is_(True)))


@router.get("")
async def list_users():
    async with SessionLocal() as session:
        users = (await session.scalars(select(User).order_by(User.created_at))).all()
    return [u.to_dict() for u in users]


@router.post("", status_code=201)
async def add_user(body: UserIn):
    auth.check_password_rules(body.password)
    try:
        user = await auth.create_user(body.email, body.name, body.password, body.role)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    await alert_settings.sync_redis()   # a new manager or supervisor gets High and Critical by default
    return user.to_dict()


@router.patch("/{user_id}")
async def update_user(user_id: int, body: UserPatch, me: User = Depends(auth.current_user)):
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user.to_dict()["demo"] and body.role not in (None, "viewer"):
            raise HTTPException(status_code=409, detail="The demo account stays read-only")
        removes_manager = user.role == "manager" and user.active and (
            (body.role is not None and body.role != "manager") or body.active is False)
        if removes_manager and user.id == me.id:
            raise HTTPException(status_code=409, detail="You can't remove your own manager access")
        if removes_manager and await _active_managers(session) <= 1:
            raise HTTPException(status_code=409, detail="There must be at least one active manager")
        for field in ("name", "role", "active"):
            value = getattr(body, field)
            if value is not None:
                setattr(user, field, value)
        await session.commit()
        auth.forget_users()   # role, password or switch-off applies to the next request
        await alert_settings.sync_redis()   # and who gets email
        return user.to_dict()


@router.post("/{user_id}/password", status_code=204)
async def reset_password(user_id: int, body: PasswordReset):
    """Admin sets a new password (e.g. a temporary one). The user's sessions end."""
    auth.check_password_rules(body.password)
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.password_hash = auth.hash_password(body.password)
        await session.commit()
        auth.forget_users()   # role, password or switch-off applies to the next request
        await alert_settings.sync_redis()   # and who gets email


@account.post("/password")
async def change_own_password(body: PasswordChange, response: Response, me: User = Depends(auth.current_user)):
    """Change your own password. Other sessions end; this one gets a fresh cookie."""
    if me.to_dict()["demo"]:
        raise HTTPException(status_code=403, detail="The demo account's password can't be changed")
    if not auth.verify_password(body.current_password, me.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    auth.check_password_rules(body.new_password)
    async with SessionLocal() as session:
        user = await session.get(User, me.id)
        user.password_hash = auth.hash_password(body.new_password)
        await session.commit()
        auth.forget_users()   # role, password or switch-off applies to the next request
        await alert_settings.sync_redis()   # and who gets email
    auth.set_session_cookie(response, user)
    return user.to_dict()
