from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

import bcrypt
import jwt
import secrets
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

from database import client, db
from auth import get_current_user, require_roles, session_is_active
from instrument_traceability import (
    assert_result_instruments,
    sample_instrument_issues,
    sample_with_traceability,
    seed_traceability_master_data,
)
from sample_integrity import outstanding_required_parameters

app = FastAPI(title="LIMS API")
api = APIRouter(prefix="/api")

JWT_ALG = "HS256"
ROLES = ("admin", "qa", "qc")
logger = logging.getLogger("lims")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").strip().lower() not in {
    "0", "false", "no", "off"
}
COOKIE_SAMESITE = "none" if COOKIE_SECURE else "lax"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str, email: str, role: str, sid: str) -> str:
    payload = {"sub": user_id, "email": email, "role": role, "type": "access", "sid": sid,
               "exp": datetime.now(timezone.utc) + timedelta(hours=8)}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALG)


def create_refresh_token(user_id: str, sid: str) -> str:
    payload = {"sub": user_id, "type": "refresh", "sid": sid,
               "exp": datetime.now(timezone.utc) + timedelta(days=7)}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALG)


async def start_session(user_id: str) -> str:
    sid = new_id()
    await db.auth_sessions.insert_one({"id": sid, "user_id": user_id, "created_at": now_iso(),
                                       "revoked": False})
    return sid


async def revoke_session(sid: str, user_id: str) -> bool:
    result = await db.auth_sessions.update_one(
        {"id": sid, "user_id": user_id},
        {"$set": {"revoked": True, "revoked_at": now_iso()}})
    return result.modified_count == 1


async def revoke_all_sessions(user_id: str) -> int:
    result = await db.auth_sessions.update_many(
        {"user_id": user_id, "revoked": False},
        {"$set": {"revoked": True, "revoked_at": now_iso()}})
    return result.modified_count


def generate_temporary_password() -> str:
    """Cryptographically secure temporary password; only its hash is ever stored."""
    return secrets.token_urlsafe(18)


def set_auth_cookies(response: Response, access: str, refresh: str):
    response.set_cookie("access_token", access, httponly=True, secure=COOKIE_SECURE,
                        samesite=COOKIE_SAMESITE, max_age=28800, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=COOKIE_SECURE,
                        samesite=COOKIE_SAMESITE, max_age=604800, path="/")


# ---------- Models ----------
class LoginIn(BaseModel):
    email: str
    password: str


class UserIn(BaseModel):
    email: str
    password: Optional[str] = None
    name: str
    initials: str
    role: str = "qc"


class FirstRunIn(BaseModel):
    email: str
    password: str
    name: str
    initials: str = "SA"


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    initials: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None


class SamplePointIn(BaseModel):
    name: str
    description: str = ""
    active: bool = True


class ParameterIn(BaseModel):
    name: str
    units: str = ""
    method: str = ""
    value_type: str = "numeric"  # numeric | text
    options: List[str] = []
    instrument_required: bool = False
    instrument_category: str = "MANUAL_NOT_CURRENTLY_CONTROLLED"


class SpecIn(BaseModel):
    sample_point_id: str
    parameter_id: str
    lower_limit: Optional[float] = None
    upper_limit: Optional[float] = None
    expected_text: Optional[str] = None
    active: bool = True


class SampleIn(BaseModel):
    sample_point_id: str
    sample_date: str
    sample_time: str = ""
    analyst_initials: str = ""
    notes: str = ""


class ResultIn(BaseModel):
    parameter_id: str
    value_numeric: Optional[float] = None
    value_text: Optional[str] = None
    instrument_id: Optional[str] = None
    comment: str = ""


class ResultsIn(BaseModel):
    results: List[ResultIn]


class DecisionIn(BaseModel):
    comment: str = ""


# ---------- Audit ----------
async def audit(user: Optional[dict], action: str, entity: str, entity_id: str,
                before: Any = None, after: Any = None, reason: str = ""):
    await db.audit_trail.insert_one({
        "id": new_id(),
        "timestamp": now_iso(),
        "user_id": (user or {}).get("id", ""),
        "user_email": (user or {}).get("email", "system"),
        "user_role": (user or {}).get("role", "system"),
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "before": before,
        "after": after,
        "reason": reason,
    })


# ---------- Auth routes ----------
@api.post("/auth/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = body.email.lower()
    ident = f"{request.client.host if request.client else 'x'}:{email}"
    attempt = await db.login_attempts.find_one({"identifier": ident})
    if attempt and attempt.get("count", 0) >= 5:
        locked_until = datetime.fromisoformat(attempt["last"]) + timedelta(minutes=15)
        if datetime.now(timezone.utc) < locked_until:
            raise HTTPException(status_code=429, detail="Account temporarily locked. Try again in 15 minutes.")
        await db.login_attempts.delete_one({"identifier": ident})

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": ident},
            {"$inc": {"count": 1}, "$set": {"last": now_iso()}}, upsert=True)
        await audit(None, "LOGIN_FAILED", "auth", email, after={"identifier": ident})
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("active", True):
        raise HTTPException(status_code=403, detail="Account is inactive. Contact an administrator.")

    await db.login_attempts.delete_one({"identifier": ident})
    sid = await start_session(user["id"])
    access = create_access_token(user["id"], user["email"], user["role"], sid)
    set_auth_cookies(response, access, create_refresh_token(user["id"], sid))
    safe = {k: v for k, v in user.items() if k not in ("_id", "password_hash")}
    await audit(safe, "LOGIN", "auth", user["id"], after={"identifier": ident, "session_id": sid})
    return {"user": safe, "access_token": access,
            "must_change_password": bool(user.get("must_change_password"))}


@api.post("/auth/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    if user.get("session_id"):
        await revoke_session(user["session_id"], user["id"])
    await audit(user, "LOGOUT", "auth", user["id"], after={"session_id": user.get("session_id")})
    return {"ok": True}


@api.get("/auth/provisioning-status")
async def provisioning_status():
    """First-run provisioning is available only while no administrator exists."""
    admins = await db.users.count_documents({"role": "admin"})
    return {"first_run_available": admins == 0, "administrator_exists": admins > 0}


@api.post("/auth/first-run")
async def first_run(body: FirstRunIn, response: Response):
    if await db.users.count_documents({"role": "admin"}) > 0:
        raise HTTPException(status_code=403,
                            detail="First-run provisioning is disabled because an administrator already exists")
    if len(body.password) < 12:
        raise HTTPException(status_code=400,
                            detail="The initial administrator password must be at least 12 characters")
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="A user with this email already exists")
    doc = {"id": new_id(), "email": email, "name": body.name, "initials": body.initials.upper(),
           "role": "admin", "active": True, "must_change_password": False,
           "password_hash": hash_password(body.password), "created_at": now_iso(),
           "created_via": "FIRST_RUN"}
    await db.users.insert_one(dict(doc))
    safe = {k: v for k, v in doc.items() if k != "password_hash"}
    sid = await start_session(doc["id"])
    access = create_access_token(doc["id"], email, "admin", sid)
    set_auth_cookies(response, access, create_refresh_token(doc["id"], sid))
    await audit(safe, "FIRST_RUN_ADMIN_PROVISIONED", "user", doc["id"], after=safe)
    return {"user": safe, "access_token": access}


@api.post("/auth/change-password")
async def change_password(body: ChangePasswordIn, user: dict = Depends(get_current_user)):
    record = await db.users.find_one({"id": user["id"]})
    if not record or not verify_password(body.current_password, record["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if verify_password(body.new_password, record["password_hash"]):
        raise HTTPException(status_code=400, detail="The new password must differ from the current password")
    await db.users.update_one({"id": user["id"]}, {"$set": {
        "password_hash": hash_password(body.new_password),
        "must_change_password": False,
        "password_changed_at": now_iso()}})
    revoked = await revoke_all_sessions(user["id"])
    await audit(user, "PASSWORD_CHANGED", "user", user["id"],
                after={"sessions_revoked": revoked, "must_change_password": False})
    return {"ok": True, "sessions_revoked": revoked}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@api.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALG])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    if not await session_is_active(payload.get("sid"), payload.get("sub")):
        raise HTTPException(status_code=401, detail="Session has been revoked. Please sign in again.")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user or not user.get("active", True):
        raise HTTPException(status_code=401, detail="User inactive or not found")
    await revoke_session(payload["sid"], user["id"])
    sid = await start_session(user["id"])
    access = create_access_token(user["id"], user["email"], user["role"], sid)
    set_auth_cookies(response, access, create_refresh_token(user["id"], sid))
    return {"user": user, "access_token": access}


# ---------- Users (admin) ----------
@api.get("/users")
async def list_users(user: dict = Depends(require_roles("admin"))):
    return await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", 1).to_list(500)


@api.post("/users")
async def create_user(body: UserIn, user: dict = Depends(require_roles("admin"))):
    if body.role not in ROLES:
        raise HTTPException(status_code=400, detail="Role must be admin, qa or qc")
    temporary = not body.password
    password = body.password or generate_temporary_password()
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="A user with this email already exists")
    doc = {"id": new_id(), "email": email, "name": body.name, "initials": body.initials.upper(),
           "role": body.role, "active": True, "password_hash": hash_password(password),
           "must_change_password": True, "created_at": now_iso(), "created_by": user["email"]}
    await db.users.insert_one(dict(doc))
    safe = {k: v for k, v in doc.items() if k != "password_hash"}
    await audit(user, "CREATE", "user", doc["id"], after=safe)
    if temporary:
        # The generated value is shown once to the administrator and only its hash is stored.
        return {**safe, "temporary_password_issued": True}
    return safe


@api.patch("/users/{user_id}")
async def update_user(user_id: str, body: UserUpdate, user: dict = Depends(require_roles("admin"))):
    existing = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    updates = {k: v for k, v in body.model_dump(exclude_none=True).items() if k != "password"}
    if body.role and body.role not in ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    events = []
    if body.password:
        if len(body.password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        updates["password_hash"] = hash_password(body.password)
        updates["must_change_password"] = True
        updates["password_reset_at"] = now_iso()
        events.append("PASSWORD_RESET")
    if body.active is False:
        events.append("USER_DEACTIVATED")
    if body.active is True and existing.get("active") is False:
        events.append("USER_ACTIVATED")
    if body.role and body.role != existing.get("role"):
        events.append("ROLE_CHANGED")
    if updates:
        await db.users.update_one({"id": user_id}, {"$set": updates})
    revoked = 0
    if body.password or body.active is False or (body.role and body.role != existing.get("role")):
        revoked = await revoke_all_sessions(user_id)
    after = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    await audit(user, "UPDATE", "user", user_id, before=existing, after=after)
    for event in events:
        await audit(user, event, "user", user_id,
                    before={"role": existing.get("role"), "active": existing.get("active")},
                    after={"role": after.get("role"), "active": after.get("active"),
                           "sessions_revoked": revoked})
    return after


# ---------- Sample points ----------
@api.get("/sample-points")
async def list_sample_points(user: dict = Depends(get_current_user)):
    return await db.sample_points.find({}, {"_id": 0}).sort("name", 1).to_list(1000)


@api.post("/sample-points")
async def create_sample_point(body: SamplePointIn, user: dict = Depends(require_roles("admin", "qa"))):
    doc = {"id": new_id(), **body.model_dump(), "created_at": now_iso()}
    await db.sample_points.insert_one(dict(doc))
    await audit(user, "CREATE", "sample_point", doc["id"], after=doc)
    return doc


# ---------- Parameters ----------
@api.get("/parameters")
async def list_parameters(user: dict = Depends(get_current_user)):
    return await db.parameters.find({}, {"_id": 0}).sort("name", 1).to_list(300)


@api.post("/parameters")
async def create_parameter(body: ParameterIn, user: dict = Depends(require_roles("admin", "qa"))):
    doc = {"id": new_id(), **body.model_dump(), "created_at": now_iso()}
    await db.parameters.insert_one(dict(doc))
    await audit(user, "CREATE", "parameter", doc["id"], after=doc)
    return doc


# ---------- Specifications ----------
@api.get("/specifications")
async def list_specs(sample_point_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {"sample_point_id": sample_point_id} if sample_point_id else {}
    return await db.specifications.find(q, {"_id": 0}).to_list(1000)


@api.post("/specifications")
async def create_spec(body: SpecIn, user: dict = Depends(require_roles("admin", "qa"))):
    doc = {"id": new_id(), **body.model_dump(), "created_at": now_iso(), "version": 1}
    await db.specifications.insert_one(dict(doc))
    await audit(user, "CREATE", "specification", doc["id"], after=doc)
    return doc


@api.put("/specifications/{spec_id}")
async def update_spec(spec_id: str, body: SpecIn, user: dict = Depends(require_roles("admin", "qa"))):
    before = await db.specifications.find_one({"id": spec_id}, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Specification not found")
    updates = body.model_dump()
    updates["version"] = before.get("version", 1) + 1
    updates["updated_at"] = now_iso()
    await db.specifications.update_one({"id": spec_id}, {"$set": updates})
    after = await db.specifications.find_one({"id": spec_id}, {"_id": 0})
    await audit(user, "UPDATE", "specification", spec_id, before=before, after=after)
    return after


@api.delete("/specifications/{spec_id}")
async def delete_spec(spec_id: str, user: dict = Depends(require_roles("admin"))):
    before = await db.specifications.find_one({"id": spec_id}, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Specification not found")
    await db.specifications.delete_one({"id": spec_id})
    await audit(user, "DELETE", "specification", spec_id, before=before)
    return {"ok": True}


# ---------- Samples ----------
async def next_record_id(sample_date: str) -> str:
    datepart = sample_date.replace("-", "")[:8]
    count = await db.samples.count_documents({})
    return f"REC-{datepart}-{count + 1:04d}"


def evaluate_numeric(spec: dict, value: float) -> str:
    lo, hi = spec.get("lower_limit"), spec.get("upper_limit")
    if lo is not None and value < lo:
        return "FAIL"
    if hi is not None and value > hi:
        return "FAIL"
    if hi is not None and hi > 0 and value >= 0.9 * hi:
        return "WARN"
    return "PASS"


def evaluate(spec: Optional[dict], r: dict) -> str:
    if not spec:
        return "NO_SPEC"
    if r.get("value_numeric") is None:
        expected = (spec.get("expected_text") or "").strip().lower()
        if not expected:
            return "NO_SPEC"
        return "PASS" if (r.get("value_text") or "").strip().lower() == expected else "FAIL"
    return evaluate_numeric(spec, r["value_numeric"])


@api.post("/samples")
async def create_sample(body: SampleIn, user: dict = Depends(require_roles("admin", "qc", "qa"))):
    sp = await db.sample_points.find_one({"id": body.sample_point_id}, {"_id": 0})
    if not sp:
        raise HTTPException(status_code=404, detail="Sample point not found")
    doc = {
        "id": new_id(),
        "record_id": await next_record_id(body.sample_date),
        "sample_point_id": sp["id"],
        "sample_point_name": sp["name"],
        "sample_date": body.sample_date,
        "sample_time": body.sample_time,
        "analyst_initials": body.analyst_initials or user.get("initials", ""),
        "analyst_id": user["id"],
        "notes": body.notes,
        "status": "OPEN",
        "qa_status": "Not Submitted",
        "overall_result": "PENDING",
        "results": [],
        "created_at": now_iso(),
        "created_by": user["email"],
    }
    await db.samples.insert_one(dict(doc))
    await audit(user, "CREATE", "sample", doc["id"], after=doc)
    return doc


@api.get("/samples")
async def list_samples(status: Optional[str] = None, qa_status: Optional[str] = None,
                       sample_point_id: Optional[str] = None, search: Optional[str] = None,
                       user: dict = Depends(get_current_user)):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if qa_status:
        q["qa_status"] = qa_status
    if sample_point_id:
        q["sample_point_id"] = sample_point_id
    if search:
        q["record_id"] = {"$regex": search, "$options": "i"}
    return await db.samples.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@api.get("/samples/{sample_id}")
async def get_sample(sample_id: str, user: dict = Depends(get_current_user)):
    s = await db.samples.find_one({"id": sample_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Sample not found")
    return await sample_with_traceability(s)


def build_sample_result(item, parameter: dict, spec: Optional[dict], prev: Optional[dict], user: dict) -> dict:
    r = item.model_dump()
    r["parameter_name"] = parameter["name"]
    r["units"] = parameter.get("units", "")
    r["status"] = evaluate(spec, r)
    r["entered_by"] = user["email"]
    r["entered_at"] = now_iso()
    r["revision"] = (prev.get("revision", 1) + 1) if prev else 1
    return r


def overall_result(results: list, complete: bool) -> str:
    """Deterministic overall status.

    A sample is only PASS when every required spec parameter has a definitive
    result AND none of them failed. A single missing/pending required result
    keeps the sample PENDING even if every entered result passes. A single
    FAIL always dominates.
    """
    statuses = [r["status"] for r in results]
    if "FAIL" in statuses:
        return "FAIL"
    if not complete:
        return "PENDING"
    if "WARN" in statuses:
        return "WARN"
    return "PASS" if results else "PENDING"


@api.post("/samples/{sample_id}/results")
async def save_results(sample_id: str, body: ResultsIn,
                       user: dict = Depends(require_roles("admin", "qc"))):
    sample = await db.samples.find_one({"id": sample_id}, {"_id": 0})
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    if sample["qa_status"] == "Approved":
        raise HTTPException(status_code=400, detail="Approved samples are locked. Results cannot be changed.")
    specs = await db.specifications.find({"sample_point_id": sample["sample_point_id"]}, {"_id": 0}).to_list(500)
    spec_map = {s["parameter_id"]: s for s in specs}
    params = {p["id"]: p for p in await db.parameters.find({}, {"_id": 0}).to_list(300)}

    await assert_result_instruments(body.results, params)

    existing = {r["parameter_id"]: r for r in sample.get("results", [])}
    for item in body.results:
        parameter = params.get(item.parameter_id)
        if not parameter:
            continue
        prev = existing.get(item.parameter_id)
        r = build_sample_result(item, parameter, spec_map.get(item.parameter_id), prev, user)
        if prev:
            await audit(user, "UPDATE_RESULT", "sample_result", sample_id,
                        before=prev, after=r, reason=item.comment)
        else:
            await audit(user, "ENTER_RESULT", "sample_result", sample_id, after=r)
        existing[item.parameter_id] = r

    results = list(existing.values())
    active_specs = [s for s in specs if s.get("active", True)]
    required_ids = {s["parameter_id"] for s in active_specs}
    definitive_ids = {r["parameter_id"] for r in results
                      if r.get("status") in ("PASS", "WARN", "FAIL")}
    complete = bool(required_ids) and required_ids.issubset(definitive_ids)
    await db.samples.update_one({"id": sample_id}, {"$set": {
        "results": results, "overall_result": overall_result(results, complete),
        "status": "COMPLETE" if complete else "IN_PROGRESS",
        "updated_at": now_iso()}})
    updated = await db.samples.find_one({"id": sample_id}, {"_id": 0})
    return await sample_with_traceability(updated)


@api.post("/samples/{sample_id}/submit")
async def submit_sample(sample_id: str, body: DecisionIn, user: dict = Depends(require_roles("admin", "qc"))):
    sample = await db.samples.find_one({"id": sample_id}, {"_id": 0})
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    if not sample.get("results"):
        raise HTTPException(status_code=400, detail="Enter at least one result before submitting for QA review")
    outstanding = await outstanding_required_parameters(sample)
    if outstanding:
        raise HTTPException(status_code=422, detail={
            "message": "Cannot submit: required results are missing",
            "outstanding_parameters": outstanding,
        })
    instrument_issues = await sample_instrument_issues(sample)
    if instrument_issues:
        raise HTTPException(status_code=422, detail={
            "message": "Cannot submit: instrument traceability must be corrected",
            "instrument_issues": instrument_issues,
        })
    await db.samples.update_one({"id": sample_id}, {"$set": {
        "qa_status": "Pending Review", "submitted_by": user["email"],
        "submitted_at": now_iso(), "submit_comment": body.comment}})
    await audit(user, "SUBMIT_FOR_REVIEW", "sample", sample_id,
                before={"qa_status": sample["qa_status"]}, after={"qa_status": "Pending Review"},
                reason=body.comment)
    return await db.samples.find_one({"id": sample_id}, {"_id": 0})


@api.post("/samples/{sample_id}/decision/{decision}")
async def qa_decision(sample_id: str, decision: str, body: DecisionIn,
                      user: dict = Depends(require_roles("admin", "qa"))):
    mapping = {"approve": "Approved", "reject": "Requires Investigation"}
    if decision not in mapping:
        raise HTTPException(status_code=400, detail="Decision must be approve or reject")
    sample = await db.samples.find_one({"id": sample_id}, {"_id": 0})
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    if sample["qa_status"] != "Pending Review":
        raise HTTPException(status_code=400, detail="Only samples pending review can be signed off")
    if decision == "reject" and not body.comment.strip():
        raise HTTPException(status_code=400, detail="A reason is required when rejecting a record")
    if decision == "approve":
        outstanding = await outstanding_required_parameters(sample)
        if outstanding:
            raise HTTPException(status_code=422, detail={
                "message": "Cannot approve: required results are missing",
                "outstanding_parameters": outstanding,
            })
        instrument_issues = await sample_instrument_issues(sample)
        if instrument_issues:
            raise HTTPException(status_code=422, detail={
                "message": "Cannot approve: instrument traceability must be corrected",
                "instrument_issues": instrument_issues,
            })
    new_status = mapping[decision]
    await db.samples.update_one({"id": sample_id}, {"$set": {
        "qa_status": new_status,
        "status": "CLOSED" if decision == "approve" else "IN_PROGRESS",
        "qa_reviewer": user["email"], "qa_reviewed_at": now_iso(),
        "qa_comment": body.comment}})
    if decision == "reject" or sample.get("overall_result") == "FAIL":
        await db.oos_log.insert_one({
            "id": new_id(), "sample_id": sample_id, "record_id": sample["record_id"],
            "sample_point_name": sample["sample_point_name"], "raised_at": now_iso(),
            "raised_by": user["email"], "reason": body.comment or "Out of specification result",
            "status": "Open"})
    await audit(user, "QA_APPROVE" if decision == "approve" else "QA_REJECT", "sample", sample_id,
                before={"qa_status": sample["qa_status"]}, after={"qa_status": new_status},
                reason=body.comment)
    return await db.samples.find_one({"id": sample_id}, {"_id": 0})


@api.get("/samples/{sample_id}/coa")
async def coa(sample_id: str, user: dict = Depends(get_current_user)):
    sample = await db.samples.find_one({"id": sample_id}, {"_id": 0})
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    outstanding = await outstanding_required_parameters(sample)
    if outstanding:
        raise HTTPException(status_code=422, detail={
            "message": "Cannot issue an ordinary CoA: required results are missing",
            "outstanding_parameters": outstanding,
        })
    instrument_issues = await sample_instrument_issues(sample)
    if instrument_issues:
        raise HTTPException(status_code=422, detail={
            "message": "Cannot issue an ordinary CoA: instrument traceability must be corrected",
            "instrument_issues": instrument_issues,
        })
    specs = await db.specifications.find({"sample_point_id": sample["sample_point_id"]}, {"_id": 0}).to_list(500)
    await audit(user, "EXPORT_COA", "sample", sample_id)
    return {"sample": sample, "specifications": specs, "generated_at": now_iso(),
            "generated_by": user["email"]}


# ---------- Audit trail & OOS ----------
@api.get("/audit-trail")
async def get_audit(entity: Optional[str] = None, entity_id: Optional[str] = None,
                    action: Optional[str] = None, user_email: Optional[str] = None,
                    limit: int = 300, user: dict = Depends(require_roles("admin", "qa", "qc"))):
    q: Dict[str, Any] = {}
    for k, v in (("entity", entity), ("entity_id", entity_id), ("action", action), ("user_email", user_email)):
        if v:
            q[k] = v
    return await db.audit_trail.find(q, {"_id": 0}).sort("timestamp", -1).to_list(min(limit, 1000))


@api.get("/oos-log")
async def oos_log(user: dict = Depends(get_current_user)):
    return await db.oos_log.find({}, {"_id": 0}).sort("raised_at", -1).to_list(500)


# ---------- Dashboard ----------
@api.get("/dashboard")
async def dashboard(user: dict = Depends(get_current_user)):
    samples = await db.samples.find({}, {"_id": 0}).to_list(2000)
    by_status: Dict[str, int] = {}
    by_qa: Dict[str, int] = {}
    for s in samples:
        by_status[s["status"]] = by_status.get(s["status"], 0) + 1
        by_qa[s["qa_status"]] = by_qa.get(s["qa_status"], 0) + 1
    trend: Dict[str, Dict[str, int]] = {}
    for s in samples:
        d = s["sample_date"][:10]
        t = trend.setdefault(d, {"date": d, "pass": 0, "fail": 0, "warn": 0})
        if s["overall_result"] == "PASS":
            t["pass"] += 1
        elif s["overall_result"] == "FAIL":
            t["fail"] += 1
        elif s["overall_result"] == "WARN":
            t["warn"] += 1
    recent = sorted(samples, key=lambda x: x.get("created_at", ""), reverse=True)[:8]
    return {
        "total_samples": len(samples),
        "pending_review": by_qa.get("Pending Review", 0),
        "approved": by_qa.get("Approved", 0),
        "investigations": by_qa.get("Requires Investigation", 0),
        "failures": len([s for s in samples if s["overall_result"] == "FAIL"]),
        "by_status": by_status,
        "by_qa_status": by_qa,
        "trend": sorted(trend.values(), key=lambda x: x["date"])[-14:],
        "recent_samples": recent,
        "open_oos": await db.oos_log.count_documents({"status": "Open"}),
    }


# ---------- Seed ----------
DEFAULT_PARAMS = [
    {"name": "Appearance", "units": "", "method": "2.C.10", "value_type": "text",
     "options": ["Clear Colourless", "Very Slightly Hazy", "Slightly Hazy", "Hazy", "Turbid"]},
    {"name": "pH", "units": "pH", "method": "2.P.2", "value_type": "numeric", "options": []},
    {"name": "COD", "units": "mg/L", "method": "2.C.3", "value_type": "numeric", "options": []},
    {"name": "Ammonia", "units": "mg/L", "method": "2.A.31", "value_type": "numeric", "options": []},
    {"name": "Methanol", "units": "mg/L", "method": "2.M.6", "value_type": "numeric", "options": []},
    {"name": "Formaldehyde", "units": "mg/L", "method": "2.F.10", "value_type": "numeric", "options": []},
    {"name": "Suspended Solids", "units": "mg/L", "method": "2.S.10", "value_type": "numeric", "options": []},
]

DEFAULT_POINTS = [
    ("Final Effluent", "Discharge point to river"),
    ("Lower Lagoon", "Lagoon holding stage"),
    ("Aerator", "Aeration basin"),
    ("W1", "Process water line 1"),
    ("Culvert", "Site culvert monitoring"),
    ("Down River", "Downstream environmental monitoring"),
]

DEFAULT_LIMITS = {
    "Final Effluent": {"pH": (5, 9), "COD": (0, 800), "Ammonia": (0, 60.7), "Methanol": (0, 50),
                       "Formaldehyde": (0, 10), "Suspended Solids": (0, 400)},
    "Lower Lagoon": {"pH": (5, 10), "COD": (0, 2000), "Ammonia": (0, 80)},
    "Aerator": {"pH": (6, 9), "COD": (0, 5000), "Suspended Solids": (0, 500)},
    "W1": {"pH": (6, 8.5), "Formaldehyde": (0, 0.25), "Suspended Solids": (0, 20), "Ammonia": (0, 6),
           "Methanol": (0, 25)},
    "Culvert": {"COD": (0, 50), "Ammonia": (0, 4.1), "Suspended Solids": (0, 5)},
    "Down River": {"pH": (6, 8.5), "Formaldehyde": (0, 0.25)},
}


@app.on_event("startup")
async def startup():
    await seed_indexes()
    await seed_users()
    await seed_reference_data()
    await seed_specifications()
    await batches.seed_batch_module()
    await seed_traceability_master_data()



async def seed_indexes():
    await db.users.create_index("email", unique=True)
    await db.samples.create_index("record_id")
    await db.audit_trail.create_index("timestamp")
    await db.auth_sessions.create_index("user_id")


async def seed_users():
    """Startup NEVER creates or resets credentials.

    Production accounts are provisioned through /api/auth/first-run (initial administrator only)
    and then through authorised user administration. Test accounts are created out of band by
    /app/scripts/seed_test_accounts.py, which is intended for test environments only.
    """
    admins = await db.users.count_documents({"role": "admin"})
    if admins == 0:
        logger.warning("No administrator exists: first-run provisioning is available at "
                       "POST /api/auth/first-run")


async def seed_reference_data():
    if await db.parameters.count_documents({}) == 0:
        for p in DEFAULT_PARAMS:
            await db.parameters.insert_one({"id": new_id(), **p, "created_at": now_iso()})
    existing_points = {
        item["name"]
        for item in await db.sample_points.find({}, {"_id": 0, "name": 1}).to_list(300)
    }
    for name, desc in DEFAULT_POINTS:
        if name not in existing_points:
            await db.sample_points.insert_one({"id": new_id(), "name": name, "description": desc,
                                               "active": True, "created_at": now_iso()})


async def seed_specifications():
    if await db.specifications.count_documents({}) > 0:
        return
    params = {p["name"]: p for p in await db.parameters.find({}, {"_id": 0}).to_list(300)}
    points = {p["name"]: p for p in await db.sample_points.find({}, {"_id": 0}).to_list(300)}
    for point_name, limits in DEFAULT_LIMITS.items():
        sp = points.get(point_name)
        if not sp:
            continue
        await db.specifications.insert_one({
            "id": new_id(), "sample_point_id": sp["id"], "parameter_id": params["Appearance"]["id"],
            "lower_limit": None, "upper_limit": None, "expected_text": "Clear Colourless",
            "active": True, "version": 1, "created_at": now_iso()})
        for pname, (lo, hi) in limits.items():
            await db.specifications.insert_one({
                "id": new_id(), "sample_point_id": sp["id"], "parameter_id": params[pname]["id"],
                "lower_limit": lo, "upper_limit": hi, "expected_text": None,
                "active": True, "version": 1, "created_at": now_iso()})


@app.on_event("shutdown")
async def shutdown():
    client.close()


import batches  # noqa: E402

app.include_router(api)
app.include_router(batches.router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000"), "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
logging.basicConfig(level=logging.INFO)
