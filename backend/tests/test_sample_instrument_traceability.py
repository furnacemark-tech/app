"""Regression coverage for controlled sample instrument traceability."""
import asyncio
import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / "frontend" / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env")

from database import db

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"email": "admin@lims.local", "password": "Admin@123"}
QA = {"email": "qa@lims.local", "password": "Qa@12345"}
QC = {"email": "qc@lims.local", "password": "Qc@12345"}


def session(credentials):
    response = requests.post(f"{BASE}/auth/login", json=credentials, timeout=30)
    assert response.status_code == 200, response.text
    client = requests.Session()
    client.headers.update({"Authorization": f"Bearer {response.json()['access_token']}"})
    return client


def create_point(admin, parameter):
    point = admin.post(
        f"{BASE}/sample-points",
        json={"name": f"IT-{uuid.uuid4().hex[:8]}", "description": "instrument traceability"},
        timeout=30,
    ).json()
    specification = admin.post(
        f"{BASE}/specifications",
        json={
            "sample_point_id": point["id"],
            "parameter_id": parameter["id"],
            "lower_limit": 0,
            "upper_limit": 100,
            "expected_text": None,
            "active": True,
        },
        timeout=30,
    )
    assert specification.status_code == 200, specification.text
    return point


def create_sample(qc, point):
    response = qc.post(
        f"{BASE}/samples",
        json={"sample_point_id": point["id"], "sample_date": "2026-09-07"},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    return response.json()


def save_numeric(qc, sample_id, parameter, instrument_id=None):
    result = {"parameter_id": parameter["id"], "value_numeric": 10.0}
    if instrument_id is not None:
        result["instrument_id"] = instrument_id
    return qc.post(
        f"{BASE}/samples/{sample_id}/results",
        json={"results": [result]},
        timeout=30,
    )


def instrument_issue(response, parameter_name, phrase):
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["instrument_issues"][0]["parameter"] == parameter_name
    assert phrase in detail["instrument_issues"][0]["reason"]


@pytest.fixture(scope="module")
def master_data():
    admin = session(ADMIN)
    parameters = {item["name"]: item for item in admin.get(f"{BASE}/parameters", timeout=30).json()}
    expected = {
        "Appearance": (False, "MANUAL_VISUAL"),
        "pH": (True, "PH_METER"),
        "COD": (False, "MANUAL_NOT_CURRENTLY_CONTROLLED"),
        "Ammonia": (False, "MANUAL_NOT_CURRENTLY_CONTROLLED"),
        "Methanol": (True, "GC"),
        "Formaldehyde": (True, "HPLC"),
        "Suspended Solids": (False, "MANUAL_NOT_CURRENTLY_CONTROLLED"),
    }
    for name, (required, category) in expected.items():
        assert parameters[name]["instrument_required"] is required
        assert parameters[name]["instrument_category"] == category
    return {"admin": admin, "parameters": parameters}


def test_valid_compatible_ph_meter_is_accepted(master_data):
    qc = session(QC)
    parameter = master_data["parameters"]["pH"]
    sample = create_sample(qc, create_point(master_data["admin"], parameter))
    response = save_numeric(qc, sample["id"], parameter, "PH-204")
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["instrument_id"] == "PH-204"
    assert result["instrument_traceability"]["state"] == "VALID"


@pytest.mark.parametrize("identifier", ["10", "NOT-A-REGISTERED-INSTRUMENT"])
def test_arbitrary_or_nonexistent_identifier_is_rejected(master_data, identifier):
    qc = session(QC)
    parameter = master_data["parameters"]["pH"]
    sample = create_sample(qc, create_point(master_data["admin"], parameter))
    instrument_issue(save_numeric(qc, sample["id"], parameter, identifier), "pH", "not registered")


def test_methanol_rejects_hplc_and_formaldehyde_rejects_gc(master_data):
    qc = session(QC)
    methanol = master_data["parameters"]["Methanol"]
    formaldehyde = master_data["parameters"]["Formaldehyde"]
    methanol_sample = create_sample(qc, create_point(master_data["admin"], methanol))
    formaldehyde_sample = create_sample(qc, create_point(master_data["admin"], formaldehyde))
    instrument_issue(
        save_numeric(qc, methanol_sample["id"], methanol, "HPLC-01"),
        "Methanol",
        "registered GC",
    )
    instrument_issue(
        save_numeric(qc, formaldehyde_sample["id"], formaldehyde, "GC-99"),
        "Formaldehyde",
        "registered HPLC",
    )


@pytest.mark.parametrize(
    ("active", "calibration_due", "service_due", "availability_status", "phrase"),
    [
        (False, "2030-01-01", "2030-01-01", "AVAILABLE", "inactive"),
        (True, "2025-01-01", "2030-01-01", "AVAILABLE", "overdue for calibration"),
        (True, "2030-01-01", "2025-01-01", "AVAILABLE", "overdue for service"),
        (True, "2030-01-01", "2030-01-01", "FAILED", "failed state"),
        (True, "2030-01-01", "2030-01-01", "UNAVAILABLE", "unavailable"),
    ],
)
def test_ineligible_ph_meter_is_rejected(
    master_data,
    active,
    calibration_due,
    service_due,
    availability_status,
    phrase,
):
    admin = master_data["admin"]
    code = f"PH-TEST-{uuid.uuid4().hex[:8]}"
    response = admin.post(
        f"{BASE}/instruments",
        json={
            "name": code,
            "instrument_code": code,
            "calibration_due": calibration_due,
            "service_due": service_due,
            "active": active,
            "category": "PH_METER",
            "availability_status": availability_status,
        },
        timeout=30,
    )
    assert response.status_code == 200, response.text
    qc = session(QC)
    parameter = master_data["parameters"]["pH"]
    sample = create_sample(qc, create_point(admin, parameter))
    instrument_issue(save_numeric(qc, sample["id"], parameter, code), "pH", phrase)


def test_required_instrument_omission_is_rejected(master_data):
    qc = session(QC)
    parameter = master_data["parameters"]["pH"]
    sample = create_sample(qc, create_point(master_data["admin"], parameter))
    instrument_issue(save_numeric(qc, sample["id"], parameter), "pH", "registered PH_METER")


def test_manual_parameter_stores_no_instrument_reference(master_data):
    qc = session(QC)
    parameter = master_data["parameters"]["COD"]
    sample = create_sample(qc, create_point(master_data["admin"], parameter))
    response = save_numeric(qc, sample["id"], parameter)
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["instrument_id"] is None
    assert result["instrument_traceability"]["state"] == "NOT_REQUIRED"


def test_manual_parameter_rejects_fabricated_instrument_reference(master_data):
    qc = session(QC)
    parameter = master_data["parameters"]["COD"]
    sample = create_sample(qc, create_point(master_data["admin"], parameter))
    instrument_issue(
        save_numeric(qc, sample["id"], parameter, "ID"),
        "COD",
        "No instrument is required",
    )


def test_historical_invalid_traceability_blocks_submit_approval_and_coa(master_data):
    qc = session(QC)
    qa = session(QA)
    parameter = master_data["parameters"]["pH"]
    sample = create_sample(qc, create_point(master_data["admin"], parameter))
    saved = save_numeric(qc, sample["id"], parameter, "PH-204")
    assert saved.status_code == 200, saved.text

    async def set_historical_invalid_pending_review():
        await db.samples.update_one(
            {"id": sample["id"]},
            {
                "$set": {
                    "results.0.instrument_id": "10",
                    "qa_status": "Pending Review",
                }
            },
        )

    asyncio.run(set_historical_invalid_pending_review())
    detail = qc.get(f"{BASE}/samples/{sample['id']}", timeout=30).json()
    assert detail["instrument_issues"][0]["parameter"] == "pH"
    instrument_issue(
        qc.post(f"{BASE}/samples/{sample['id']}/submit", json={"comment": "review"}, timeout=30),
        "pH",
        "not registered",
    )

    instrument_issue(
        qa.post(
            f"{BASE}/samples/{sample['id']}/decision/approve",
            json={"comment": "approval"},
            timeout=30,
        ),
        "pH",
        "not registered",
    )
    instrument_issue(
        qc.get(f"{BASE}/samples/{sample['id']}/coa", timeout=30),
        "pH",
        "not registered",
    )


def test_valid_traceability_keeps_the_sample_workflow_functional(master_data):
    qc = session(QC)
    qa = session(QA)
    parameter = master_data["parameters"]["pH"]
    sample = create_sample(qc, create_point(master_data["admin"], parameter))
    assert save_numeric(qc, sample["id"], parameter, "PH-204").status_code == 200
    submitted = qc.post(
        f"{BASE}/samples/{sample['id']}/submit",
        json={"comment": "ready"},
        timeout=30,
    )
    assert submitted.status_code == 200, submitted.text
    approved = qa.post(
        f"{BASE}/samples/{sample['id']}/decision/approve",
        json={"comment": "approved"},
        timeout=30,
    )
    assert approved.status_code == 200, approved.text
    coa = qc.get(f"{BASE}/samples/{sample['id']}/coa", timeout=30)
    assert coa.status_code == 200, coa.text