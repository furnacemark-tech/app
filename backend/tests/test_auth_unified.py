"""Unified authentication tests for batch endpoints.

Proves that every batch route now uses the single authoritative auth path:
  - valid active session can access authorised batch routes
  - revoked/logout session cannot access or mutate any batch endpoint
  - must_change_password users cannot access batch routes (except exempt)
  - refresh tokens cannot be used where access tokens are required
  - inactive users are rejected
  - QC/QA/admin role restrictions continue to work
  - existing OOS/disposition functionality remains unchanged
"""
import os
import time
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

UA = "Mozilla/5.0 (X11; Linux x86_64) pytest-auth-unified"


def _clear_lockouts():
    run_db(lambda: db.login_attempts.delete_many({}))


@pytest.fixture(autouse=True)
def no_lockout():
    _clear_lockouts()
    yield
    _clear_lockouts()


def login(creds):
    r = requests.post(f"{BASE}/auth/login", json=creds, timeout=30, headers={"User-Agent": UA})
    return r


def session_with_token(creds):
    r = login(creds)
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "User-Agent": UA})
    s.cookies.update(r.cookies)
    return s, token


def unique_email(prefix="auth"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}@lims.test"


def create_isolated_account(admin_session, role="qc"):
    """Create a user with a known, already-changed password for isolated tests."""
    email = unique_email("iso")
    temp = f"Temp-{uuid.uuid4().hex[:12]}"
    created = admin_session.post(f"{BASE}/users", json={
        "email": email, "password": temp, "name": "Isolated",
        "initials": "IS", "role": role}, timeout=30)
    assert created.status_code == 200, created.text
    first = login({"email": email, "password": temp})
    assert first.status_code == 200
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {first.json()['access_token']}", "User-Agent": UA})
    password = f"Live-{uuid.uuid4().hex[:12]}"
    assert s.post(f"{BASE}/auth/change-password", json={
        "current_password": temp, "new_password": password}, timeout=30).status_code == 200
    return {"id": created.json()["id"], "email": email, "password": password, "role": role}


def _product_for_batch(admin_session):
    products = admin_session.get(f"{BASE}/products", timeout=30).json()
    return next(p for p in products if p["active_version"]["sales_mode"] == "multi")


def _instruments(admin_session):
    return admin_session.get(f"{BASE}/instruments", timeout=30).json()


def _params(admin_session):
    return {p["name"]: p for p in admin_session.get(f"{BASE}/parameters", timeout=30).json()}


def _create_draft_batch(qc_session, admin_session):
    prod = _product_for_batch(admin_session)
    bn = f"AU-{uuid.uuid4().hex[:8].upper()}"
    r = qc_session.post(f"{BASE}/batches", json={
        "product_id": prod["id"], "batch_number": bn,
        "production_date": "2026-01-15"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"], bn


# ---------------- active session access ----------------
class TestActiveSessionAccess:
    def test_qc_can_list_batches(self):
        s, _ = session_with_token(QC)
        r = s.get(f"{BASE}/batches", timeout=30)
        assert r.status_code == 200

    def test_qa_can_access_queues(self):
        s, _ = session_with_token(QA)
        r = s.get(f"{BASE}/qa/queues", timeout=30)
        assert r.status_code == 200

    def test_admin_can_list_products(self):
        s, _ = session_with_token(ADMIN)
        r = s.get(f"{BASE}/products", timeout=30)
        assert r.status_code == 200

    def test_qc_can_create_batch(self):
        s, _ = session_with_token(QC)
        admin_s, _ = session_with_token(ADMIN)
        bid, bn = _create_draft_batch(s, admin_s)
        assert bid


# ---------------- revoked session ----------------
class TestRevokedSession:
    def test_logout_blocks_batch_access(self):
        s, token = session_with_token(QC)
        assert s.get(f"{BASE}/batches", timeout=30).status_code == 200
        assert s.post(f"{BASE}/auth/logout", timeout=30).status_code == 200
        # same bearer token must now be rejected on a batch route
        assert s.get(f"{BASE}/batches", timeout=30).status_code == 401
        assert s.get(f"{BASE}/products", timeout=30).status_code == 401

    def test_revoked_session_cannot_mutate_batch(self):
        admin_s, _ = session_with_token(ADMIN)
        qc_s, _ = session_with_token(QC)
        bid, bn = _create_draft_batch(qc_s, admin_s)
        # logout
        assert qc_s.post(f"{BASE}/auth/logout", timeout=30).status_code == 200
        # attempt to enter results on the batch
        params = _params(admin_s)
        r = qc_s.post(f"{BASE}/batches/{bid}/results", json={
            "results": [{"parameter_id": params["pH"]["id"], "value_numeric": 7.0}]}, timeout=30)
        assert r.status_code == 401
        # attempt to submit
        assert qc_s.post(f"{BASE}/batches/{bid}/submit", json={"comment": "x"}, timeout=30).status_code == 401

    def test_revoked_session_cannot_access_batch_detail(self):
        admin_s, _ = session_with_token(ADMIN)
        qc_s, _ = session_with_token(QC)
        bid, bn = _create_draft_batch(qc_s, admin_s)
        assert qc_s.post(f"{BASE}/auth/logout", timeout=30).status_code == 200
        assert qc_s.get(f"{BASE}/batches/{bid}", timeout=30).status_code == 401
        assert qc_s.get(f"{BASE}/batches/{bid}/history", timeout=30).status_code == 401


# ---------------- must_change_password gate ----------------
class TestMustChangePasswordGate:
    def test_temp_password_user_cannot_access_batches(self):
        admin_s, _ = session_with_token(ADMIN)
        email = unique_email("gate")
        temp = f"Temp-{uuid.uuid4().hex[:12]}"
        created = admin_s.post(f"{BASE}/users", json={
            "email": email, "password": temp, "name": "Gate",
            "initials": "GT", "role": "qc"}, timeout=30)
        assert created.status_code == 200
        first = login({"email": email, "password": temp})
        assert first.status_code == 200
        token = first.json()["access_token"]
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {token}", "User-Agent": UA})
        # batch routes must be blocked with 403 temporary password
        assert s.get(f"{BASE}/batches", timeout=30).status_code == 403
        assert s.get(f"{BASE}/products", timeout=30).status_code == 403
        # exempt paths still work
        assert s.get(f"{BASE}/auth/me", timeout=30).status_code == 200

    def test_temp_password_user_cannot_create_batch(self):
        admin_s, _ = session_with_token(ADMIN)
        email = unique_email("gate2")
        temp = f"Temp-{uuid.uuid4().hex[:12]}"
        admin_s.post(f"{BASE}/users", json={
            "email": email, "password": temp, "name": "Gate2",
            "initials": "G2", "role": "qc"}, timeout=30)
        first = login({"email": email, "password": temp})
        token = first.json()["access_token"]
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {token}", "User-Agent": UA})
        prod = _product_for_batch(admin_s)
        r = s.post(f"{BASE}/batches", json={
            "product_id": prod["id"], "batch_number": f"GT-{uuid.uuid4().hex[:6]}",
            "production_date": "2026-01-15"}, timeout=30)
        assert r.status_code == 403


# ---------------- refresh token cannot be used as access ----------------
class TestRefreshTokenRejected:
    def test_refresh_token_rejected_on_batch_route(self):
        r = login(QC)
        assert r.status_code == 200
        refresh_cookie = r.cookies.get("refresh_token")
        assert refresh_cookie
        # decode the refresh token to use as Bearer
        import jwt as _jwt
        payload = _jwt.decode(refresh_cookie, os.environ["JWT_SECRET"], algorithms=["HS256"])
        assert payload["type"] == "refresh"
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {refresh_cookie}", "User-Agent": UA})
        assert s.get(f"{BASE}/batches", timeout=30).status_code == 401
        assert s.get(f"{BASE}/products", timeout=30).status_code == 401

    def test_refresh_token_rejected_on_disposition(self):
        admin_s, _ = session_with_token(ADMIN)
        qc_s, _ = session_with_token(QC)
        bid, bn = _create_draft_batch(qc_s, admin_s)
        r = login(QA)
        refresh_cookie = r.cookies.get("refresh_token")
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {refresh_cookie}", "User-Agent": UA})
        assert s.post(f"{BASE}/batches/{bid}/disposition/release-after-investigation",
                       json={"issue": "x", "investigation_conclusion": "x", "impact_assessment": "x",
                             "release_justification": "x", "evidence_references": ["x"],
                             "oos_reviewed_accepted_without_change": True}, timeout=30).status_code == 401


# ---------------- inactive users ----------------
class TestInactiveUser:
    def test_inactive_user_rejected_on_batches(self):
        admin_s, _ = session_with_token(ADMIN)
        account = create_isolated_account(admin_s, "qc")
        # login works while active
        r = login({"email": account["email"], "password": account["password"]})
        assert r.status_code == 200
        token = r.json()["access_token"]
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {token}", "User-Agent": UA})
        assert s.get(f"{BASE}/batches", timeout=30).status_code == 200
        # deactivate
        assert admin_s.patch(f"{BASE}/users/{account['id']}", json={"active": False}, timeout=30).status_code == 200
        # existing token now rejected on batch route (session revoked + user inactive)
        assert s.get(f"{BASE}/batches", timeout=30).status_code == 401
        assert s.get(f"{BASE}/products", timeout=30).status_code == 401

    def test_inactive_user_cannot_mutate_batch(self):
        admin_s, _ = session_with_token(ADMIN)
        qc_s, _ = session_with_token(QC)
        bid, bn = _create_draft_batch(qc_s, admin_s)
        account = create_isolated_account(admin_s, "qc")
        r = login({"email": account["email"], "password": account["password"]})
        token = r.json()["access_token"]
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {token}", "User-Agent": UA})
        admin_s.patch(f"{BASE}/users/{account['id']}", json={"active": False}, timeout=30)
        params = _params(admin_s)
        assert s.post(f"{BASE}/batches/{bid}/results", json={
            "results": [{"parameter_id": params["pH"]["id"], "value_numeric": 7.0}]}, timeout=30).status_code == 401


# ---------------- role restrictions ----------------
class TestRoleRestrictions:
    def test_qc_cannot_cancel_batch(self):
        admin_s, _ = session_with_token(ADMIN)
        qc_s, _ = session_with_token(QC)
        bid, bn = _create_draft_batch(qc_s, admin_s)
        r = qc_s.post(f"{BASE}/batches/{bid}/cancel", json={"reason": "x"}, timeout=30)
        assert r.status_code == 403

    def test_qc_cannot_amend_production_date(self):
        admin_s, _ = session_with_token(ADMIN)
        qc_s, _ = session_with_token(QC)
        bid, bn = _create_draft_batch(qc_s, admin_s)
        r = qc_s.post(f"{BASE}/batches/{bid}/production-date", json={
            "production_date": "2026-01-16", "reason": "x"}, timeout=30)
        assert r.status_code == 403

    def test_qc_cannot_use_disposition(self):
        admin_s, _ = session_with_token(ADMIN)
        qc_s, _ = session_with_token(QC)
        bid, bn = _create_draft_batch(qc_s, admin_s)
        r = qc_s.post(f"{BASE}/batches/{bid}/disposition/release-after-investigation",
                      json={"issue": "x", "investigation_conclusion": "x", "impact_assessment": "x",
                            "release_justification": "x", "evidence_references": ["x"],
                            "oos_reviewed_accepted_without_change": True}, timeout=30)
        assert r.status_code == 403

    def test_admin_cannot_use_disposition(self):
        admin_s, _ = session_with_token(ADMIN)
        qc_s, _ = session_with_token(QC)
        bid, bn = _create_draft_batch(qc_s, admin_s)
        r = admin_s.post(f"{BASE}/batches/{bid}/disposition/release-after-investigation",
                         json={"issue": "x", "investigation_conclusion": "x", "impact_assessment": "x",
                               "release_justification": "x", "evidence_references": ["x"],
                               "oos_reviewed_accepted_without_change": True}, timeout=30)
        assert r.status_code == 403

    def test_qa_cannot_create_customer(self):
        qa_s, _ = session_with_token(QA)
        r = qa_s.post(f"{BASE}/customers", json={"name": "x", "account_code": "x"}, timeout=30)
        assert r.status_code == 403

    def test_qa_can_access_qa_queues(self):
        qa_s, _ = session_with_token(QA)
        assert qa_s.get(f"{BASE}/qa/queues", timeout=30).status_code == 200


# ---------------- OOS/disposition unchanged ----------------
class TestOosDispositionUnchanged:
    def _make_held_mineral_batch(self, qc_s, admin_s):
        # create a mineral product with a tight spec
        mineral = admin_s.post(f"{BASE}/parameters", json={
            "name": f"MineralAU {uuid.uuid4().hex[:6]}", "units": "mg/g", "method": "2.M.20",
            "value_type": "numeric", "options": []}, timeout=30).json()
        prod = admin_s.post(f"{BASE}/products", json={
            "name": f"MineralAU {uuid.uuid4().hex[:6]}", "code": "MAU", "batch_type": "syrup",
            "shelf_life_required": True, "shelf_life_days": 365, "sales_mode": "multi",
            "limits": [{"parameter_id": mineral["id"], "lower_limit": 9.8, "upper_limit": 14.0,
                        "expected_text": None}],
            "reason": "mineral spec"}, timeout=30).json()
        instruments = _instruments(admin_s)
        hplc = next(i for i in instruments if i["in_calibration"] and i["in_service"])
        bn = f"AU-MIN-{uuid.uuid4().hex[:6].upper()}"
        r = qc_s.post(f"{BASE}/batches", json={
            "product_id": prod["id"], "batch_number": bn,
            "production_date": "2026-01-15"}, timeout=30)
        assert r.status_code == 200
        bid = r.json()["id"]
        qc_s.post(f"{BASE}/batches/{bid}/results", json={
            "instrument_id": hplc["id"],
            "results": [{"parameter_id": mineral["id"], "value_numeric": 9.6}]}, timeout=30)
        # qc release -> held
        blocked = qc_s.post(f"{BASE}/batches/{bid}/release", json={}, timeout=30)
        assert blocked.status_code == 400
        return bid, mineral["id"]

    def test_qc_cannot_release_oos_batch(self):
        admin_s, _ = session_with_token(ADMIN)
        qc_s, _ = session_with_token(QC)
        bid, pid = self._make_held_mineral_batch(qc_s, admin_s)
        # still on hold
        b = qc_s.get(f"{BASE}/batches/{bid}", timeout=30).json()
        assert b["status"] == "ON_HOLD"
        assert b["overall_result"] == "FAIL"

    def test_disposition_preserves_fail_and_releases(self):
        admin_s, _ = session_with_token(ADMIN)
        qc_s, _ = session_with_token(QC)
        qa_s, _ = session_with_token(QA)
        bid, pid = self._make_held_mineral_batch(qc_s, admin_s)
        r = qa_s.post(f"{BASE}/batches/{bid}/disposition/release-after-investigation", json={
            "issue": "Mineral below spec",
            "investigation_conclusion": "Confirmed true value",
            "impact_assessment": "Nutritional specialist assessed no impact",
            "release_justification": "Fit for intended use",
            "corrective_action": "Tighten in-process check",
            "evidence_references": ["NUTR-1", "LAB-2"],
            "oos_reviewed_accepted_without_change": True,
        }, timeout=30)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["status"] == "RELEASED"
        assert b["release_basis"] == "RELEASE_AFTER_INVESTIGATION"
        assert b["overall_result"] == "FAIL"
        result = next(x for x in b["results"] if x["parameter_id"] == pid)
        assert result["status"] == "FAIL"
        assert result["value_numeric"] == 9.6
        assert b["active_disposition"]["outcome"] == "RELEASE_AFTER_INVESTIGATION"

    def test_plain_qa_release_refused_for_oos(self):
        admin_s, _ = session_with_token(ADMIN)
        qc_s, _ = session_with_token(QC)
        qa_s, _ = session_with_token(QA)
        bid, pid = self._make_held_mineral_batch(qc_s, admin_s)
        r = qa_s.post(f"{BASE}/batches/{bid}/qa-decision/release", json={
            "issue": "OOS", "root_cause": "c", "impact": "i", "corrective_action": "a"}, timeout=30)
        assert r.status_code == 400
        assert "RELEASE_AFTER_INVESTIGATION" in r.json()["detail"]

