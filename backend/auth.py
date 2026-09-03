"""Shared authentication and session-validation for the LIMS API.

Single source of truth for JWT validation, server-side session checks, role
gating, and the temporary-password gate. Imported by both server.py and
batches.py so every protected endpoint enforces the same rules.
"""
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt
from fastapi import HTTPException, Request, Depends

from database import db

JWT_ALG = "HS256"

# Paths a user with a temporary password may still call. Exact-match set so a
# future route cannot accidentally inherit the exemption by sharing a prefix.
PASSWORD_EXEMPT_PATHS = {
    "/api/auth/me",
    "/api/auth/logout",
    "/api/auth/change-password",
    "/api/auth/refresh",
}


async def session_is_active(sid: Optional[str], user_id: Optional[str] = None) -> bool:
    if not sid or not user_id:
        return False
    session = await db.auth_sessions.find_one({"id": sid, "user_id": user_id})
    return bool(session) and not session.get("revoked", False)


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    if not await session_is_active(payload.get("sid"), payload.get("sub")):
        raise HTTPException(status_code=401, detail="Session has been revoked. Please sign in again.")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user or not user.get("active", True):
        raise HTTPException(status_code=401, detail="User inactive or not found")
    if user.get("must_change_password") and request.url.path not in PASSWORD_EXEMPT_PATHS:
        raise HTTPException(status_code=403,
                            detail="Your temporary password must be changed before using the system")
    user["session_id"] = payload.get("sid")
    return user


def require_roles(*roles):
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions for this action")
        return user
    return dep
