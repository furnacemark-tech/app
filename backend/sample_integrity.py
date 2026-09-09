from typing import Any, Dict, List

from database import db


async def outstanding_required_parameters(sample: Dict[str, Any]) -> List[str]:
    """Return active specification parameters that do not have a definitive result."""
    specifications = await db.specifications.find(
        {"sample_point_id": sample["sample_point_id"], "active": True},
        {"_id": 0, "parameter_id": 1},
    ).to_list(500)
    required_ids = [item["parameter_id"] for item in specifications]
    if not required_ids:
        return []
    definitive_ids = {
        item["parameter_id"]
        for item in sample.get("results", [])
        if item.get("status") in {"PASS", "WARN", "FAIL"}
    }
    missing_ids = [item for item in required_ids if item not in definitive_ids]
    if not missing_ids:
        return []
    parameter_names = {
        item["id"]: item.get("name", item["id"])
        for item in await db.parameters.find(
            {},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(500)
    }
    return [parameter_names.get(item, item) for item in missing_ids]