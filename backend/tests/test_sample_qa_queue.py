"""Focused regressions for the QA/Admin sample attention queue."""
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
CREATED_SAMPLE_IDS = []
CREATED_POINT_IDS = []
CREATED_SPECIFICATION_IDS = []


def session(credentials):
    response = requests.post(f"{BASE}/auth/login", json=credentials, timeout=30)
    assert response.status_code == 200, response.text
    client = requests.Session()
    client.headers.update({"Authorization": f"Bearer {response.json()['access_token']}"})
    return client


def point_with_specs(admin, parameters):
    point = admin.post(
        f"{BASE}/sample-points",
        json={"name": f"QAQ-{uuid.uuid4().hex[:8]}", "description": "isolated QA queue test"},
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


def sample_for(qc, point):
    response = qc.post(
        f"{BASE}/samples",
        json={"sample_point_id": point["id"], "sample_date": "2026-09-08"},
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


def rows(queue, key):
    return queue["sample_queues"][key]


def row(queue, key, sample_id):
    return next(item for item in rows(queue, key) if item["id"] == sample_id)


def parameters(admin):
    return {item["name"]: item for item in admin.get(f"{BASE}/parameters", timeout=30).json()}


def set_sample_fields(sample_id, values):
    run_db(lambda: db.samples.update_one({"id": sample_id}, {"$set": values}))


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


def test_complete_submitted_sample_is_ready_for_qa_review():
    admin = session(ADMIN)
    qc = session(QC)
    qa = session(QA)
    ph = parameters(admin)["pH"]
    sample = sample_for(qc, point_with_specs(admin, [ph]))
    save_ph(qc, sample["id"], ph)
    submitted = qc.post(f"{BASE}/samples/{sample['id']}/submit", json={"comment": "ready"})
    assert submitted.status_code == 200, submitted.text
    queue = qa.get(f"{BASE}/qa/queues", timeout=30).json()
    assert row(queue, "ready_for_review", sample["id"])["attention_reasons"] == []
    assert all(item["id"] != sample["id"] for item in rows(queue, "blocked_incomplete"))


def test_incomplete_visible_record_lists_each_outstanding_parameter():
    admin = session(ADMIN)
    qa = session(QA)
    qc = session(QC)
    master = parameters(admin)
    sample = sample_for(qc, point_with_specs(admin, [master["Methanol"], master["Formaldehyde"]]))

    set_sample_fields(sample["id"], {"qa_status": "Pending Review"})
    queue = qa.get(f"{BASE}/qa/queues", timeout=30).json()
    reasons = row(queue, "blocked_incomplete", sample["id"])["attention_reasons"]
    assert reasons == ["2 required result(s) outstanding: Methanol, Formaldehyde"]


def test_failed_result_appears_in_oos_investigation_queue():
    admin = session(ADMIN)
    qa = session(QA)
    qc = session(QC)
    ph = parameters(admin)["pH"]
    sample = sample_for(qc, point_with_specs(admin, [ph]))
    save_ph(qc, sample["id"], ph, value=99.0)
    queue = qa.get(f"{BASE}/qa/queues", timeout=30).json()
    reasons = row(queue, "oos_investigation", sample["id"])["attention_reasons"]
    assert "OOS result: pH" in reasons


def test_invalid_required_instrument_appears_in_instrument_issue_queue():
    admin = session(ADMIN)
    qa = session(QA)
    qc = session(QC)
    ph = parameters(admin)["pH"]
    sample = sample_for(qc, point_with_specs(admin, [ph]))
    save_ph(qc, sample["id"], ph)

    set_sample_fields(
        sample["id"],
        {"results.0.instrument_id": "10", "qa_status": "Pending Review"},
    )
    queue = qa.get(f"{BASE}/qa/queues", timeout=30).json()
    reasons = row(queue, "instrument_issue", sample["id"])["attention_reasons"]
    assert any("pH" in reason and "not registered" in reason for reason in reasons)


def test_approved_sample_is_not_in_ready_for_review():
    admin = session(ADMIN)
    qa = session(QA)
    qc = session(QC)
    ph = parameters(admin)["pH"]
    sample = sample_for(qc, point_with_specs(admin, [ph]))
    save_ph(qc, sample["id"], ph)
    submitted = qc.post(
        f"{BASE}/samples/{sample['id']}/submit",
        json={"comment": "ready"},
    )
    assert submitted.status_code == 200
    assert qa.post(
        f"{BASE}/samples/{sample['id']}/decision/approve",
        json={"comment": "approved"},
    ).status_code == 200
    queue = qa.get(f"{BASE}/qa/queues", timeout=30).json()
    assert row(queue, "approved", sample["id"])["qa_status"] == "Approved"
    assert all(item["id"] != sample["id"] for item in rows(queue, "ready_for_review"))


def test_rejected_sample_is_returned_rejected_and_oos():
    admin = session(ADMIN)
    qa = session(QA)
    qc = session(QC)
    ph = parameters(admin)["pH"]
    sample = sample_for(qc, point_with_specs(admin, [ph]))
    save_ph(qc, sample["id"], ph)
    submitted = qc.post(
        f"{BASE}/samples/{sample['id']}/submit",
        json={"comment": "ready"},
    )
    assert submitted.status_code == 200
    assert qa.post(
        f"{BASE}/samples/{sample['id']}/decision/reject",
        json={"comment": "return to QC"},
    ).status_code == 200
    queue = qa.get(f"{BASE}/qa/queues", timeout=30).json()
    reasons = row(queue, "returned_rejected", sample["id"])["attention_reasons"]
    assert "QA rejected / returned for investigation" in reasons
    assert any(item["id"] == sample["id"] for item in rows(queue, "oos_investigation"))


def test_record_with_incomplete_and_instrument_issues_has_both_reasons():
    admin = session(ADMIN)
    qa = session(QA)
    qc = session(QC)
    master = parameters(admin)
    sample = sample_for(qc, point_with_specs(admin, [master["pH"], master["COD"]]))
    save_ph(qc, sample["id"], master["pH"])

    set_sample_fields(
        sample["id"],
        {"results.0.instrument_id": "10", "qa_status": "Pending Review"},
    )
    queue = qa.get(f"{BASE}/qa/queues", timeout=30).json()
    blocked = row(queue, "blocked_incomplete", sample["id"])
    instrument = row(queue, "instrument_issue", sample["id"])
    assert blocked["id"] == instrument["id"]
    assert "COD" in " ".join(blocked["attention_reasons"])
    assert any("pH" in reason for reason in instrument["attention_reasons"])


def test_qc_cannot_access_sample_qa_queue_information():
    response = session(QC).get(f"{BASE}/qa/queues", timeout=30)
    assert response.status_code == 403, response.text