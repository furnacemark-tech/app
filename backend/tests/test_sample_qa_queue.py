"""Focused regressions for the QA/Admin sample attention queue.

Migrated to the server-side paginated, single-category `items` contract:
`GET /api/qa/queues?category=&page=&page_size=&search=` returns one category's
page in `items`, plus `page`, `page_size`, `total_items`, `total_pages`,
`has_previous`, `has_next`, `category_counts` (all six categories) and
`total_attention_records` (distinct records across categories).
"""
import os
import uuid
from pathlib import Path

import requests
import pytest
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / "frontend" / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env")

from database import db
from conftest import run_db

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"email": "admin@lims.local", "password": "Admin@123"}
QA = {"email": "qa@lims.local", "password": "Qa@12345"}
QC = {"email": "qc@lims.local", "password": "Qc@12345"}
CATEGORIES = ("ready", "blocked", "oos", "instrument_issue", "approved", "returned")
CREATED_SAMPLE_IDS = []
CREATED_POINT_IDS = []
CREATED_SPECIFICATION_IDS = []


def session(credentials):
    response = requests.post(f"{BASE}/auth/login", json=credentials, timeout=30)
    assert response.status_code == 200, response.text
    client = requests.Session()
    client.headers.update({"Authorization": f"Bearer {response.json()['access_token']}"})
    return client


def named_point_with_specs(admin, name, parameters):
    point = admin.post(
        f"{BASE}/sample-points",
        json={"name": name, "description": "isolated QA queue test"},
        timeout=30,
    ).json()
    CREATED_POINT_IDS.append(point["id"])
    for parameter in parameters:
        response = admin.post(
            f"{BASE}/specifications",
            json={
                "sample_point_id": point["id"],
                "parameter_id": parameter["id"],
                "lower_limit": 0,
                "upper_limit": 20,
                "expected_text": None,
                "active": True,
            },
            timeout=30,
        )
        assert response.status_code == 200, response.text
        CREATED_SPECIFICATION_IDS.append(response.json()["id"])
    return point


def point_with_specs(admin, parameters):
    return named_point_with_specs(admin, f"QAQ-{uuid.uuid4().hex[:8]}", parameters)


def sample_for(qc, point, sample_date="2026-09-08"):
    response = qc.post(
        f"{BASE}/samples",
        json={"sample_point_id": point["id"], "sample_date": sample_date},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    sample = response.json()
    CREATED_SAMPLE_IDS.append(sample["id"])
    return sample


def save_ph(qc, sample_id, parameter, value=10.0):
    response = qc.post(
        f"{BASE}/samples/{sample_id}/results",
        json={
            "results": [
                {
                    "parameter_id": parameter["id"],
                    "value_numeric": value,
                    "instrument_id": "PH-204",
                }
            ]
        },
        timeout=30,
    )
    assert response.status_code == 200, response.text


def submit(qc, sample_id):
    response = qc.post(f"{BASE}/samples/{sample_id}/submit", json={"comment": "ready"}, timeout=30)
    assert response.status_code == 200, response.text


def ready_sample(admin, qc, point, ph, sample_date="2026-09-08"):
    sample = sample_for(qc, point, sample_date=sample_date)
    save_ph(qc, sample["id"], ph)
    submit(qc, sample["id"])
    return sample


def parameters(admin):
    return {item["name"]: item for item in admin.get(f"{BASE}/parameters", timeout=30).json()}


def set_sample_fields(sample_id, values):
    run_db(lambda: db.samples.update_one({"id": sample_id}, {"$set": values}))


def fetch(client, category="ready", page=1, page_size=25, search=None):
    params = {"category": category, "page": page, "page_size": page_size}
    if search is not None:
        params["search"] = search
    response = client.get(f"{BASE}/qa/queues", params=params, timeout=30)
    assert response.status_code == 200, response.text
    return response.json()


def ids(payload):
    return [item["id"] for item in payload["items"]]


def find(payload, sample_id):
    return next((item for item in payload["items"] if item["id"] == sample_id), None)


@pytest.fixture(scope="module", autouse=True)
def clean_isolated_queue_records():
    yield

    async def remove_queue_records():
        entity_ids = CREATED_SAMPLE_IDS + CREATED_POINT_IDS + CREATED_SPECIFICATION_IDS
        await db.oos_log.delete_many({"sample_id": {"$in": CREATED_SAMPLE_IDS}})
        await db.audit_trail.delete_many({"entity_id": {"$in": entity_ids}})
        await db.samples.delete_many({"id": {"$in": CREATED_SAMPLE_IDS}})
        await db.specifications.delete_many({"id": {"$in": CREATED_SPECIFICATION_IDS}})
        await db.sample_points.delete_many({"id": {"$in": CREATED_POINT_IDS}})

    run_db(remove_queue_records)


# --------------------------------------------------------------------------- #
# Classification (migrated to single-category items contract)
# --------------------------------------------------------------------------- #
def test_complete_submitted_sample_is_ready_for_qa_review():
    admin, qc, qa = session(ADMIN), session(QC), session(QA)
    ph = parameters(admin)["pH"]
    sample = ready_sample(admin, qc, point_with_specs(admin, [ph]), ph)
    row = find(fetch(qa, "ready", page_size=100), sample["id"])
    assert row is not None
    assert row["attention_reasons"] == []
    assert sample["id"] not in ids(fetch(qa, "blocked", page_size=100))


def test_incomplete_visible_record_lists_each_outstanding_parameter():
    admin, qa, qc = session(ADMIN), session(QA), session(QC)
    master = parameters(admin)
    sample = sample_for(qc, point_with_specs(admin, [master["Methanol"], master["Formaldehyde"]]))
    set_sample_fields(sample["id"], {"qa_status": "Pending Review"})
    row = find(fetch(qa, "blocked", page_size=100), sample["id"])
    assert row is not None
    assert row["attention_reasons"] == ["2 required result(s) outstanding: Methanol, Formaldehyde"]


def test_failed_result_appears_in_oos_investigation_queue():
    admin, qa, qc = session(ADMIN), session(QA), session(QC)
    ph = parameters(admin)["pH"]
    sample = sample_for(qc, point_with_specs(admin, [ph]))
    save_ph(qc, sample["id"], ph, value=99.0)
    row = find(fetch(qa, "oos", page_size=100), sample["id"])
    assert row is not None
    assert "OOS result: pH" in row["attention_reasons"]


def test_invalid_required_instrument_appears_in_instrument_issue_queue():
    admin, qa, qc = session(ADMIN), session(QA), session(QC)
    ph = parameters(admin)["pH"]
    sample = sample_for(qc, point_with_specs(admin, [ph]))
    save_ph(qc, sample["id"], ph)
    set_sample_fields(sample["id"], {"results.0.instrument_id": "10", "qa_status": "Pending Review"})
    row = find(fetch(qa, "instrument_issue", page_size=100), sample["id"])
    assert row is not None
    assert any("pH" in reason and "not registered" in reason for reason in row["attention_reasons"])


def test_approved_sample_is_not_in_ready_for_review():
    admin, qa, qc = session(ADMIN), session(QA), session(QC)
    ph = parameters(admin)["pH"]
    sample = ready_sample(admin, qc, point_with_specs(admin, [ph]), ph)
    assert qa.post(f"{BASE}/samples/{sample['id']}/decision/approve",
                   json={"comment": "approved"}).status_code == 200
    row = find(fetch(qa, "approved", page_size=100), sample["id"])
    assert row is not None and row["qa_status"] == "Approved"
    assert sample["id"] not in ids(fetch(qa, "ready", page_size=100))


def test_rejected_sample_is_returned_rejected_and_oos():
    admin, qa, qc = session(ADMIN), session(QA), session(QC)
    ph = parameters(admin)["pH"]
    sample = ready_sample(admin, qc, point_with_specs(admin, [ph]), ph)
    assert qa.post(f"{BASE}/samples/{sample['id']}/decision/reject",
                   json={"comment": "return to QC"}).status_code == 200
    returned = find(fetch(qa, "returned", page_size=100), sample["id"])
    assert returned is not None
    assert "QA rejected / returned for investigation" in returned["attention_reasons"]
    assert sample["id"] in ids(fetch(qa, "oos", page_size=100))


def test_record_with_incomplete_and_instrument_issues_has_both_reasons():
    admin, qa, qc = session(ADMIN), session(QA), session(QC)
    master = parameters(admin)
    sample = sample_for(qc, point_with_specs(admin, [master["pH"], master["COD"]]))
    save_ph(qc, sample["id"], master["pH"])
    set_sample_fields(sample["id"], {"results.0.instrument_id": "10", "qa_status": "Pending Review"})
    blocked = find(fetch(qa, "blocked", page_size=100), sample["id"])
    instrument = find(fetch(qa, "instrument_issue", page_size=100), sample["id"])
    assert blocked is not None and instrument is not None
    assert blocked["id"] == instrument["id"]
    assert "COD" in " ".join(blocked["attention_reasons"])
    assert any("pH" in reason for reason in instrument["attention_reasons"])


# --------------------------------------------------------------------------- #
# Pagination
# --------------------------------------------------------------------------- #
def test_pagination_splits_a_category_without_overlap():
    admin, qc, qa = session(ADMIN), session(QC), session(QA)
    ph = parameters(admin)["pH"]
    point = point_with_specs(admin, [ph])  # one searchable sample point, three ready samples
    created = {ready_sample(admin, qc, point, ph)["id"] for _ in range(3)}
    token = point["name"]

    page1 = fetch(qa, "ready", page=1, page_size=2, search=token)
    page2 = fetch(qa, "ready", page=2, page_size=2, search=token)

    assert page1["total_items"] == 3
    assert page1["total_pages"] == 2
    assert page1["page"] == 1 and page1["page_size"] == 2
    assert len(page1["items"]) == 2
    assert page1["has_previous"] is False and page1["has_next"] is True
    assert len(page2["items"]) == 1
    assert page2["has_previous"] is True and page2["has_next"] is False

    seen = set(ids(page1)) | set(ids(page2))
    assert seen == created
    assert set(ids(page1)).isdisjoint(set(ids(page2)))


def test_pagination_out_of_range_page_is_empty_but_totals_hold():
    admin, qc, qa = session(ADMIN), session(QC), session(QA)
    ph = parameters(admin)["pH"]
    point = point_with_specs(admin, [ph])
    ready_sample(admin, qc, point, ph)
    payload = fetch(qa, "ready", page=99, page_size=25, search=point["name"])
    assert payload["items"] == []
    assert payload["total_items"] == 1
    assert payload["has_next"] is False


# --------------------------------------------------------------------------- #
# Search (literal, regex-metacharacter safe)
# --------------------------------------------------------------------------- #
def test_search_matches_record_id_and_sample_point_name():
    admin, qc, qa = session(ADMIN), session(QC), session(QA)
    ph = parameters(admin)["pH"]
    point = point_with_specs(admin, [ph])
    sample = ready_sample(admin, qc, point, ph)

    by_point = fetch(qa, "ready", page_size=100, search=point["name"])
    assert ids(by_point) == [sample["id"]]
    by_record = fetch(qa, "ready", page_size=100, search=sample["record_id"])
    assert sample["id"] in ids(by_record)


def test_search_escapes_regex_metacharacters():
    admin, qc, qa = session(ADMIN), session(QC), session(QA)
    ph = parameters(admin)["pH"]
    token = uuid.uuid4().hex[:8]
    dotted = ready_sample(admin, qc, named_point_with_specs(admin, f"qaq{token}a.b", [ph]), ph)
    literal = ready_sample(admin, qc, named_point_with_specs(admin, f"qaq{token}axb", [ph]), ph)

    # "a.b" must be treated literally: it must NOT match the "axb" sample point.
    result = fetch(qa, "ready", page_size=100, search=f"qaq{token}a.b")
    assert result["total_items"] == 1
    assert ids(result) == [dotted["id"]]
    assert literal["id"] not in ids(result)


# --------------------------------------------------------------------------- #
# Ordering
# --------------------------------------------------------------------------- #
def test_ordering_is_by_sample_date_then_recency_descending():
    admin, qc, qa = session(ADMIN), session(QC), session(QA)
    ph = parameters(admin)["pH"]
    point = point_with_specs(admin, [ph])
    older = ready_sample(admin, qc, point, ph, sample_date="2026-09-01")
    middle = ready_sample(admin, qc, point, ph, sample_date="2026-09-02")
    newer = ready_sample(admin, qc, point, ph, sample_date="2026-09-03")
    payload = fetch(qa, "ready", page_size=100, search=point["name"])
    assert ids(payload) == [newer["id"], middle["id"], older["id"]]


# --------------------------------------------------------------------------- #
# Counts (facet ↔ items consistency; distinct-record total)
# --------------------------------------------------------------------------- #
def test_category_counts_match_item_totals_and_distinct_attention_total():
    admin, qc, qa = session(ADMIN), session(QC), session(QA)
    ph = parameters(admin)["pH"]
    ready_sample(admin, qc, point_with_specs(admin, [ph]), ph)  # guarantee >0 attention records

    snapshot = fetch(qa, "ready", page_size=100)
    counts = snapshot["category_counts"]

    union = set()
    for category in CATEGORIES:
        page = fetch(qa, category, page_size=100)
        assert counts[category] == page["total_items"], category
        assert len(page["items"]) == page["total_items"] <= 100, category
        union |= set(ids(page))

    total = snapshot["total_attention_records"]
    assert total == len(union)
    assert total > 0
    assert total <= sum(counts.values())  # distinct <= sum across categories


# --------------------------------------------------------------------------- #
# Classification ↔ displayed-reason agreement
# --------------------------------------------------------------------------- #
def test_displayed_reasons_agree_with_classification():
    admin, qc, qa = session(ADMIN), session(QC), session(QA)
    master = parameters(admin)
    ph = master["pH"]
    # Seed one record per assertable category so each loop below is non-trivial.
    ready_sample(admin, qc, point_with_specs(admin, [ph]), ph)
    incomplete = sample_for(qc, point_with_specs(admin, [master["Methanol"]]))
    set_sample_fields(incomplete["id"], {"qa_status": "Pending Review"})
    oos = sample_for(qc, point_with_specs(admin, [ph]))
    save_ph(qc, oos["id"], ph, value=99.0)
    bad = sample_for(qc, point_with_specs(admin, [ph]))
    save_ph(qc, bad["id"], ph)
    set_sample_fields(bad["id"], {"results.0.instrument_id": "10", "qa_status": "Pending Review"})

    for row in fetch(qa, "ready", page_size=100)["items"]:
        assert row["attention_reasons"] == []
    for row in fetch(qa, "blocked", page_size=100)["items"]:
        assert any("outstanding" in reason.lower() for reason in row["attention_reasons"])
    for row in fetch(qa, "oos", page_size=100)["items"]:
        assert any(
            any(token in reason.lower() for token in ("oos", "investigation", "rejected"))
            for reason in row["attention_reasons"]
        )
    for row in fetch(qa, "instrument_issue", page_size=100)["items"]:
        assert any("instrument" in reason.lower() for reason in row["attention_reasons"])


# --------------------------------------------------------------------------- #
# Validation (FastAPI query constraints)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page_size": 0},
        {"page_size": 101},
        {"category": "bogus"},
        {"search": "x" * 121},
    ],
)
def test_invalid_query_parameters_are_rejected(params):
    qa = session(QA)
    request = {"category": "ready", "page": 1, "page_size": 25, **params}
    response = qa.get(f"{BASE}/qa/queues", params=request, timeout=30)
    assert response.status_code == 422, response.text


def test_valid_boundary_parameters_are_accepted():
    qa = session(QA)
    for params in ({"page_size": 1}, {"page_size": 100}, {"category": "returned"}):
        response = qa.get(f"{BASE}/qa/queues",
                          params={"category": "ready", "page": 1, "page_size": 25, **params},
                          timeout=30)
        assert response.status_code == 200, response.text


# --------------------------------------------------------------------------- #
# Access control
# --------------------------------------------------------------------------- #
def test_qc_cannot_access_sample_qa_queue_information():
    response = session(QC).get(f"{BASE}/qa/queues", timeout=30)
    assert response.status_code == 403, response.text


def test_unauthenticated_request_is_rejected():
    response = requests.get(f"{BASE}/qa/queues", timeout=30)
    assert response.status_code == 401, response.text


def test_admin_can_access_sample_qa_queue():
    response = session(ADMIN).get(f"{BASE}/qa/queues", params={"category": "ready"}, timeout=30)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "items" in body and "category_counts" in body and "total_attention_records" in body
