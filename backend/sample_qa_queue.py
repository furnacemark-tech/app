from datetime import date
from math import ceil
from typing import Any, Dict, List

from database import db
from instrument_traceability import sample_with_traceability
from sample_integrity import outstanding_required_parameters


SAMPLE_QUEUE_KEYS = (
    "ready_for_review",
    "blocked_incomplete",
    "oos_investigation",
    "instrument_issue",
    "approved",
    "returned_rejected",
)

CATEGORY_TO_QUEUE_KEY = {
    "ready": "ready_for_review",
    "blocked": "blocked_incomplete",
    "oos": "oos_investigation",
    "instrument_issue": "instrument_issue",
    "approved": "approved",
    "returned": "returned_rejected",
}


def _queue_pipeline() -> List[Dict[str, Any]]:
    today = date.today().isoformat()
    return [
        {
            "$lookup": {
                "from": "sample_points",
                "localField": "sample_point_id",
                "foreignField": "id",
                "as": "sample_point",
            }
        },
        {
            "$lookup": {
                "from": "specifications",
                "let": {"point_id": "$sample_point_id"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$sample_point_id", "$$point_id"]},
                                    {"$eq": ["$active", True]},
                                ]
                            }
                        }
                    },
                    {
                        "$lookup": {
                            "from": "parameters",
                            "localField": "parameter_id",
                            "foreignField": "id",
                            "as": "parameter",
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "parameter_id": 1,
                            "parameter_name": {
                                "$ifNull": [{"$arrayElemAt": ["$parameter.name", 0]}, "$parameter_id"]
                            },
                        }
                    },
                ],
                "as": "active_specs",
            }
        },
        {
            "$lookup": {
                "from": "parameters",
                "localField": "results.parameter_id",
                "foreignField": "id",
                "as": "parameters",
            }
        },
        {
            "$addFields": {
                "result_instrument_references": {
                    "$filter": {
                        "input": {
                            "$map": {
                                "input": {"$ifNull": ["$results", []]},
                                "as": "result",
                                "in": {"$ifNull": ["$$result.instrument_id", ""]},
                            }
                        },
                        "as": "reference",
                        "cond": {"$ne": ["$$reference", ""]},
                    }
                },
                "definitive_result_ids": {
                    "$map": {
                        "input": {
                            "$filter": {
                                "input": {"$ifNull": ["$results", []]},
                                "as": "result",
                                "cond": {"$in": ["$$result.status", ["PASS", "WARN", "FAIL"]]},
                            }
                        },
                        "as": "result",
                        "in": "$$result.parameter_id",
                    }
                },
            }
        },
        {
            "$lookup": {
                "from": "instruments",
                "let": {"references": "$result_instrument_references"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$or": [
                                    {"$in": ["$id", "$$references"]},
                                    {"$in": ["$instrument_code", "$$references"]},
                                ]
                            }
                        }
                    },
                    {"$project": {"_id": 0}},
                ],
                "as": "registered_instruments",
            }
        },
        {
            "$lookup": {
                "from": "oos_log",
                "let": {"sample_id": "$id"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$sample_id", "$$sample_id"]},
                                    {"$eq": ["$status", "Open"]},
                                ]
                            }
                        }
                    },
                    {"$limit": 1},
                ],
                "as": "open_oos",
            }
        },
        {
            "$addFields": {
                "sample_point_name": {"$ifNull": [{"$arrayElemAt": ["$sample_point.name", 0]}, ""]},
                "outstanding_specs": {
                    "$filter": {
                        "input": "$active_specs",
                        "as": "specification",
                        "cond": {
                            "$not": [
                                {"$in": ["$$specification.parameter_id", "$definitive_result_ids"]}
                            ]
                        },
                    }
                },
                "failed_parameters": {
                    "$map": {
                        "input": {
                            "$filter": {
                                "input": {"$ifNull": ["$results", []]},
                                "as": "result",
                                "cond": {"$eq": ["$$result.status", "FAIL"]},
                            }
                        },
                        "as": "result",
                        "in": {"$ifNull": ["$$result.parameter_name", "$$result.parameter_id"]},
                    }
                },
            }
        },
        {
            "$addFields": {
                "has_instrument_issue": {
                    "$anyElementTrue": {
                        "$map": {
                            "input": {"$ifNull": ["$results", []]},
                            "as": "result",
                            "in": {
                                "$let": {
                                    "vars": {
                                        "parameter": {
                                            "$arrayElemAt": [
                                                {
                                                    "$filter": {
                                                        "input": "$parameters",
                                                        "as": "parameter",
                                                        "cond": {
                                                            "$eq": [
                                                                "$$parameter.id",
                                                                "$$result.parameter_id",
                                                            ]
                                                        },
                                                    }
                                                },
                                                0,
                                            ]
                                        },
                                        "instrument": {
                                            "$arrayElemAt": [
                                                {
                                                    "$filter": {
                                                        "input": "$registered_instruments",
                                                        "as": "instrument",
                                                        "cond": {
                                                            "$or": [
                                                                {"$eq": ["$$instrument.id", "$$result.instrument_id"]},
                                                                {
                                                                    "$eq": [
                                                                        "$$instrument.instrument_code",
                                                                        "$$result.instrument_id",
                                                                    ]
                                                                },
                                                            ]
                                                        },
                                                    }
                                                },
                                                0,
                                            ]
                                        },
                                        "is_required_spec": {
                                            "$in": [
                                                "$$result.parameter_id",
                                                "$active_specs.parameter_id",
                                            ]
                                        },
                                    },
                                    "in": {
                                        "$and": [
                                            {"$in": ["$$result.status", ["PASS", "WARN", "FAIL"]]},
                                            "$$is_required_spec",
                                            {"$ne": [{"$ifNull": ["$$parameter.id", None]}, None]},
                                            {
                                                "$cond": [
                                                    {"$eq": ["$$parameter.instrument_required", True]},
                                                    {
                                                        "$or": [
                                                            {
                                                                "$eq": [
                                                                    {"$ifNull": ["$$result.instrument_id", ""]},
                                                                    "",
                                                                ]
                                                            },
                                                            {
                                                                "$eq": [
                                                                    {"$ifNull": ["$$instrument.id", None]},
                                                                    None,
                                                                ]
                                                            },
                                                            {
                                                                "$ne": [
                                                                    "$$instrument.category",
                                                                    "$$parameter.instrument_category",
                                                                ]
                                                            },
                                                            {"$ne": ["$$instrument.active", True]},
                                                            {
                                                                "$ne": [
                                                                    {
                                                                        "$ifNull": [
                                                                            "$$instrument.availability_status",
                                                                            "AVAILABLE",
                                                                        ]
                                                                    },
                                                                    "AVAILABLE",
                                                                ]
                                                            },
                                                            {"$lt": ["$$instrument.calibration_due", today]},
                                                            {"$lt": ["$$instrument.service_due", today]},
                                                        ]
                                                    },
                                                    {
                                                        "$ne": [
                                                            {"$ifNull": ["$$result.instrument_id", ""]},
                                                            "",
                                                        ]
                                                    },
                                                ]
                                            },
                                        ]
                                    },
                                }
                            },
                        }
                    }
                },
                "open_oos_count": {"$size": "$open_oos"},
            }
        },
        {
            "$addFields": {
                "is_ready": {
                    "$and": [
                        {"$eq": ["$qa_status", "Pending Review"]},
                        {"$eq": [{"$size": "$outstanding_specs"}, 0]},
                        {"$eq": ["$has_instrument_issue", False]},
                    ]
                },
                "is_blocked": {
                    "$and": [
                        {"$ne": ["$qa_status", "Not Submitted"]},
                        {"$gt": [{"$size": "$outstanding_specs"}, 0]},
                    ]
                },
                "is_oos": {
                    "$or": [
                        {"$gt": [{"$size": "$failed_parameters"}, 0]},
                        {"$gt": ["$open_oos_count", 0]},
                        {"$eq": ["$qa_status", "Requires Investigation"]},
                    ]
                },
                "is_approved": {"$eq": ["$qa_status", "Approved"]},
                "is_returned": {"$eq": ["$qa_status", "Requires Investigation"]},
            }
        },
    ]


def _category_match(category: str) -> Dict[str, Any]:
    fields = {
        "ready": "is_ready",
        "blocked": "is_blocked",
        "oos": "is_oos",
        "instrument_issue": "has_instrument_issue",
        "approved": "is_approved",
        "returned": "is_returned",
    }
    return {fields[category]: True}


def _search_match(search: str | None) -> Dict[str, Any] | None:
    if not search:
        return None
    escaped = search.strip()
    if not escaped:
        return None
    return {
        "$or": [
            {"record_id": {"$regex": escaped, "$options": "i"}},
            {"sample_point_name": {"$regex": escaped, "$options": "i"}},
        ]
    }


def _instrument_attention(enriched: Dict[str, Any]) -> List[str]:
    results_by_parameter = {
        item.get("parameter_id"): item
        for item in enriched.get("results", [])
    }
    messages = []
    for issue in enriched.get("instrument_issues", []):
        result = results_by_parameter.get(issue["parameter_id"], {})
        traceability = result.get("instrument_traceability", {})
        reference = traceability.get("registered_instrument_code")
        if not reference:
            reference = traceability.get("registered_instrument_name")
        reason = issue["reason"]
        if reference and any(
            phrase in reason.lower()
            for phrase in ("inactive", "overdue", "failed", "unavailable")
        ):
            messages.append(f"Instrument unavailable or overdue: {reference}")
        else:
            messages.append(f"Instrument traceability: {issue['parameter']}: {reason}")
    return list(dict.fromkeys(messages))


def _sample_row(
    sample: Dict[str, Any],
    attention_reasons: List[str],
) -> Dict[str, Any]:
    return {
        "id": sample["id"],
        "record_id": sample["record_id"],
        "sample_point_name": sample.get("sample_point_name", ""),
        "sample_date": sample.get("sample_date", ""),
        "analyst_initials": sample.get("analyst_initials", ""),
        "status": sample.get("status", ""),
        "qa_status": sample.get("qa_status", ""),
        "overall_result": sample.get("overall_result", ""),
        "attention_reasons": attention_reasons,
    }


async def build_sample_qa_queues(
    category: str,
    page: int,
    page_size: int,
    search: str | None = None,
) -> Dict[str, Any]:
    pipeline = _queue_pipeline()
    count_facets = {
        queue_key: [{"$match": _category_match(category_key)}, {"$count": "total"}]
        for category_key, queue_key in CATEGORY_TO_QUEUE_KEY.items()
    }
    count_facets["total_attention_records"] = [
        {
            "$match": {
                "$or": [
                    {"is_ready": True},
                    {"is_blocked": True},
                    {"is_oos": True},
                    {"has_instrument_issue": True},
                    {"is_approved": True},
                    {"is_returned": True},
                ]
            }
        },
        {"$count": "total"},
    ]
    count_result = await db.samples.aggregate([*pipeline, {"$facet": count_facets}]).to_list(1)
    facets = count_result[0] if count_result else {}
    category_counts = {
        category_key: (facets.get(queue_key) or [{"total": 0}])[0]["total"]
        for category_key, queue_key in CATEGORY_TO_QUEUE_KEY.items()
    }
    total_attention_records = (facets.get("total_attention_records") or [{"total": 0}])[0]["total"]

    item_pipeline = [*pipeline, {"$match": _category_match(category)}]
    search_match = _search_match(search)
    if search_match:
        item_pipeline.append({"$match": search_match})
    item_pipeline.extend(
        [
            {"$sort": {"sample_date": -1, "created_at": -1, "record_id": -1}},
            {
                "$facet": {
                    "items": [
                        {"$skip": (page - 1) * page_size},
                        {"$limit": page_size},
                        {"$project": {"_id": 0}},
                    ],
                    "total": [{"$count": "total"}],
                }
            },
        ]
    )
    page_result = await db.samples.aggregate(item_pipeline).to_list(1)
    page_facets = page_result[0] if page_result else {"items": [], "total": []}
    total_items = (page_facets.get("total") or [{"total": 0}])[0]["total"]
    total_pages = max(1, ceil(total_items / page_size))
    items = []
    for sample in page_facets.get("items", []):
        enriched = await sample_with_traceability(sample)
        outstanding = await outstanding_required_parameters(sample)
        attention_reasons = []
        if outstanding:
            attention_reasons.append(
                f"{len(outstanding)} required result(s) outstanding: {', '.join(outstanding)}"
            )
        attention_reasons.extend(_instrument_attention(enriched))
        failed_parameters = [
            item.get("parameter_name", item.get("parameter_id", "Result"))
            for item in sample.get("results", [])
            if item.get("status") == "FAIL"
        ]
        if failed_parameters:
            attention_reasons.append(f"OOS result: {', '.join(failed_parameters)}")
        if sample.get("open_oos_count", 0) > 0:
            attention_reasons.append("Open OOS investigation")
        if sample.get("qa_status") == "Requires Investigation":
            attention_reasons.append("QA rejected / returned for investigation")
        items.append(_sample_row(enriched, attention_reasons))

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_previous": page > 1,
        "has_next": page < total_pages,
        "category_counts": category_counts,
        "total_attention_records": total_attention_records,
    }