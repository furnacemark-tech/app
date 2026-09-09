from datetime import date
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException

from database import db


INSTRUMENT_AVAILABILITY = {"AVAILABLE", "UNAVAILABLE", "FAILED"}

APPROVED_PARAMETER_INSTRUMENT_MAPPING = {
    "2.C.10": (False, "MANUAL_VISUAL"),
    "2.P.2": (True, "PH_METER"),
    "2.C.3": (False, "MANUAL_NOT_CURRENTLY_CONTROLLED"),
    "2.A.31": (False, "MANUAL_NOT_CURRENTLY_CONTROLLED"),
    "2.M.6": (True, "GC"),
    "2.F.10": (True, "HPLC"),
    "2.S.10": (False, "MANUAL_NOT_CURRENTLY_CONTROLLED"),
}

APPROVED_INSTRUMENT_CATEGORY_BY_CODE = {
    "PH-204": "PH_METER",
    "HPLC-01": "HPLC",
    "GC-99": "GC",
}


def instrument_requirement(parameter: Dict[str, Any]) -> Tuple[bool, str]:
    required = bool(parameter.get("instrument_required", False))
    category = parameter.get("instrument_category", "")
    return required, category


def instrument_state(instrument: Dict[str, Any]) -> Tuple[bool, str]:
    today = date.today().isoformat()
    if not instrument.get("active", False):
        return False, "The registered instrument is inactive."
    if instrument.get("availability_status", "AVAILABLE") == "FAILED":
        return False, "The registered instrument is in a failed state."
    if instrument.get("availability_status", "AVAILABLE") == "UNAVAILABLE":
        return False, "The registered instrument is unavailable."
    if not instrument.get("calibration_due") or instrument["calibration_due"] < today:
        return False, "The registered instrument is overdue for calibration."
    if not instrument.get("service_due") or instrument["service_due"] < today:
        return False, "The registered instrument is overdue for service."
    return True, ""


async def resolve_registered_instrument(reference: str) -> Tuple[Dict[str, Any] | None, str]:
    matches = await db.instruments.find(
        {"$or": [{"id": reference}, {"instrument_code": reference}]},
        {"_id": 0},
    ).to_list(3)
    unique = {item["id"]: item for item in matches}
    if not unique:
        return None, "The supplied instrument identifier is not registered."
    if len(unique) > 1:
        return None, "The supplied instrument identifier is ambiguous in the instrument register."
    return next(iter(unique.values())), ""


async def assess_instrument_traceability(
    parameter: Dict[str, Any] | None,
    reference: str | None,
) -> Dict[str, Any]:
    value = (reference or "").strip()
    if not parameter:
        return {
            "state": "INVALID",
            "is_valid": False,
            "reason": "The result parameter no longer exists in controlled master data.",
        }

    required, category = instrument_requirement(parameter)
    assessment = {
        "state": "NOT_REQUIRED" if not required else "INVALID",
        "is_valid": not required,
        "required": required,
        "category": category,
        "reference": value or None,
    }
    if not required:
        if value:
            assessment.update(
                {
                    "state": "INVALID",
                    "is_valid": False,
                    "reason": (
                        "No instrument is required for this parameter; "
                        "remove the instrument value."
                    ),
                }
            )
        return assessment

    if not category:
        assessment["reason"] = "The required instrument category is not configured in master data."
        return assessment
    if not value:
        assessment["reason"] = f"A registered {category} instrument is required."
        return assessment

    instrument, resolution_error = await resolve_registered_instrument(value)
    if resolution_error:
        assessment["reason"] = resolution_error
        return assessment
    assessment.update(
        {
            "registered_instrument_id": instrument["id"],
            "registered_instrument_code": instrument.get("instrument_code", ""),
            "registered_instrument_name": instrument.get("name", ""),
        }
    )
    if instrument.get("category") != category:
        assessment["reason"] = f"A registered {category} instrument is required for this method."
        return assessment

    eligible, state_reason = instrument_state(instrument)
    if not eligible:
        assessment["reason"] = state_reason
        return assessment

    assessment.update(
        {
            "state": "VALID",
            "is_valid": True,
            "reason": "",
        }
    )
    return assessment


def issue_for(parameter: Dict[str, Any], assessment: Dict[str, Any]) -> Dict[str, str]:
    return {
        "parameter_id": parameter["id"],
        "parameter": parameter.get("name", parameter["id"]),
        "reason": assessment.get("reason", "Instrument traceability is invalid."),
    }


async def assert_result_instruments(results: list, parameters: Dict[str, Dict[str, Any]]) -> None:
    issues = []
    for item in results:
        parameter = parameters.get(item.parameter_id)
        if not parameter:
            continue
        assessment = await assess_instrument_traceability(parameter, item.instrument_id)
        if not assessment["is_valid"]:
            issues.append(issue_for(parameter, assessment))
    if issues:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Cannot save results: instrument traceability is invalid.",
                "instrument_issues": issues,
            },
        )


async def sample_with_traceability(sample: Dict[str, Any]) -> Dict[str, Any]:
    parameters = {
        item["id"]: item
        for item in await db.parameters.find({}, {"_id": 0}).to_list(500)
    }
    required_ids = {
        item["parameter_id"]
        for item in await db.specifications.find(
            {"sample_point_id": sample["sample_point_id"], "active": True},
            {"_id": 0, "parameter_id": 1},
        ).to_list(500)
    }
    results = []
    issues = []
    for stored in sample.get("results", []):
        result = dict(stored)
        parameter = parameters.get(result.get("parameter_id"))
        assessment = await assess_instrument_traceability(parameter, result.get("instrument_id"))
        result["instrument_traceability"] = assessment
        results.append(result)
        definitive = result.get("status") in {"PASS", "WARN", "FAIL"}
        if parameter and result.get("parameter_id") in required_ids and definitive:
            if not assessment["is_valid"]:
                issues.append(issue_for(parameter, assessment))

    enriched = dict(sample)
    enriched["results"] = results
    enriched["instrument_issues"] = issues
    return enriched


async def sample_instrument_issues(sample: Dict[str, Any]) -> List[Dict[str, str]]:
    enriched = await sample_with_traceability(sample)
    return enriched["instrument_issues"]


async def seed_traceability_master_data() -> None:
    for method, (required, category) in APPROVED_PARAMETER_INSTRUMENT_MAPPING.items():
        await db.parameters.update_many(
            {
                "method": method,
                "$or": [
                    {"instrument_required": {"$exists": False}},
                    {"instrument_category": {"$exists": False}},
                ],
            },
            {"$set": {"instrument_required": required, "instrument_category": category}},
        )
    for code, category in APPROVED_INSTRUMENT_CATEGORY_BY_CODE.items():
        await db.instruments.update_many(
            {"instrument_code": code, "category": {"$exists": False}},
            {"$set": {"category": category}},
        )
    await db.instruments.update_many(
        {"availability_status": {"$exists": False}},
        {"$set": {"availability_status": "AVAILABLE"}},
    )