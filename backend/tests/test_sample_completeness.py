"""Regression tests for the REC-20260903-0003 defect.

Ordinary release must not be possible while required-spec results are still
missing. Covers overall status, submit-for-QA, QA approve, and CoA gates.
"""
import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

from conftest import run_db
from database import db

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / "frontend" / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env")

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"email": "admin@lims.local", "password": "Admin@123"}
QA = {"email": "qa@lims.local", "password": "Qa@12345"}
QC = {"email": "qc@lims.local", "password": "Qc@12345"}

UA = "pytest-sample-completeness"


def _clear_lockouts():
    run_db(lambda: db.login_attempts.delete_many({}))


@pytest.fixture(autouse=True)
def no_lockout():
    _clear_lockouts()
    yield
    _clear_lockouts()


def _session(creds):
    r = requests.post(f"{BASE}/auth/login", json=creds, timeout=30, headers={"User-Agent": UA})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "User-Agent": UA})
    return s


@pytest.fixture(scope="module")
def sample_point_and_params():
    """A dedicated sample point with two mandatory numeric parameters."""
    admin = _session(ADMIN)
    tag = uuid.uuid4().hex[:6]
    sp = admin.post(f"{BASE}/sample-points",
                    json={"name": f"SC-{tag}", "description": "completeness test"},
                    timeout=30).json()
    p1 = admin.post(f"{BASE}/parameters",
                    json={"name": f"P1-{tag}", "units": "mg/L", "method": "T.1",
                          "value_type": "numeric"}, timeout=30).json()
    p2 = admin.post(f"{BASE}/parameters",
                    json={"name": f"P2-{tag}", "units": "mg/L", "method": "T.2",
                          "value_type": "numeric"}, timeout=30).json()
    for pid, hi in ((p1["id"], 10.0), (p2["id"], 20.0)):
        admin.post(f"{BASE}/specifications", json={
            "sample_point_id": sp["id"], "parameter_id": pid,
            "lower_limit": 0.0, "upper_limit": hi, "expected_text": None,
            "active": True}, timeout=30)
    return {"sp": sp, "p1": p1, "p2": p2}


def _new_sample(qc, sp_id):
    return qc.post(f"{BASE}/samples", json={
        "sample_point_id": sp_id, "sample_date": "2026-02-01",
        "sample_time": "10:00", "analyst_initials": "QC",
        "notes": "sc"}, timeout=30).json()


def _enter(qc, sid, results):
    return qc.post(f"{BASE}/samples/{sid}/results",
                   json={"results": results}, timeout=30)


class TestIncompleteBlockedOnSubmit:
    def test_partial_results_report_pending_overall(self, sample_point_and_params):
        f = sample_point_and_params
        qc = _session(QC)
        s = _new_sample(qc, f["sp"]["id"])
        r = _enter(qc, s["id"],
                   [{"parameter_id": f["p1"]["id"], "value_numeric": 5.0}])
        assert r.status_code == 200
        body = r.json()
        assert body["overall_result"] == "PENDING", body
        assert body["status"] == "IN_PROGRESS"

    def test_submit_rejected_with_outstanding_names(self, sample_point_and_params):
        f = sample_point_and_params
        qc = _session(QC)
        s = _new_sample(qc, f["sp"]["id"])
        _enter(qc, s["id"],
               [{"parameter_id": f["p1"]["id"], "value_numeric": 5.0}])
        r = qc.post(f"{BASE}/samples/{s['id']}/submit",
                    json={"comment": "please"}, timeout=30)
        assert r.status_code == 422, r.text
        detail = r.json()["detail"]
        assert f["p2"]["name"] in detail["outstanding_parameters"]
        assert f["p1"]["name"] not in detail["outstanding_parameters"]


class TestIncompleteBlockedOnApprove:
    def test_crafted_pending_review_incomplete_approve_rejected(self, sample_point_and_params):
        """Simulate a legacy/crafted sample already at PENDING REVIEW while
        incomplete — approve must still refuse."""
        f = sample_point_and_params
        qc = _session(QC)
        qa = _session(QA)
        s = _new_sample(qc, f["sp"]["id"])
        _enter(qc, s["id"],
               [{"parameter_id": f["p1"]["id"], "value_numeric": 5.0}])

        run_db(
            lambda: db.samples.update_one(
                {"id": s["id"]},
                {"$set": {"qa_status": "Pending Review"}},
            )
        )
        r = qa.post(f"{BASE}/samples/{s['id']}/decision/approve",
                    json={"comment": "ok"}, timeout=30)
        assert r.status_code == 422, r.text
        assert f["p2"]["name"] in r.json()["detail"]["outstanding_parameters"]


class TestIncompleteBlockedOnCoA:
    def test_incomplete_coa_rejected(self, sample_point_and_params):
        f = sample_point_and_params
        qc = _session(QC)
        s = _new_sample(qc, f["sp"]["id"])
        _enter(qc, s["id"],
               [{"parameter_id": f["p1"]["id"], "value_numeric": 5.0}])
        r = qc.get(f"{BASE}/samples/{s['id']}/coa", timeout=30)
        assert r.status_code == 422, r.text
        assert f["p2"]["name"] in r.json()["detail"]["outstanding_parameters"]

    def test_incomplete_coa_error_identifies_each_outstanding_parameter(
        self,
        sample_point_and_params,
    ):
        f = sample_point_and_params
        qc = _session(QC)
        s = _new_sample(qc, f["sp"]["id"])
        r = qc.get(f"{BASE}/samples/{s['id']}/coa", timeout=30)
        assert r.status_code == 422, r.text
        detail = r.json()["detail"]
        assert detail["message"] == "Cannot issue an ordinary CoA: required results are missing"
        assert set(detail["outstanding_parameters"]) == {f["p1"]["name"], f["p2"]["name"]}


class TestCompleteAllPass:
    def test_complete_all_pass_submit_and_approve(self, sample_point_and_params):
        f = sample_point_and_params
        qc = _session(QC)
        qa = _session(QA)
        s = _new_sample(qc, f["sp"]["id"])
        r = _enter(qc, s["id"], [
            {"parameter_id": f["p1"]["id"], "value_numeric": 5.0},
            {"parameter_id": f["p2"]["id"], "value_numeric": 10.0},
        ])
        assert r.status_code == 200
        body = r.json()
        assert body["overall_result"] == "PASS", body
        assert body["status"] == "COMPLETE"
        sub = qc.post(f"{BASE}/samples/{s['id']}/submit",
                      json={"comment": "ready"}, timeout=30)
        assert sub.status_code == 200, sub.text
        appr = qa.post(f"{BASE}/samples/{s['id']}/decision/approve",
                       json={"comment": "signed"}, timeout=30)
        assert appr.status_code == 200, appr.text
        assert appr.json()["qa_status"] == "Approved"
        coa = qc.get(f"{BASE}/samples/{s['id']}/coa", timeout=30)
        assert coa.status_code == 200


class TestFailPathUnchanged:
    def test_failed_result_path_still_works(self, sample_point_and_params):
        f = sample_point_and_params
        qc = _session(QC)
        qa = _session(QA)
        s = _new_sample(qc, f["sp"]["id"])
        # p1 fails (upper limit 10), p2 passes
        r = _enter(qc, s["id"], [
            {"parameter_id": f["p1"]["id"], "value_numeric": 999.0},
            {"parameter_id": f["p2"]["id"], "value_numeric": 5.0},
        ])
        assert r.status_code == 200
        body = r.json()
        assert body["overall_result"] == "FAIL"
        # Submit is still allowed because sample is complete
        sub = qc.post(f"{BASE}/samples/{s['id']}/submit",
                      json={"comment": "review"}, timeout=30)
        assert sub.status_code == 200
        # QA can reject; sample must land in the OOS log
        rej = qa.post(f"{BASE}/samples/{s['id']}/decision/reject",
                      json={"comment": "out of spec"}, timeout=30)
        assert rej.status_code == 200
        assert rej.json()["qa_status"] == "Requires Investigation"
