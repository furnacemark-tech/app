"""LIMS backend API tests"""
import os
import time
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from database import db
from conftest import run_db
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://audit-data-lab.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@lims.local", "password": "Admin@123"}
QA = {"email": "qa@lims.local", "password": "Qa@12345"}
QC = {"email": "qc@lims.local", "password": "Qc@12345"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    return s, data


@pytest.fixture(scope="session")
def admin_session():
    s, _ = _login(ADMIN)
    return s


@pytest.fixture(scope="session")
def qa_session():
    s, _ = _login(QA)
    return s


@pytest.fixture(scope="session")
def qc_session():
    s, _ = _login(QC)
    return s


# ---------------- AUTH ----------------
class TestAuth:
    def test_login_admin(self):
        r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["user"]["role"] == "admin"
        assert data.get("access_token")

    def test_login_qa(self):
        r = requests.post(f"{API}/auth/login", json=QA, timeout=30)
        assert r.status_code == 200 and r.json()["user"]["role"] == "qa"

    def test_login_qc(self):
        r = requests.post(f"{API}/auth/login", json=QC, timeout=30)
        assert r.status_code == 200 and r.json()["user"]["role"] == "qc"

    def test_login_wrong_password(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": "admin@lims.local", "password": "wrong"}, timeout=30)
        assert r.status_code == 401

    def test_me_requires_auth(self):
        r = requests.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401

    def test_me_with_token(self, admin_session):
        r = admin_session.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN["email"]


# ---------------- ROLE GATING ----------------
class TestRoles:
    def test_qc_cannot_list_users(self, qc_session):
        r = qc_session.get(f"{API}/users", timeout=30)
        assert r.status_code == 403

    def test_qa_cannot_list_users(self, qa_session):
        r = qa_session.get(f"{API}/users", timeout=30)
        assert r.status_code == 403

    def test_admin_lists_users(self, admin_session):
        r = admin_session.get(f"{API}/users", timeout=30)
        assert r.status_code == 200
        assert len(r.json()) >= 3


# ---------------- SEEDED DATA ----------------
class TestSeed:
    def test_sample_points_seeded(self, qc_session):
        r = qc_session.get(f"{API}/sample-points", timeout=30)
        assert r.status_code == 200
        names = {p["name"] for p in r.json()}
        for n in ["Final Effluent", "Lower Lagoon", "Aerator", "W1", "Culvert", "Down River"]:
            assert n in names, f"missing {n}"

    def test_parameters_seeded(self, qc_session):
        r = qc_session.get(f"{API}/parameters", timeout=30)
        assert r.status_code == 200
        names = {p["name"] for p in r.json()}
        assert {"pH", "COD", "Ammonia", "Appearance"}.issubset(names)

    def test_specifications_seeded(self, qc_session):
        r = qc_session.get(f"{API}/specifications", timeout=30)
        assert r.status_code == 200
        assert len(r.json()) > 0


# ---------------- FULL SAMPLE WORKFLOW ----------------
class TestWorkflow:
    @pytest.fixture(scope="class")
    def context(self, qc_session, qa_session, admin_session):
        pts = qc_session.get(f"{API}/sample-points").json()
        fe = next(p for p in pts if p["name"] == "Final Effluent")
        params = {p["name"]: p for p in qc_session.get(f"{API}/parameters").json()}
        specs = qc_session.get(f"{API}/specifications", params={"sample_point_id": fe["id"]}).json()
        gc_code = f"GC-WORKFLOW-{uuid.uuid4().hex[:8]}"
        instrument = admin_session.post(f"{API}/instruments", json={
            "name": gc_code,
            "instrument_code": gc_code,
            "calibration_due": "2030-01-01",
            "service_due": "2030-01-01",
            "active": True,
            "category": "GC",
            "availability_status": "AVAILABLE",
        })
        assert instrument.status_code == 200, instrument.text
        context = {
            "fe": fe,
            "params": params,
            "specs": specs,
            "qc": qc_session,
            "qa": qa_session,
            "valid_gc_code": gc_code,
        }
        yield context

        run_db(lambda: db.instruments.delete_one({"instrument_code": gc_code}))

    def test_qc_creates_sample(self, context):
        r = context["qc"].post(f"{API}/samples", json={
            "sample_point_id": context["fe"]["id"],
            "sample_date": "2026-01-15",
            "sample_time": "10:00",
            "notes": "TEST_workflow"
        })
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["record_id"].startswith("REC-20260115-")
        assert s["qa_status"] == "Not Submitted"
        pytest.sample_id = s["id"]

    def test_qc_saves_results_pass_warn_fail(self, context):
        sid = pytest.sample_id
        params = context["params"]
        # pH 7 -> PASS (spec 5-9), COD 750 -> WARN (>=0.9*800=720), Ammonia 100 -> FAIL (>60.7), Appearance match -> PASS
        # All seven Final Effluent required parameters must be entered so the sample is COMPLETE;
        # Methanol/Formaldehyde/Suspended Solids are set to PASS values to keep the overall_result
        # driven by the Ammonia FAIL as the pre-existing assertions expect.
        results = [
            {
                "parameter_id": params["pH"]["id"],
                "value_numeric": 7.0,
                "instrument_id": "PH-204",
            },
            {"parameter_id": params["COD"]["id"], "value_numeric": 750.0},
            {"parameter_id": params["Ammonia"]["id"], "value_numeric": 100.0},
            {"parameter_id": params["Appearance"]["id"], "value_text": "Clear Colourless"},
            {
                "parameter_id": params["Methanol"]["id"],
                "value_numeric": 5.0,
                "instrument_id": context["valid_gc_code"],
            },
            {
                "parameter_id": params["Formaldehyde"]["id"],
                "value_numeric": 1.0,
                "instrument_id": "HPLC-01",
            },
            {"parameter_id": params["Suspended Solids"]["id"], "value_numeric": 100.0},
        ]
        r = context["qc"].post(f"{API}/samples/{sid}/results", json={"results": results})
        assert r.status_code == 200, r.text
        sample = r.json()
        by_name = {x["parameter_name"]: x for x in sample["results"]}
        assert by_name["pH"]["status"] == "PASS"
        assert by_name["COD"]["status"] == "WARN"
        assert by_name["Ammonia"]["status"] == "FAIL"
        assert by_name["Appearance"]["status"] == "PASS"
        assert sample["overall_result"] == "FAIL"

    def test_appearance_mismatch_fails(self, context):
        sid = pytest.sample_id
        r = context["qc"].post(f"{API}/samples/{sid}/results", json={"results": [
            {"parameter_id": context["params"]["Appearance"]["id"], "value_text": "Turbid",
             "comment": "revise"}
        ]})
        assert r.status_code == 200
        by_name = {x["parameter_name"]: x for x in r.json()["results"]}
        assert by_name["Appearance"]["status"] == "FAIL"
        # revision must have incremented
        assert by_name["Appearance"]["revision"] >= 2

    def test_qc_cannot_approve(self, context):
        sid = pytest.sample_id
        # submit for review first
        r = context["qc"].post(f"{API}/samples/{sid}/submit", json={"comment": "please review"})
        assert r.status_code == 200
        assert r.json()["qa_status"] == "Pending Review"
        # QC tries to approve
        r2 = context["qc"].post(f"{API}/samples/{sid}/decision/approve", json={"comment": ""})
        assert r2.status_code == 403

    def test_qa_reject_requires_comment(self, context):
        sid = pytest.sample_id
        r = context["qa"].post(f"{API}/samples/{sid}/decision/reject", json={"comment": ""})
        assert r.status_code == 400

    def test_qa_reject_with_comment_creates_oos(self, context):
        sid = pytest.sample_id
        r = context["qa"].post(f"{API}/samples/{sid}/decision/reject",
                               json={"comment": "Ammonia OOS"})
        assert r.status_code == 200
        assert r.json()["qa_status"] == "Requires Investigation"
        oos = context["qa"].get(f"{API}/oos-log").json()
        assert any(o["sample_id"] == sid for o in oos)

    def test_resubmit_and_approve_locks(self, context):
        sid = pytest.sample_id
        # QC re-submits (already has results)
        r = context["qc"].post(f"{API}/samples/{sid}/submit", json={"comment": "resubmit"})
        assert r.status_code == 200
        # QA approves
        r2 = context["qa"].post(f"{API}/samples/{sid}/decision/approve", json={"comment": "ok"})
        assert r2.status_code == 200
        assert r2.json()["qa_status"] == "Approved"
        # Locked - QC cannot change results
        r3 = context["qc"].post(f"{API}/samples/{sid}/results", json={"results": [
            {"parameter_id": context["params"]["pH"]["id"], "value_numeric": 8.0}
        ]})
        assert r3.status_code == 400

    def test_coa_export(self, context):
        sid = pytest.sample_id
        r = context["qc"].get(f"{API}/samples/{sid}/coa")
        assert r.status_code == 200
        j = r.json()
        assert j["sample"]["id"] == sid
        assert "specifications" in j


# ---------------- SPECIFICATIONS ----------------
class TestSpecs:
    def test_qc_cannot_edit_spec(self, qc_session):
        specs = qc_session.get(f"{API}/specifications").json()
        s = specs[0]
        r = qc_session.put(f"{API}/specifications/{s['id']}", json={
            "sample_point_id": s["sample_point_id"], "parameter_id": s["parameter_id"],
            "lower_limit": s.get("lower_limit"), "upper_limit": s.get("upper_limit"),
            "expected_text": s.get("expected_text"), "active": True})
        assert r.status_code == 403

    def test_qa_edits_spec_increments_version(self, qa_session):
        specs = qa_session.get(f"{API}/specifications").json()
        s = next(x for x in specs if x.get("upper_limit") is not None)
        original_version = s.get("version", 1)
        r = qa_session.put(f"{API}/specifications/{s['id']}", json={
            "sample_point_id": s["sample_point_id"], "parameter_id": s["parameter_id"],
            "lower_limit": s.get("lower_limit"), "upper_limit": s["upper_limit"],
            "expected_text": s.get("expected_text"), "active": True})
        assert r.status_code == 200
        assert r.json()["version"] == original_version + 1


# ---------------- AUDIT TRAIL ----------------
class TestAudit:
    def test_audit_has_login_and_workflow_actions(self, admin_session):
        r = admin_session.get(f"{API}/audit-trail", params={"limit": 500})
        assert r.status_code == 200
        actions = {a["action"] for a in r.json()}
        # LOGIN and workflow actions should exist from prior tests
        assert "LOGIN" in actions
        for expected in ["CREATE", "ENTER_RESULT", "SUBMIT_FOR_REVIEW", "QA_APPROVE", "QA_REJECT", "EXPORT_COA"]:
            assert expected in actions, f"missing audit action {expected} (have: {actions})"

    def test_audit_filter_by_action(self, admin_session):
        r = admin_session.get(f"{API}/audit-trail", params={"action": "LOGIN"})
        assert r.status_code == 200
        assert all(a["action"] == "LOGIN" for a in r.json())

    def test_audit_filter_by_email(self, admin_session):
        r = admin_session.get(f"{API}/audit-trail", params={"user_email": QA["email"]})
        assert r.status_code == 200
        for a in r.json():
            assert a["user_email"] == QA["email"]

    def test_update_result_audit_has_before_after(self, admin_session):
        r = admin_session.get(f"{API}/audit-trail", params={"action": "UPDATE_RESULT"})
        assert r.status_code == 200
        entries = r.json()
        assert len(entries) > 0
        e = entries[0]
        assert e.get("before") is not None and e.get("after") is not None


# ---------------- USER MANAGEMENT ----------------
class TestUserManagement:
    _created_id = None
    _created_email = f"test_user_{int(time.time())}@lims.local"

    def test_password_min_length_enforced(self, admin_session):
        r = admin_session.post(f"{API}/users", json={
            "email": f"short_{int(time.time())}@lims.local", "password": "short",
            "name": "Short", "initials": "SH", "role": "qc"})
        assert r.status_code == 400

    def test_create_qc_user(self, admin_session):
        r = admin_session.post(f"{API}/users", json={
            "email": TestUserManagement._created_email, "password": "Test@1234",
            "name": "Test QC", "initials": "TQ", "role": "qc"})
        assert r.status_code == 200, r.text
        TestUserManagement._created_id = r.json()["id"]

    def test_new_user_can_login(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": TestUserManagement._created_email, "password": "Test@1234"})
        assert r.status_code == 200

    def test_change_role(self, admin_session):
        r = admin_session.patch(f"{API}/users/{TestUserManagement._created_id}", json={"role": "qa"})
        assert r.status_code == 200
        assert r.json()["role"] == "qa"

    def test_deactivate_blocks_login(self, admin_session):
        r = admin_session.patch(f"{API}/users/{TestUserManagement._created_id}", json={"active": False})
        assert r.status_code == 200
        r2 = requests.post(f"{API}/auth/login",
                           json={"email": TestUserManagement._created_email, "password": "Test@1234"})
        assert r2.status_code in (401, 403)


# ---------------- DASHBOARD ----------------
class TestDashboard:
    def test_dashboard_admin(self, admin_session):
        r = admin_session.get(f"{API}/dashboard")
        assert r.status_code == 200
        d = r.json()
        for k in ["total_samples", "pending_review", "approved", "recent_samples"]:
            assert k in d

    def test_dashboard_qc(self, qc_session):
        r = qc_session.get(f"{API}/dashboard")
        assert r.status_code == 200
