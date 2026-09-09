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


async def build_sample_qa_queues() -> Dict[str, Any]:
    samples = await db.samples.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    open_oos = {
        item["sample_id"]
        for item in await db.oos_log.find(
            {"status": "Open"},
            {"_id": 0, "sample_id": 1},
        ).to_list(500)
    }
    queues = {key: [] for key in SAMPLE_QUEUE_KEYS}
    for sample in samples:
        enriched = await sample_with_traceability(sample)
        outstanding = await outstanding_required_parameters(sample)
        instrument_messages = _instrument_attention(enriched)
        failed_parameters = [
            item.get("parameter_name", item.get("parameter_id", "Result"))
            for item in sample.get("results", [])
            if item.get("status") == "FAIL"
        ]
        attention_reasons = []
        if outstanding:
            attention_reasons.append(
                f"{len(outstanding)} required result(s) outstanding: {', '.join(outstanding)}"
            )
        attention_reasons.extend(instrument_messages)
        if failed_parameters:
            attention_reasons.append(f"OOS result: {', '.join(failed_parameters)}")
        if sample["id"] in open_oos:
            attention_reasons.append("Open OOS investigation")
        if sample.get("qa_status") == "Requires Investigation":
            attention_reasons.append("QA rejected / returned for investigation")

        row = _sample_row(sample, attention_reasons)
        has_instrument_issue = bool(enriched.get("instrument_issues"))
        has_oos = bool(failed_parameters) or sample["id"] in open_oos
        is_returned = sample.get("qa_status") == "Requires Investigation"
        is_approved = sample.get("qa_status") == "Approved"
        is_blocked = bool(outstanding) and sample.get("qa_status") != "Not Submitted"
        is_ready = (
            sample.get("qa_status") == "Pending Review"
            and not outstanding
            and not has_instrument_issue
        )
        if is_ready:
            queues["ready_for_review"].append(row)
        if is_blocked:
            queues["blocked_incomplete"].append(row)
        if has_oos or is_returned:
            queues["oos_investigation"].append(row)
        if has_instrument_issue:
            queues["instrument_issue"].append(row)
        if is_approved:
            queues["approved"].append(row)
        if is_returned:
            queues["returned_rejected"].append(row)

    return {
        "sample_queues": queues,
        "sample_queue_counts": {key: len(rows) for key, rows in queues.items()},
    }