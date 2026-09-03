"""Batch release workflow: products/specs, instruments, customers, batches, CoA, deliveries."""
import os
import io
import csv
import uuid
from datetime import datetime, timezone, date, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from pydantic import BaseModel

from auth import get_current_user, require_roles
from database import db

router = APIRouter(prefix="/api")

STATUS = ("DRAFT", "SUBMITTED", "RETURNED", "APPROVED", "RELEASED", "ON_HOLD", "CANCELLED")
DISPOSITIONS = ("RETURN_TO_QC", "REJECT", "RELEASE_AFTER_INVESTIGATION")
# Confidential investigation detail is withheld from customer certificates unless explicitly configured.
COA_INCLUDE_INVESTIGATION_DETAILS = os.environ.get("COA_INCLUDE_INVESTIGATION_DETAILS", "false").lower() == "true"


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def audit(user: dict, action: str, entity: str, entity_id: str,
                before: Any = None, after: Any = None, reason: str = ""):
    await db.audit_trail.insert_one({
        "id": new_id(), "timestamp": now_iso(), "user_id": user.get("id", ""),
        "user_email": user.get("email", "system"), "user_role": user.get("role", "system"),
        "action": action, "entity": entity, "entity_id": entity_id,
        "before": before, "after": after, "reason": reason,
    })


def CU():
    return Depends(get_current_user)


def RR(*roles):
   return Depends(require_roles(*roles))


# ---------------- Models ----------------
class LimitIn(BaseModel):
    parameter_id: str
    lower_limit: Optional[float] = None
    upper_limit: Optional[float] = None
    expected_text: Optional[str] = None


class ProductIn(BaseModel):
    name: str
    code: str = ""
    batch_type: str = "standard"
    shelf_life_required: bool = True
    shelf_life_days: int = 365
    sales_mode: str = "multi"  # multi | exclusive
    exclusive_customer_id: Optional[str] = None
    limits: List[LimitIn] = []
    reason: str = "Initial specification"


class AmendIn(BaseModel):
    shelf_life_required: Optional[bool] = None
    shelf_life_days: Optional[int] = None
    limits: Optional[List[LimitIn]] = None
    sales_mode: Optional[str] = None
    exclusive_customer_id: Optional[str] = None
    reason: str


class InstrumentIn(BaseModel):
    name: str
    instrument_code: str = ""
    calibration_due: str
    service_due: str
    active: bool = True


class ContactIn(BaseModel):
    name: str
    email: str
    active: bool = True


class CustomerIn(BaseModel):
    name: str
    account_code: str = ""
    active: bool = True


class BatchIn(BaseModel):
    product_id: str
    batch_number: str
    production_date: str
    customer_id: Optional[str] = None


class BatchResultIn(BaseModel):
    parameter_id: str
    value_numeric: Optional[float] = None
    value_text: Optional[str] = None
    reason: str = ""


class BatchResultsIn(BaseModel):
    results: List[BatchResultIn]
    instrument_id: Optional[str] = None


class CommentIn(BaseModel):
    comment: str = ""


class InvestigationIn(BaseModel):
    issue: str
    root_cause: str = ""
    impact: str = ""
    corrective_action: str = ""
    decision: str = ""  # RETURN_TO_QC | RELEASE | REJECT
    required_actions: List[str] = []


class DispositionIn(BaseModel):
    """RELEASE_AFTER_INVESTIGATION disposition. Never alters the original result or its FAIL status."""
    issue: str
    investigation_conclusion: str
    impact_assessment: str
    release_justification: str
    corrective_action: str = ""
    corrective_action_not_applicable: bool = False
    evidence_references: List[str] = []
    oos_reviewed_accepted_without_change: bool = False
    dispositioned_parameter_ids: List[str] = []
    customer_ids: List[str] = []


class ProductionDateIn(BaseModel):
    production_date: str
    reason: str


class CoaAuthIn(BaseModel):
    reason: str
    customer_id: Optional[str] = None


class RecipientIn(BaseModel):
    contact_id: Optional[str] = None
    name: str
    email: str


class SendIn(BaseModel):
    recipients: List[RecipientIn]


# ---------------- Spec version helpers ----------------
async def create_version(product_id: str, data: dict, user: dict, reason: str, before: Optional[dict]) -> dict:
    prev = await db.spec_versions.find({"product_id": product_id}, {"_id": 0}).sort("version", -1).to_list(1)
    version = (prev[0]["version"] + 1) if prev else 1
    doc = {"id": new_id(), "product_id": product_id, "version": version,
           "shelf_life_required": data["shelf_life_required"], "shelf_life_days": data["shelf_life_days"],
           "limits": data.get("limits", []), "sales_mode": data.get("sales_mode", "multi"),
           "exclusive_customer_id": data.get("exclusive_customer_id"),
           "effective_from": date.today().isoformat(), "created_at": now_iso(),
           "created_by": user["email"], "reason": reason,
           "original_values": before, "new_values": {k: data[k] for k in ("shelf_life_required", "shelf_life_days")}}
    await db.spec_versions.insert_one(dict(doc))
    return doc


async def version_for_date(product_id: str, production_date: str) -> Optional[dict]:
    versions = await db.spec_versions.find(
        {"product_id": product_id, "effective_from": {"$lte": production_date[:10]}}, {"_id": 0}
    ).sort("version", -1).to_list(50)
    if versions:
        return versions[0]
    all_v = await db.spec_versions.find({"product_id": product_id}, {"_id": 0}).sort("version", 1).to_list(1)
    return all_v[0] if all_v else None


def evaluate_value(limit: Optional[dict], value_numeric, value_text) -> str:
    if not limit:
        return "NO_SPEC"
    if value_numeric is None:
        expected = (limit.get("expected_text") or "").strip().lower()
        if not expected:
            return "NO_SPEC"
        return "PASS" if (value_text or "").strip().lower() == expected else "FAIL"
    lo, hi = limit.get("lower_limit"), limit.get("upper_limit")
    if lo is not None and value_numeric < lo:
        return "FAIL"
    if hi is not None and value_numeric > hi:
        return "FAIL"
    return "PASS"


# ---------------- Products ----------------
@router.get("/products")
async def list_products(user: dict = CU()):
    products = await db.products.find({}, {"_id": 0}).sort("name", 1).to_list(300)
    for p in products:
        latest = await db.spec_versions.find({"product_id": p["id"]}, {"_id": 0}).sort("version", -1).to_list(1)
        p["active_version"] = latest[0] if latest else None
    return products


@router.post("/products")
async def create_product(body: ProductIn, user: dict = RR("admin", "qa")):
    doc = {"id": new_id(), "name": body.name, "code": body.code, "batch_type": body.batch_type,
           "created_at": now_iso(), "created_by": user["email"]}
    await db.products.insert_one(dict(doc))
    data = {"shelf_life_required": body.shelf_life_required, "shelf_life_days": body.shelf_life_days,
            "limits": [l.model_dump() for l in body.limits], "sales_mode": body.sales_mode,
            "exclusive_customer_id": body.exclusive_customer_id}
    v = await create_version(doc["id"], data, user, body.reason, None)
    await audit(user, "CREATE", "product", doc["id"], after={**doc, "version": v})
    return {**doc, "active_version": v}


@router.get("/products/{product_id}/versions")
async def product_versions(product_id: str, user: dict = CU()):
    return await db.spec_versions.find({"product_id": product_id}, {"_id": 0}).sort("version", -1).to_list(100)


def merged_spec_data(cur: dict, body: AmendIn) -> dict:
    def pick(new_value, key, default=None):
        return cur.get(key, default) if new_value is None else new_value

    return {
        "shelf_life_required": pick(body.shelf_life_required, "shelf_life_required"),
        "shelf_life_days": pick(body.shelf_life_days, "shelf_life_days"),
        "limits": [l.model_dump() for l in body.limits] if body.limits is not None else cur.get("limits", []),
        "sales_mode": body.sales_mode or cur.get("sales_mode", "multi"),
        "exclusive_customer_id": pick(body.exclusive_customer_id, "exclusive_customer_id"),
    }


@router.post("/products/{product_id}/amend")
async def amend_product(product_id: str, body: AmendIn, user: dict = RR("admin", "qa")):
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if not body.reason.strip():
        raise HTTPException(status_code=400, detail="A reason is required for a specification amendment")
    latest = await db.spec_versions.find({"product_id": product_id}, {"_id": 0}).sort("version", -1).to_list(1)
    if not latest:
        raise HTTPException(status_code=400, detail="Product has no specification version")
    cur = latest[0]
    data = merged_spec_data(cur, body)
    before = {k: cur.get(k) for k in ("shelf_life_required", "shelf_life_days", "limits", "sales_mode")}
    version = await create_version(product_id, data, user, body.reason, before)
    await audit(user, "AMEND_SPECIFICATION", "product", product_id, before=before, after=data, reason=body.reason)
    return version


# ---------------- Instruments ----------------
@router.get("/instruments")
async def list_instruments(user: dict = CU()):
    today = date.today().isoformat()
    items = await db.instruments.find({}, {"_id": 0}).sort("name", 1).to_list(200)
    for i in items:
        i["in_calibration"] = i["calibration_due"] >= today
        i["in_service"] = i["service_due"] >= today
    return items


@router.post("/instruments")
async def create_instrument(body: InstrumentIn, user: dict = RR("admin", "qa")):
    doc = {"id": new_id(), **body.model_dump(), "created_at": now_iso()}
    await db.instruments.insert_one(dict(doc))
    await audit(user, "CREATE", "instrument", doc["id"], after=doc)
    return doc


@router.patch("/instruments/{instrument_id}")
async def update_instrument(instrument_id: str, body: InstrumentIn, user: dict = RR("admin", "qa")):
    before = await db.instruments.find_one({"id": instrument_id}, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Instrument not found")
    await db.instruments.update_one({"id": instrument_id}, {"$set": body.model_dump()})
    after = await db.instruments.find_one({"id": instrument_id}, {"_id": 0})
    await audit(user, "UPDATE", "instrument", instrument_id, before=before, after=after)
    return after


# ---------------- Customers (Admin only writes) ----------------
@router.get("/customers")
async def list_customers(user: dict = CU()):
    return await db.customers.find({}, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("/customers")
async def create_customer(body: CustomerIn, user: dict = RR("admin")):
    doc = {"id": new_id(), **body.model_dump(), "contacts": [], "created_at": now_iso()}
    await db.customers.insert_one(dict(doc))
    await audit(user, "CREATE", "customer", doc["id"], after=doc)
    return doc


@router.patch("/customers/{customer_id}")
async def update_customer(customer_id: str, body: CustomerIn, user: dict = RR("admin")):
    before = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.customers.update_one({"id": customer_id}, {"$set": body.model_dump()})
    after = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    await audit(user, "UPDATE", "customer", customer_id, before=before, after=after)
    return after


@router.post("/customers/{customer_id}/contacts")
async def add_contact(customer_id: str, body: ContactIn, user: dict = RR("admin")):
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    contact = {"id": new_id(), **body.model_dump(), "created_at": now_iso()}
    await db.customers.update_one({"id": customer_id}, {"$push": {"contacts": contact}})
    await audit(user, "CREATE", "customer_contact", customer_id, after=contact)
    return contact


@router.patch("/customers/{customer_id}/contacts/{contact_id}")
async def update_contact(customer_id: str, contact_id: str, body: ContactIn, user: dict = RR("admin")):
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    contacts = customer.get("contacts", [])
    before = next((c for c in contacts if c["id"] == contact_id), None)
    if not before:
        raise HTTPException(status_code=404, detail="Contact not found")
    updated = [{**c, **body.model_dump()} if c["id"] == contact_id else c for c in contacts]
    await db.customers.update_one({"id": customer_id}, {"$set": {"contacts": updated}})
    await audit(user, "UPDATE", "customer_contact", customer_id, before=before,
                after={**before, **body.model_dump()})
    return {**before, **body.model_dump()}


# ---------------- Batches ----------------
async def batch_or_404(batch_id: str) -> dict:
    b = await db.batches.find_one({"id": batch_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Batch not found")
    return b


async def add_history(batch_id: str, user: dict, action: str, detail: dict, reason: str = ""):
    entry = {"id": new_id(), "timestamp": now_iso(), "user_email": user["email"],
             "user_role": user["role"], "action": action, "detail": detail, "reason": reason}
    await db.batches.update_one({"id": batch_id}, {"$push": {"history": entry}})
    await audit(user, action, "batch", batch_id, after=detail, reason=reason)
    return entry


def compute_expiry(production_date: str, days: int) -> str:
    return (date.fromisoformat(production_date[:10]) + timedelta(days=int(days))).isoformat()


@router.post("/batches")
async def create_batch(body: BatchIn, user: dict = RR("admin", "qc")):
    product = await db.products.find_one({"id": body.product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    spec = await version_for_date(body.product_id, body.production_date)
    if not spec:
        raise HTTPException(status_code=400, detail="Product has no specification version")
    customer_id = None
    customer_name = None
    if spec.get("sales_mode") == "exclusive":
        customer_id = body.customer_id or spec.get("exclusive_customer_id")
        if not customer_id:
            raise HTTPException(status_code=400, detail="A customer must be selected for a customer-exclusive product")
        cust = await db.customers.find_one({"id": customer_id}, {"_id": 0})
        if not cust:
            raise HTTPException(status_code=404, detail="Customer not found")
        customer_name = cust["name"]
    doc = {
        "id": new_id(), "batch_number": body.batch_number, "product_id": product["id"],
        "product_name": product["name"], "batch_type": product.get("batch_type", "standard"),
        "production_date": body.production_date[:10],
        "spec_version": spec["version"], "spec_version_id": spec["id"],
        "shelf_life_required": spec["shelf_life_required"],
        "shelf_life_days": spec["shelf_life_days"],
        "expiry_date": compute_expiry(body.production_date, spec["shelf_life_days"]) if spec["shelf_life_required"] else None,
        "applied_limits": spec.get("limits", []),
        "sales_mode": spec.get("sales_mode", "multi"),
        "customer_id": customer_id, "customer_name": customer_name,
        "status": "DRAFT", "instrument_id": None, "instrument_snapshot": None,
        "results": [], "hold_reasons": [], "investigation": None, "required_actions": [],
        "submitted_by": None, "released_by": None, "coas": [], "deliveries": [],
        "cancelled": None, "replacement_batch_id": None, "investigation_required": False,
        "release_basis": "STANDARD_RELEASE", "dispositions": [], "active_disposition": None,
        "overall_result": "PENDING",
        "created_at": now_iso(), "created_by": user["email"], "history": [],
    }
    await db.batches.insert_one(dict(doc))
    await add_history(doc["id"], user, "BATCH_CREATED", {
        "batch_number": doc["batch_number"], "production_date": doc["production_date"],
        "spec_version": spec["version"], "shelf_life_days": spec["shelf_life_days"],
        "expiry_date": doc["expiry_date"], "customer_id": customer_id})
    return await batch_or_404(doc["id"])


@router.get("/batches")
async def list_batches(status: Optional[str] = None, user: dict = CU()):
    q = {"status": status} if status else {}
    return await db.batches.find(q, {"_id": 0, "history": 0}).sort("created_at", -1).to_list(500)


@router.get("/batches/{batch_id}")
async def get_batch(batch_id: str, user: dict = CU()):
    return await batch_or_404(batch_id)


def result_value(item) -> Any:
    return item.value_numeric if item.value_numeric is not None else item.value_text


def previous_value(prev: dict) -> Any:
    return prev.get("value_numeric") if prev.get("value_numeric") is not None else prev.get("value_text")


def build_result(item, parameter: dict, limit: Optional[dict], prev: Optional[dict], user: dict) -> dict:
    rec = {
        "parameter_id": parameter["id"], "parameter_name": parameter["name"],
        "units": parameter.get("units", ""),
        "value_numeric": item.value_numeric, "value_text": item.value_text,
        "status": evaluate_value(limit, item.value_numeric, item.value_text),
        "entered_by": user["email"], "entered_at": now_iso(),
        "revision": (prev.get("revision", 1) + 1) if prev else 1,
        "original_value": previous_value(prev) if prev else None,
        "amendments": list(prev.get("amendments", [])) if prev else [],
    }
    if prev:
        rec["amendments"].append({
            "original_value": previous_value(prev), "new_value": result_value(item),
            "reason": item.reason, "user_email": user["email"], "timestamp": now_iso()})
    return rec


async def confirm_instrument(batch_id: str, instrument_id: str, user: dict) -> None:
    inst = await db.instruments.find_one({"id": instrument_id}, {"_id": 0})
    if not inst:
        raise HTTPException(status_code=404, detail="Instrument not found")
    snapshot = {"id": inst["id"], "name": inst["name"], "calibration_due": inst["calibration_due"],
                "service_due": inst["service_due"], "confirmed_at": now_iso(),
                "confirmed_by": user["email"]}
    await db.batches.update_one({"id": batch_id}, {"$set": {
        "instrument_id": inst["id"], "instrument_snapshot": snapshot}})
    await add_history(batch_id, user, "INSTRUMENT_CONFIRMED", snapshot)


@router.post("/batches/{batch_id}/results")
async def enter_results(batch_id: str, body: BatchResultsIn, user: dict = RR("admin", "qc")):
    batch = await batch_or_404(batch_id)
    if batch["status"] in ("RELEASED", "CANCELLED", "SUBMITTED", "APPROVED"):
        raise HTTPException(status_code=400,
                            detail=f"Results cannot be edited while the batch is {batch['status']}")
    limits = {l["parameter_id"]: l for l in batch.get("applied_limits", [])}
    params = {p["id"]: p for p in await db.parameters.find({}, {"_id": 0}).to_list(300)}
    existing = {r["parameter_id"]: r for r in batch.get("results", [])}

    if body.instrument_id:
        await confirm_instrument(batch_id, body.instrument_id, user)

    for item in body.results:
        parameter = params.get(item.parameter_id)
        if not parameter:
            raise HTTPException(status_code=400, detail="Unknown parameter in submitted results")
        prev = existing.get(item.parameter_id)
        if prev and not item.reason.strip():
            raise HTTPException(status_code=400,
                                detail=f"A reason is required to amend the {parameter['name']} result")
        rec = build_result(item, parameter, limits.get(item.parameter_id), prev, user)
        if prev:
            await add_history(batch_id, user, "RESULT_AMENDED", {
                "parameter": parameter["name"],
                "original_value": rec["amendments"][-1]["original_value"],
                "new_value": rec["amendments"][-1]["new_value"]}, reason=item.reason)
        else:
            await add_history(batch_id, user, "RESULT_ENTERED", {
                "parameter": parameter["name"], "value": result_value(item), "status": rec["status"]})
        existing[item.parameter_id] = rec

    results = list(existing.values())
    statuses = [r["status"] for r in results]
    overall = "FAIL" if "FAIL" in statuses else ("PASS" if results else "PENDING")
    await db.batches.update_one({"id": batch_id}, {"$set": {
        "results": results, "overall_result": overall, "updated_at": now_iso()}})
    return await batch_or_404(batch_id)



def _result_problems(batch: dict, parameters: dict) -> List[str]:
    problems: List[str] = []
    results = {r["parameter_id"]: r for r in batch.get("results", [])}
    for limit in batch.get("applied_limits", []):
        result = results.get(limit["parameter_id"])
        if not result:
            name = parameters.get(limit["parameter_id"], {}).get("name", "a specified parameter")
            problems.append(f"Missing result for {name}")
        elif result["status"] == "FAIL":
            problems.append(f"{result['parameter_name']} result is outside the approved specification")
    return problems


def _instrument_problems(batch: dict, today: str) -> List[str]:
    instrument = batch.get("instrument_snapshot")
    if not instrument:
        return ["No instrument has been confirmed for this batch"]
    problems = []
    if instrument["calibration_due"] < today:
        problems.append(f"Instrument {instrument['name']} is overdue for calibration")
    if instrument["service_due"] < today:
        problems.append(f"Instrument {instrument['name']} is overdue for service")
    return problems


def _shelf_life_problems(batch: dict) -> List[str]:
    if not batch.get("shelf_life_required"):
        return []
    if batch.get("production_date") and batch.get("expiry_date"):
        return []
    return ["Shelf-life and expiry information is required before release"]


async def release_checks(batch: dict) -> List[str]:
    parameters = {p["id"]: p for p in await db.parameters.find({}, {"_id": 0}).to_list(300)}
    return (_result_problems(batch, parameters)
            + _instrument_problems(batch, date.today().isoformat())
            + _shelf_life_problems(batch))


def coa_certificate_number(batch: dict, cust: Optional[dict], revision: int) -> str:
    if cust:
        suffix = (cust.get("account_code") or cust["name"][:3]).upper()
    else:
        suffix = "ALL"
    return f"COA-{batch['batch_number']}-{suffix}-R{revision}"


def coa_snapshot(batch: dict) -> dict:
    shelf_life = batch.get("shelf_life_required")
    disposition = batch.get("active_disposition")
    snapshot = {
        "batch_number": batch["batch_number"], "product_name": batch["product_name"],
        "production_date": batch["production_date"],
        "expiry_date": batch.get("expiry_date") if shelf_life else None,
        "shelf_life_days": batch.get("shelf_life_days") if shelf_life else None,
        "shelf_life_required": shelf_life,
        "spec_version": batch["spec_version"],
        "results": batch.get("results", []),
        "instrument": batch.get("instrument_snapshot"),
        "release_basis": batch.get("release_basis", "STANDARD_RELEASE"),
        "contains_dispositioned_oos": bool(disposition),
        "disposition_reference": disposition["reference"] if disposition else None,
    }
    if disposition and COA_INCLUDE_INVESTIGATION_DETAILS:
        snapshot["disposition_details"] = disposition
    return snapshot


def supersede_existing(coas: list, coa: dict, supersedes: Optional[dict]) -> list:
    if not supersedes:
        return coas
    return [{**c, "status": "SUPERSEDED", "superseded_by_coa_id": coa["id"],
             "delivery_status": "SUPERSEDED"} if c["id"] == supersedes["id"] else c for c in coas]


async def create_coa(batch: dict, user: dict, customer_id: Optional[str], reason: str,
                     supersedes: Optional[dict] = None) -> dict:
    cust = await db.customers.find_one({"id": customer_id}, {"_id": 0}) if customer_id else None
    revision = len([c for c in batch.get("coas", []) if c.get("customer_id") == customer_id]) + 1
    coa = {
        "id": new_id(), "revision": revision,
        "certificate_number": coa_certificate_number(batch, cust, revision),
        "customer_id": customer_id, "customer_name": cust["name"] if cust else None,
        "issue_date": now_iso(), "status": "ACTIVE", "delivery_status": "READY_FOR_QA_TO_SEND",
        "authorised_by": user["email"], "supersedes_coa_id": supersedes["id"] if supersedes else None,
        "reason": reason,
        "snapshot": coa_snapshot(batch),
    }
    coas = supersede_existing(batch.get("coas", []), coa, supersedes) + [coa]
    await db.batches.update_one({"id": batch["id"]}, {"$set": {"coas": coas}})
    await add_history(batch["id"], user, "COA_GENERATED", {
        "certificate_number": coa["certificate_number"], "revision": coa["revision"],
        "customer": coa["customer_name"], "supersedes": supersedes["certificate_number"] if supersedes else None},
        reason=reason)
    return coa


@router.post("/batches/{batch_id}/submit")
async def submit_batch(batch_id: str, body: CommentIn, user: dict = RR("admin", "qc")):
    batch = await batch_or_404(batch_id)
    if batch["status"] not in ("DRAFT", "RETURNED"):
        raise HTTPException(status_code=400, detail=f"A {batch['status']} batch cannot be submitted")
    if not batch.get("results"):
        raise HTTPException(status_code=400, detail="Enter results before submitting the batch")
    await db.batches.update_one({"id": batch_id}, {"$set": {
        "status": "SUBMITTED", "submitted_by": user["email"], "submitted_at": now_iso()}})
    await add_history(batch_id, user, "BATCH_SUBMITTED", {"from": batch["status"]}, reason=body.comment)
    return await batch_or_404(batch_id)


class ReleaseIn(BaseModel):
    customer_ids: List[str] = []


@router.post("/batches/{batch_id}/release")
async def qc_release(batch_id: str, body: ReleaseIn, user: dict = RR("admin", "qc")):
    batch = await batch_or_404(batch_id)
    if batch["status"] in ("RELEASED", "CANCELLED"):
        raise HTTPException(status_code=400, detail=f"Batch is already {batch['status']}")
    if batch.get("investigation_required") or oos_parameter_ids(batch):
        problems = await release_checks(batch)
        await db.batches.update_one({"id": batch_id}, {"$set": {
            "status": "ON_HOLD", "hold_reasons": problems, "held_at": now_iso(),
            "investigation_required": True}})
        await add_history(batch_id, user, "BATCH_HELD_FOR_QA", {"reasons": problems})
        raise HTTPException(
            status_code=400,
            detail="Release blocked: out of specification results require a documented QA investigation. "
                   "Only QA can release this batch, after a completed disposition. " + "; ".join(problems))
    problems = await release_checks(batch)
    if problems:
        await db.batches.update_one({"id": batch_id}, {"$set": {
            "status": "ON_HOLD", "hold_reasons": problems, "held_at": now_iso(),
            "investigation_required": True}})
        await add_history(batch_id, user, "BATCH_HELD_FOR_QA", {"reasons": problems})
        raise HTTPException(status_code=400, detail="Release blocked: " + "; ".join(problems) +
                            ". The batch is on hold for QA investigation.")
    targets = [batch["customer_id"]] if batch.get("customer_id") else (body.customer_ids or [None])
    batch = await batch_or_404(batch_id)
    for cid in targets:
        await create_coa(await batch_or_404(batch_id), user, cid, "Initial release")
    await db.batches.update_one({"id": batch_id}, {"$set": {
        "status": "RELEASED", "released_by": user["email"], "released_at": now_iso(),
        "hold_reasons": []}})
    await add_history(batch_id, user, "BATCH_RELEASED", {"customers": targets})
    return await batch_or_404(batch_id)


def oos_parameter_ids(batch: dict) -> List[str]:
    """Parameter ids whose recorded result is FAIL against the applied specification version."""
    return [r["parameter_id"] for r in batch.get("results", []) if r.get("status") == "FAIL"]


def oos_problem_for(result: dict) -> str:
    return f"{result['parameter_name']} result is outside the approved specification"


def partition_release_problems(problems: List[str], accepted_problems: List[str]) -> tuple:
    """Split release problems into QA-accepted specification failures and unresolved blockers."""
    remaining = list(problems)
    accepted = []
    for a in accepted_problems:
        if a in remaining:
            remaining.remove(a)
            accepted.append(a)
    return accepted, remaining


def _assert_disposition_documented(body: DispositionIn) -> None:
    required = {
        "investigation/issue description": body.issue,
        "investigation conclusion": body.investigation_conclusion,
        "scientific/technical impact assessment": body.impact_assessment,
        "justification for release": body.release_justification,
    }
    missing = [label for label, value in required.items() if not value.strip()]
    if missing:
        raise HTTPException(status_code=400,
                            detail="A completed investigation is required before release. Missing: " + ", ".join(missing))
    if not body.corrective_action.strip() and not body.corrective_action_not_applicable:
        raise HTTPException(status_code=400,
                            detail="Record the corrective/preventive action, or confirm it is not applicable")
    if not [e for e in body.evidence_references if e.strip()]:
        raise HTTPException(status_code=400,
                            detail="At least one reference to supporting evidence or specialist assessment is required")
    if not body.oos_reviewed_accepted_without_change:
        raise HTTPException(
            status_code=400,
            detail="QA must explicitly confirm the OOS result has been reviewed and is accepted for disposition "
                   "without changing its original FAIL classification")


def build_disposition(batch: dict, body: DispositionIn, accepted: List[dict], user: dict) -> dict:
    return {
        "id": new_id(),
        "reference": f"DISP-{batch['batch_number']}-{len(batch.get('dispositions', [])) + 1}",
        "outcome": "RELEASE_AFTER_INVESTIGATION",
        "issue": body.issue,
        "investigation_conclusion": body.investigation_conclusion,
        "impact_assessment": body.impact_assessment,
        "release_justification": body.release_justification,
        "corrective_action": body.corrective_action,
        "corrective_action_not_applicable": body.corrective_action_not_applicable,
        "evidence_references": [e for e in body.evidence_references if e.strip()],
        "oos_reviewed_accepted_without_change": True,
        "qa_user": user["email"],
        "qa_user_id": user["id"],
        "recorded_at": now_iso(),
        "spec_version": batch["spec_version"],
        "spec_version_id": batch.get("spec_version_id"),
        "accepted_oos_results": accepted,
    }


def accepted_oos_snapshot(batch: dict, parameter_ids: List[str]) -> List[dict]:
    limits = {l["parameter_id"]: l for l in batch.get("applied_limits", [])}
    snapshot = []
    for r in batch.get("results", []):
        if r["parameter_id"] not in parameter_ids:
            continue
        limit = limits.get(r["parameter_id"], {})
        snapshot.append({
            "parameter_id": r["parameter_id"], "parameter_name": r["parameter_name"],
            "original_value": r.get("value_numeric") if r.get("value_numeric") is not None else r.get("value_text"),
            "units": r.get("units", ""),
            "original_classification": r["status"],
            "original_specification": {"lower_limit": limit.get("lower_limit"),
                                       "upper_limit": limit.get("upper_limit"),
                                       "expected_text": limit.get("expected_text")},
            "specification_version": batch["spec_version"],
            "entered_by": r.get("entered_by"), "entered_at": r.get("entered_at"),
        })
    return snapshot


@router.post("/batches/{batch_id}/disposition/release-after-investigation")
async def release_after_investigation(batch_id: str, body: DispositionIn, user: dict = RR("qa")):
    """QA disposition permitting release of an OOS batch. Original results and FAIL status are never altered."""
    batch = await batch_or_404(batch_id)
    if batch["status"] == "CANCELLED":
        raise HTTPException(status_code=400, detail="Cancelled batches cannot be actioned")
    if batch["status"] == "RELEASED":
        raise HTTPException(status_code=400, detail="Batch is already released")
    if batch["status"] != "ON_HOLD" and not batch.get("investigation_required"):
        raise HTTPException(status_code=400,
                            detail="Only a batch on hold for investigation can be dispositioned for release")
    if user["email"] in (batch.get("submitted_by"), batch.get("created_by")):
        raise HTTPException(status_code=403, detail="You cannot approve or release your own work")

    _assert_disposition_documented(body)

    failing = oos_parameter_ids(batch)
    requested = [p for p in body.dispositioned_parameter_ids if p in failing] if body.dispositioned_parameter_ids else failing
    if not requested:
        raise HTTPException(status_code=400,
                            detail="No out of specification result was identified for disposition")

    results_by_id = {r["parameter_id"]: r for r in batch.get("results", [])}
    accepted_problems = [oos_problem_for(results_by_id[p]) for p in requested]
    problems = await release_checks(batch)
    accepted, remaining = partition_release_problems(problems, accepted_problems)
    if remaining:
        raise HTTPException(status_code=400,
                            detail="Release blocked by unresolved controls that a QA disposition cannot waive: "
                                   + "; ".join(remaining))

    disposition = build_disposition(batch, body, accepted_oos_snapshot(batch, requested), user)
    await db.batches.update_one({"id": batch_id}, {"$set": {
        "status": "RELEASED",
        "release_basis": "RELEASE_AFTER_INVESTIGATION",
        "released_by": user["email"], "released_at": now_iso(),
        "investigation_required": False,
        "active_disposition": disposition,
        "retained_hold_reasons": accepted,
        "hold_reasons": [],
    }, "$push": {"dispositions": disposition}})
    await add_history(batch_id, user, "QA_RELEASE_AFTER_INVESTIGATION", {
        "reference": disposition["reference"],
        "accepted_oos_results": disposition["accepted_oos_results"],
        "investigation_conclusion": body.investigation_conclusion,
        "impact_assessment": body.impact_assessment,
        "release_justification": body.release_justification,
        "evidence_references": disposition["evidence_references"],
        "corrective_action": body.corrective_action or "Not applicable",
        "original_classification_unchanged": True,
        "qa_user": user["email"], "recorded_at": disposition["recorded_at"],
    }, reason=body.release_justification)

    for item in disposition["accepted_oos_results"]:
        await db.oos_log.update_many(
            {"batch_id": batch_id, "parameter_id": item["parameter_id"]},
            {"$set": {"status": "Closed - Released after investigation",
                      "disposition_reference": disposition["reference"]}})
        await db.oos_log.insert_one({
            "id": new_id(), "batch_id": batch_id, "sample_id": batch_id,
            "record_id": batch["batch_number"], "parameter_id": item["parameter_id"],
            "sample_point_name": f"{batch['product_name']} · {item['parameter_name']}",
            "raised_at": now_iso(), "raised_by": user["email"],
            "reason": f"{item['parameter_name']} = {item['original_value']} {item['units']} "
                      f"remains {item['original_classification']} against specification v{item['specification_version']}; "
                      f"released under {disposition['reference']}",
            "status": "Closed - Released after investigation",
            "disposition_reference": disposition["reference"]})

    refreshed = await batch_or_404(batch_id)
    targets = [batch["customer_id"]] if batch.get("customer_id") else (body.customer_ids or [None])
    for cid in targets:
        await create_coa(await batch_or_404(batch_id), user, cid,
                         f"Released after investigation ({disposition['reference']})")
    await add_history(batch_id, user, "BATCH_RELEASED", {
        "customers": targets, "release_basis": "RELEASE_AFTER_INVESTIGATION",
        "disposition_reference": disposition["reference"],
        "overall_result_retained": refreshed.get("overall_result")})
    return await batch_or_404(batch_id)


def qa_updates_for(decision: str, investigation: dict, user: dict) -> tuple:
    if decision == "return":
        return {"status": "RETURNED", "investigation": investigation,
                "required_actions": investigation["required_actions"],
                "investigation_required": True}, "QA_RETURNED_TO_QC"
    if decision == "approve":
        return {"status": "APPROVED", "investigation": investigation,
                "qa_reviewer": user["email"], "qa_reviewed_at": now_iso()}, "QA_APPROVED"
    if decision == "reject":
        return {"status": "ON_HOLD", "investigation": investigation,
                "rejected_by": user["email"], "rejected_at": now_iso()}, "QA_REJECTED"
    return {"status": "RELEASED", "investigation": investigation,
            "released_by": user["email"], "released_at": now_iso(), "hold_reasons": [],
            "investigation_required": False}, "QA_RELEASED"


def _assert_decision_allowed(decision: str, body: InvestigationIn, batch: dict, user: dict) -> None:
    if batch["status"] == "CANCELLED":
        raise HTTPException(status_code=400, detail="Cancelled batches cannot be actioned")
    if decision not in ("approve", "return", "release", "reject"):
        raise HTTPException(status_code=400, detail="Invalid QA decision")
    if decision in ("approve", "release") and user["email"] in (
            batch.get("submitted_by"), batch.get("created_by")):
        raise HTTPException(status_code=403, detail="You cannot approve or release your own work")
    if not body.issue.strip():
        raise HTTPException(status_code=400, detail="A comment or issue description is required")
    if batch["status"] == "RELEASED" and decision in ("release", "approve"):
        raise HTTPException(status_code=400, detail="Batch is already released")
    if decision == "release" and oos_parameter_ids(batch):
        raise HTTPException(
            status_code=400,
            detail="This batch has out of specification results. Use the documented "
                   "RELEASE_AFTER_INVESTIGATION disposition to release it.")


def _assert_investigation_documented(decision: str, body: InvestigationIn, batch: dict) -> None:
    needs_docs = bool(batch.get("investigation_required")) or batch["status"] == "ON_HOLD"
    if not needs_docs or decision not in ("release", "reject"):
        return
    if body.root_cause.strip() and body.impact.strip() and body.corrective_action.strip():
        return
    raise HTTPException(
        status_code=400,
        detail="Root cause, impact and corrective action must be documented before closing an investigation")


async def validate_qa_decision(decision: str, body: InvestigationIn, batch: dict, user: dict) -> None:
    _assert_decision_allowed(decision, body, batch, user)
    _assert_investigation_documented(decision, body, batch)
    if decision == "release":
        problems = await release_checks(batch)
        if problems:
            raise HTTPException(status_code=400, detail="Release blocked: " + "; ".join(problems))


@router.post("/batches/{batch_id}/qa-decision/{decision}")
async def qa_decision(batch_id: str, decision: str, body: InvestigationIn, user: dict = RR("qa")):
    batch = await batch_or_404(batch_id)
    await validate_qa_decision(decision, body, batch, user)

    investigation = {
        "issue": body.issue, "root_cause": body.root_cause, "impact": body.impact,
        "corrective_action": body.corrective_action, "decision": decision.upper(),
        "required_actions": body.required_actions, "qa_user": user["email"], "recorded_at": now_iso(),
    }
    updates, action = qa_updates_for(decision, investigation, user)
    await db.batches.update_one({"id": batch_id}, {"$set": updates})
    await add_history(batch_id, user, action, investigation, reason=body.issue)
    if decision == "release":
        targets = [batch["customer_id"]] if batch.get("customer_id") else [None]
        for cid in targets:
            await create_coa(await batch_or_404(batch_id), user, cid,
                             "Released by QA after investigation")
    return await batch_or_404(batch_id)



@router.post("/batches/{batch_id}/production-date")
async def amend_production_date(batch_id: str, body: ProductionDateIn, user: dict = RR("qa")):
    batch = await batch_or_404(batch_id)
    if batch["status"] == "CANCELLED":
        raise HTTPException(status_code=400, detail="Cancelled batches cannot be amended")
    if not body.reason.strip():
        raise HTTPException(status_code=400, detail="A reason is required to amend the production date")
    spec = await version_for_date(batch["product_id"], body.production_date)
    if not spec:
        raise HTTPException(status_code=400, detail="No specification version applies to that production date")
    expiry = compute_expiry(body.production_date, spec["shelf_life_days"]) if spec["shelf_life_required"] else None
    before = {"production_date": batch["production_date"], "expiry_date": batch.get("expiry_date"),
              "spec_version": batch["spec_version"]}
    await db.batches.update_one({"id": batch_id}, {"$set": {
        "production_date": body.production_date[:10], "spec_version": spec["version"],
        "spec_version_id": spec["id"], "shelf_life_required": spec["shelf_life_required"],
        "shelf_life_days": spec["shelf_life_days"], "expiry_date": expiry,
        "applied_limits": spec.get("limits", batch.get("applied_limits", [])),
        "coa_reissue_required": batch["status"] == "RELEASED"}})
    await add_history(batch_id, user, "PRODUCTION_DATE_AMENDED", {
        "original_value": before["production_date"], "new_value": body.production_date[:10],
        "recalculated_expiry": expiry, "spec_version": spec["version"]}, reason=body.reason)
    return await batch_or_404(batch_id)


@router.post("/batches/{batch_id}/coa/{coa_id}/authorise-replacement")
async def authorise_replacement(batch_id: str, coa_id: str, body: CoaAuthIn, user: dict = RR("qa")):
    batch = await batch_or_404(batch_id)
    original = next((c for c in batch.get("coas", []) if c["id"] == coa_id), None)
    if not original:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if original["status"] == "SUPERSEDED":
        raise HTTPException(status_code=400, detail="A superseded certificate cannot be replaced")
    if not body.reason.strip():
        raise HTTPException(status_code=400, detail="A reason for reissue is required")
    coa = await create_coa(batch, user, original.get("customer_id"), body.reason, supersedes=original)
    await db.batches.update_one({"id": batch_id}, {"$set": {"coa_reissue_required": False}})
    return coa


def _assert_coa_sendable(batch: dict, coa: Optional[dict], recipients: list) -> None:
    if not coa:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if coa["status"] != "ACTIVE":
        raise HTTPException(status_code=400, detail="Superseded certificates cannot be sent to a customer")
    if batch["status"] == "CANCELLED":
        raise HTTPException(status_code=400, detail="Cancelled batches cannot be sent to a customer")
    if not recipients:
        raise HTTPException(status_code=400, detail="At least one recipient is required")


def _delivery_record(coa: dict, recipient: RecipientIn, user: dict) -> dict:
    if not recipient.name.strip() or not recipient.email.strip():
        raise HTTPException(status_code=400, detail="Recipient name and email address are required")
    return {"id": new_id(), "coa_id": coa["id"], "coa_revision": coa["revision"],
            "certificate_number": coa["certificate_number"],
            "customer_id": coa.get("customer_id"), "customer_name": coa.get("customer_name"),
            "contact_id": recipient.contact_id, "recipient_name": recipient.name,
            "recipient_email": recipient.email, "sent_by": user["email"], "sent_at": now_iso()}


@router.post("/batches/{batch_id}/coa/{coa_id}/send")
async def send_coa(batch_id: str, coa_id: str, body: SendIn, user: dict = RR("qa")):
    batch = await batch_or_404(batch_id)
    coa = next((c for c in batch.get("coas", []) if c["id"] == coa_id), None)
    _assert_coa_sendable(batch, coa, body.recipients)

    records = [_delivery_record(coa, r, user) for r in body.recipients]
    for rec in records:
        await db.batches.update_one({"id": batch_id}, {"$push": {"deliveries": rec}})
        await add_history(batch_id, user, "COA_SENT", rec)

    coas = [{**c, "delivery_status": "SENT", "last_sent_at": now_iso()} if c["id"] == coa_id else c
            for c in batch.get("coas", [])]
    await db.batches.update_one({"id": batch_id}, {"$set": {"coas": coas}})
    return records


class CancelIn(BaseModel):
    reason: str
    replacement_batch_id: Optional[str] = None


@router.post("/batches/{batch_id}/cancel")
async def cancel_batch(batch_id: str, body: CancelIn, user: dict = RR("qa")):
    batch = await batch_or_404(batch_id)
    if batch["status"] == "CANCELLED":
        raise HTTPException(status_code=400, detail="Batch is already cancelled")
    if batch.get("coas"):
        raise HTTPException(status_code=400,
                            detail="This batch has a released C of A. Post-release cancellation is handled outside the LIMS.")
    if not body.reason.strip():
        raise HTTPException(status_code=400, detail="A cancellation reason is required")
    cancelled = {"reason": body.reason, "cancelled_by": user["email"], "cancelled_at": now_iso(),
                 "status_at_cancellation": batch["status"],
                 "replacement_batch_id": body.replacement_batch_id}
    await db.batches.update_one({"id": batch_id}, {"$set": {
        "status": "CANCELLED", "cancelled": cancelled,
        "replacement_batch_id": body.replacement_batch_id}})
    await add_history(batch_id, user, "BATCH_CANCELLED", cancelled, reason=body.reason)
    return await batch_or_404(batch_id)


# ---------------- PDF / queues / alerts / reports ----------------
def _coa_summary_rows(coa: dict, snap: dict) -> List[List[str]]:
    rows = [
        ["Certificate number", coa["certificate_number"], "Revision", str(coa["revision"])],
        ["Issue date", coa["issue_date"][:19].replace("T", " "), "Status", coa["status"]],
        ["Batch number", snap.get("batch_number", ""), "Product", snap.get("product_name", "")],
        ["Customer", coa.get("customer_name") or "All customers", "Specification", f"v{snap.get('spec_version')}"],
        ["Production date", snap.get("production_date", ""), "Instrument",
         (snap.get("instrument") or {}).get("name", "")],
    ]
    if snap.get("shelf_life_required"):
        rows.append(["Shelf life (days)", str(snap.get("shelf_life_days")),
                     "Expiry date", snap.get("expiry_date", "")])
    if snap.get("contains_dispositioned_oos"):
        rows.append(["Release basis", "Released after QA investigation",
                     "Disposition ref", snap.get("disposition_reference", "")])
    if coa.get("supersedes_coa_id"):
        rows.append(["Replaces", "Previous revision", "Reason", coa.get("reason", "")])
    return rows


def _coa_result_rows(snap: dict) -> List[List[str]]:
    rows = [["Parameter", "Result", "Units", "Outcome"]]
    for r in snap.get("results", []):
        value = r.get("value_numeric") if r.get("value_numeric") is not None else r.get("value_text")
        rows.append([r.get("parameter_name", ""), str(value), r.get("units", ""), r.get("status", "")])
    return rows


def coa_pdf_bytes(batch: dict, coa: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=coa["certificate_number"])
    s = getSampleStyleSheet()
    navy = colors.HexColor("#002FA7")
    snap = coa.get("snapshot", {})

    story = [
        Paragraph("<font color='#002FA7'><b>SYNTH LIMS</b></font>", s["Title"]),
        Paragraph("Certificate of Analysis", s["Heading2"]),
        Spacer(1, 6),
    ]
    if coa["status"] != "ACTIVE":
        story.append(Paragraph("<font color='red'><b>SUPERSEDED — NOT VALID FOR ISSUE</b></font>", s["Normal"]))
        story.append(Spacer(1, 6))

    summary = Table(_coa_summary_rows(coa, snap), colWidths=[35 * mm, 55 * mm, 30 * mm, 50 * mm])
    summary.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#475569")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#475569")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))

    results = Table(_coa_result_rows(snap), colWidths=[60 * mm, 40 * mm, 30 * mm, 40 * mm])
    results.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), navy),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))

    story += [summary, Spacer(1, 10), Paragraph("<b>Analytical results</b>", s["Heading4"]),
              results, Spacer(1, 12),
              Paragraph(f"Authorised by <b>{coa.get('authorised_by', '')}</b>", s["Normal"]),
              Paragraph("This certificate was generated by SYNTH LIMS and is retained in the batch audit history.",
                        s["Italic"])]
    doc.build(story)
    return buf.getvalue()



@router.get("/batches/{batch_id}/coa/{coa_id}/pdf")
async def coa_pdf(batch_id: str, coa_id: str, user: dict = CU()):
    batch = await batch_or_404(batch_id)
    coa = next((c for c in batch.get("coas", []) if c["id"] == coa_id), None)
    if not coa:
        raise HTTPException(status_code=404, detail="Certificate not found")
    pdf = coa_pdf_bytes(batch, coa)
    await add_history(batch_id, user, "COA_PDF_DOWNLOADED",
                      {"certificate_number": coa["certificate_number"], "revision": coa["revision"]})
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{coa["certificate_number"]}.pdf"'})


@router.get("/qa/queues")
async def qa_queues(user: dict = CU()):
    fields = {"_id": 0, "history": 0}
    awaiting = await db.batches.find({"status": "SUBMITTED"}, fields).sort("created_at", -1).to_list(300)
    on_hold = await db.batches.find({"status": {"$in": ["ON_HOLD", "RETURNED"]}}, fields).sort("created_at", -1).to_list(300)
    released = await db.batches.find({"status": "RELEASED"}, fields).to_list(500)
    to_send = []
    for b in released:
        for c in b.get("coas", []):
            if c["status"] == "ACTIVE" and c.get("delivery_status") == "READY_FOR_QA_TO_SEND":
                to_send.append({"batch_id": b["id"], "batch_number": b["batch_number"],
                                "product_name": b["product_name"], "certificate_number": c["certificate_number"],
                                "revision": c["revision"], "customer_name": c.get("customer_name"),
                                "issue_date": c["issue_date"]})
    reissue = [{"batch_id": b["id"], "batch_number": b["batch_number"], "product_name": b["product_name"]}
               for b in released if b.get("coa_reissue_required")]
    samples_pending = await db.samples.count_documents({"qa_status": "Pending Review"})
    return {"awaiting_review": awaiting, "on_hold": on_hold, "certificates_to_send": to_send,
            "reissue_required": reissue, "samples_pending_review": samples_pending}


@router.get("/alerts/expiring")
async def expiring_alerts(days: int = 90, user: dict = CU()):
    today = date.today()
    horizon = (today + timedelta(days=days)).isoformat()
    batches = await db.batches.find(
        {"status": "RELEASED", "shelf_life_required": True, "expiry_date": {"$ne": None, "$lte": horizon}},
        {"_id": 0, "history": 0}).to_list(500)
    out = []
    for b in batches:
        remaining = (date.fromisoformat(b["expiry_date"]) - today).days
        out.append({"batch_id": b["id"], "batch_number": b["batch_number"], "product_name": b["product_name"],
                    "customer_name": b.get("customer_name"), "expiry_date": b["expiry_date"],
                    "days_remaining": remaining,
                    "severity": "EXPIRED" if remaining < 0 else ("CRITICAL" if remaining <= 30 else "WARNING")})
    return sorted(out, key=lambda x: x["days_remaining"])


CSV_COLUMNS = ["Batch number", "Product", "Batch type", "Status", "Production date", "Shelf life required",
               "Shelf life (days)", "Expiry date", "Spec version", "Customer", "Instrument",
               "Results summary", "Created by", "Created at", "Submitted by", "Released by", "Released at",
               "Hold reasons", "Active C of A", "C of A revisions", "Deliveries", "Cancelled by", "Cancel reason",
               "Release basis", "Dispositioned OOS reference", "Dispositioned OOS parameters"]


def _results_summary(batch: dict) -> str:
    parts = []
    for r in batch.get("results", []):
        value = r.get("value_numeric") if r.get("value_numeric") is not None else r.get("value_text")
        parts.append(f"{r['parameter_name']}={value} ({r['status']})")
    return "; ".join(parts)


def _customer_label(batch: dict) -> str:
    if batch.get("customer_name"):
        return batch["customer_name"]
    return "Multi-customer" if batch.get("sales_mode") == "multi" else ""


def batch_csv_row(batch: dict) -> list:
    shelf_life = batch.get("shelf_life_required")
    active = next((c["certificate_number"] for c in batch.get("coas", []) if c["status"] == "ACTIVE"), "")
    cancelled = batch.get("cancelled") or {}
    return [
        batch["batch_number"], batch["product_name"], batch.get("batch_type", ""), batch["status"],
        batch["production_date"], "Yes" if shelf_life else "No",
        batch.get("shelf_life_days") if shelf_life else "",
        batch.get("expiry_date") or "", f"v{batch['spec_version']}",
        _customer_label(batch), (batch.get("instrument_snapshot") or {}).get("name", ""),
        _results_summary(batch), batch.get("created_by", ""), batch.get("created_at", ""),
        batch.get("submitted_by") or "", batch.get("released_by") or "", batch.get("released_at") or "",
        "; ".join(batch.get("hold_reasons", [])), active, len(batch.get("coas", [])),
        len(batch.get("deliveries", [])), cancelled.get("cancelled_by", ""), cancelled.get("reason", ""),
        batch.get("release_basis", "STANDARD_RELEASE"),
        (batch.get("active_disposition") or {}).get("reference", ""),
        "; ".join(i["parameter_name"] for i in (batch.get("active_disposition") or {}).get("accepted_oos_results", [])),
    ]


@router.get("/reports/batches.csv")
async def batches_csv(user: dict = CU()):
    batches = await db.batches.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for b in batches:
        writer.writerow(batch_csv_row(b))
    await audit(user, "EXPORT_BATCH_REPORT", "report", "batches.csv", after={"rows": len(batches)})
    return StreamingResponse(io.BytesIO(buf.getvalue().encode()), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="batch-report-{date.today().isoformat()}.csv"'})



@router.get("/batches/{batch_id}/history")
async def batch_history(batch_id: str, user: dict = CU()):
    batch = await batch_or_404(batch_id)
    return sorted(batch.get("history", []), key=lambda x: x["timestamp"], reverse=True)


# ---------------- Seed ----------------
async def seed_batch_module():
    if await db.instruments.count_documents({}) == 0:
        await db.instruments.insert_many([
            {"id": new_id(), "name": "HPLC-01", "instrument_code": "HPLC-01",
             "calibration_due": "2027-01-31", "service_due": "2027-01-31", "active": True,
             "created_at": now_iso()},
            {"id": new_id(), "name": "pH Meter PH-204", "instrument_code": "PH-204",
             "calibration_due": "2027-03-15", "service_due": "2027-03-15", "active": True,
             "created_at": now_iso()},
            {"id": new_id(), "name": "GC-Legacy-99 (overdue)", "instrument_code": "GC-99",
             "calibration_due": "2025-01-01", "service_due": "2025-01-01", "active": True,
             "created_at": now_iso()},
        ])
    if await db.customers.count_documents({}) == 0:
        for name, code, contacts in [
            ("Northwind Chemicals", "NWC", [("Alice Reed", "alice@northwind.test"), ("Dev Patel", "dev@northwind.test")]),
            ("Halden Foods", "HAL", [("Sam Boyd", "sam@halden.test")]),
        ]:
            await db.customers.insert_one({
                "id": new_id(), "name": name, "account_code": code, "active": True,
                "created_at": now_iso(),
                "contacts": [{"id": new_id(), "name": n, "email": e, "active": True,
                              "created_at": now_iso()} for n, e in contacts]})
    if await db.products.count_documents({}) == 0:
        params = {p["name"]: p for p in await db.parameters.find({}, {"_id": 0}).to_list(300)}
        customers = await db.customers.find({}, {"_id": 0}).to_list(10)
        seed_user = {"id": "system", "email": "system", "role": "system"}
        defs = [
            ("Methanol Solution 99%", "MS99", "solvent", True, 730, "multi", None),
            ("Formaldehyde Blend FB2", "FB2", "blend", True, 365, "exclusive",
             customers[0]["id"] if customers else None),
            ("Process Water Grade A", "PWA", "water", False, 0, "multi", None),
        ]
        for name, code, btype, sl_req, sl_days, mode, cust in defs:
            pid = new_id()
            await db.products.insert_one({"id": pid, "name": name, "code": code, "batch_type": btype,
                                          "created_at": now_iso(), "created_by": "system"})
            limits = [
                {"parameter_id": params["pH"]["id"], "lower_limit": 5, "upper_limit": 9, "expected_text": None},
                {"parameter_id": params["COD"]["id"], "lower_limit": 0, "upper_limit": 800, "expected_text": None},
                {"parameter_id": params["Appearance"]["id"], "lower_limit": None, "upper_limit": None,
                 "expected_text": "Clear Colourless"},
            ]
            await create_version(pid, {"shelf_life_required": sl_req, "shelf_life_days": sl_days,
                                       "limits": limits, "sales_mode": mode,
                                       "exclusive_customer_id": cust},
                                 seed_user, "Initial specification", None)