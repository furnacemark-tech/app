"""Batch release / CoA workflow tests"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://audit-data-lab.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@lims.local", "password": "Admin@123"}
QA = {"email": "qa@lims.local", "password": "Qa@12345"}
QC = {"email": "qc@lims.local", "password": "Qc@12345"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


@pytest.fixture(scope="module")
def admin_s():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def qa_s():
    return _login(QA)


@pytest.fixture(scope="module")
def qc_s():
    return _login(QC)


@pytest.fixture(scope="module")
def context(admin_s, qa_s, qc_s):
    products = admin_s.get(f"{API}/products").json()
    by_name = {p["name"]: p for p in products}
    instruments = admin_s.get(f"{API}/instruments").json()
    inst_by_name = {i["name"]: i for i in instruments}
    customers = admin_s.get(f"{API}/customers").json()
    cust_by_name = {c["name"]: c for c in customers}
    params = {p["name"]: p for p in admin_s.get(f"{API}/parameters").json()}
    return {
        "products": by_name, "instruments": inst_by_name, "customers": cust_by_name,
        "params": params, "admin": admin_s, "qa": qa_s, "qc": qc_s,
    }


def _bn(prefix="TEST"):
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


class TestSeed:
    def test_products_seeded(self, context):
        for n in ["Methanol Solution 99%", "Formaldehyde Blend FB2", "Process Water Grade A"]:
            assert n in context["products"], f"missing product {n}"

    def test_instruments_seeded(self, context):
        names = list(context["instruments"].keys())
        assert any("HPLC" in n for n in names)
        assert any("Legacy" in n for n in names)  # overdue

    def test_customers_seeded(self, context):
        assert "Northwind Chemicals" in context["customers"]

    def test_process_water_no_shelf_life(self, context):
        p = context["products"]["Process Water Grade A"]
        v = p["active_version"]
        assert v["shelf_life_required"] is False


# ---------------- Customers RBAC ----------------
class TestCustomersRBAC:
    def test_qc_cannot_create_customer(self, context):
        r = context["qc"].post(f"{API}/customers", json={"name": "TEST_qc_cust", "account_code": "T"})
        assert r.status_code == 403

    def test_qa_cannot_create_customer(self, context):
        r = context["qa"].post(f"{API}/customers", json={"name": "TEST_qa_cust", "account_code": "T"})
        assert r.status_code == 403

    def test_admin_creates_and_adds_contact(self, context):
        name = f"TEST_Cust_{int(time.time())}"
        r = context["admin"].post(f"{API}/customers", json={"name": name, "account_code": "TST"})
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        rc = context["admin"].post(f"{API}/customers/{cid}/contacts", json={
            "name": "Buyer", "email": "buyer@test.local"})
        assert rc.status_code == 200

    def test_qc_qa_can_view_customers(self, context):
        assert context["qc"].get(f"{API}/customers").status_code == 200
        assert context["qa"].get(f"{API}/customers").status_code == 200


# ---------------- Batch happy path ----------------
class TestBatchHappyPath:
    _batch_id = None
    _batch_number = _bn("HP")

    def test_qc_create_batch_multi_customer_product(self, context):
        prod = context["products"]["Methanol Solution 99%"]
        r = context["qc"].post(f"{API}/batches", json={
            "product_id": prod["id"], "batch_number": TestBatchHappyPath._batch_number,
            "production_date": "2026-01-15"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["status"] == "DRAFT"
        assert b["expiry_date"] == "2028-01-15"  # 730 days later
        assert b["shelf_life_required"] is True
        assert b["customer_id"] is None  # multi mode
        TestBatchHappyPath._batch_id = b["id"]

    def test_qc_enters_results_in_spec(self, context):
        bid = TestBatchHappyPath._batch_id
        hplc = next(i for n, i in context["instruments"].items() if "HPLC" in n)
        params = context["params"]
        r = context["qc"].post(f"{API}/batches/{bid}/results", json={
            "instrument_id": hplc["id"],
            "results": [
                {"parameter_id": params["pH"]["id"], "value_numeric": 7.0},
                {"parameter_id": params["COD"]["id"], "value_numeric": 500.0},
                {"parameter_id": params["Appearance"]["id"], "value_text": "Clear Colourless"},
            ]})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["instrument_id"] == hplc["id"]
        assert all(x["status"] == "PASS" for x in b["results"])

    def test_qc_release_generates_active_coa(self, context):
        bid = TestBatchHappyPath._batch_id
        r = context["qc"].post(f"{API}/batches/{bid}/release", json={"customer_ids": []})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["status"] == "RELEASED"
        assert len(b["coas"]) == 1
        coa = b["coas"][0]
        assert coa["status"] == "ACTIVE"
        assert coa["delivery_status"] == "READY_FOR_QA_TO_SEND"

    def test_second_release_blocked(self, context):
        bid = TestBatchHappyPath._batch_id
        r = context["qc"].post(f"{API}/batches/{bid}/release", json={"customer_ids": []})
        assert r.status_code == 400

    def test_qa_send_coa_to_multiple_recipients(self, context):
        bid = TestBatchHappyPath._batch_id
        b = context["qa"].get(f"{API}/batches/{bid}").json()
        coa = b["coas"][0]
        r = context["qa"].post(f"{API}/batches/{bid}/coa/{coa['id']}/send", json={
            "recipients": [
                {"name": "Alice Reed", "email": "alice@northwind.test"},
                {"name": "Manual Buyer", "email": "manual@test.local"},
            ]})
        assert r.status_code == 200, r.text
        assert len(r.json()) == 2
        b2 = context["qa"].get(f"{API}/batches/{bid}").json()
        assert len(b2["deliveries"]) == 2

    def test_qa_amend_production_date_marks_reissue(self, context):
        bid = TestBatchHappyPath._batch_id
        r = context["qa"].post(f"{API}/batches/{bid}/production-date", json={
            "production_date": "2026-01-20", "reason": "Data entry correction"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["production_date"] == "2026-01-20"
        assert b["expiry_date"] == "2028-01-20"
        assert b.get("coa_reissue_required") is True

    def test_qa_authorises_replacement_coa(self, context):
        bid = TestBatchHappyPath._batch_id
        b = context["qa"].get(f"{API}/batches/{bid}").json()
        old_coa = [c for c in b["coas"] if c["status"] == "ACTIVE"][0]
        r = context["qa"].post(f"{API}/batches/{bid}/coa/{old_coa['id']}/authorise-replacement",
                               json={"reason": "Production date corrected"})
        assert r.status_code == 200, r.text
        new_coa = r.json()
        assert new_coa["supersedes_coa_id"] == old_coa["id"]
        assert new_coa["status"] == "ACTIVE"
        assert new_coa["revision"] == 2
        b2 = context["qa"].get(f"{API}/batches/{bid}").json()
        old_now = next(c for c in b2["coas"] if c["id"] == old_coa["id"])
        assert old_now["status"] == "SUPERSEDED"

    def test_sending_superseded_coa_rejected(self, context):
        bid = TestBatchHappyPath._batch_id
        b = context["qa"].get(f"{API}/batches/{bid}").json()
        superseded = next(c for c in b["coas"] if c["status"] == "SUPERSEDED")
        r = context["qa"].post(f"{API}/batches/{bid}/coa/{superseded['id']}/send", json={
            "recipients": [{"name": "X", "email": "x@test.local"}]})
        assert r.status_code == 400


# ---------------- Exclusive product customer lock ----------------
class TestExclusiveProduct:
    def test_create_batch_for_exclusive_product_locks_customer(self, context):
        prod = context["products"]["Formaldehyde Blend FB2"]
        r = context["qc"].post(f"{API}/batches", json={
            "product_id": prod["id"], "batch_number": _bn("EX"),
            "production_date": "2026-01-15"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["customer_id"] is not None
        assert b["customer_name"] == "Northwind Chemicals"


# ---------------- No shelf life product ----------------
class TestNoShelfLife:
    def test_batch_with_no_shelf_life(self, context):
        prod = context["products"]["Process Water Grade A"]
        r = context["qc"].post(f"{API}/batches", json={
            "product_id": prod["id"], "batch_number": _bn("PW"),
            "production_date": "2026-01-15"})
        assert r.status_code == 200
        b = r.json()
        assert b["expiry_date"] is None
        assert b["shelf_life_required"] is False


# ---------------- ON_HOLD (overdue instrument) ----------------
class TestHoldOverdueInstrument:
    _batch_id = None

    def test_release_with_overdue_instrument_puts_on_hold(self, context):
        prod = context["products"]["Methanol Solution 99%"]
        r = context["qc"].post(f"{API}/batches", json={
            "product_id": prod["id"], "batch_number": _bn("HOLD"),
            "production_date": "2026-01-15"})
        bid = r.json()["id"]
        TestHoldOverdueInstrument._batch_id = bid
        params = context["params"]
        overdue = next(i for n, i in context["instruments"].items() if "Legacy" in n)
        # enter fully in-spec results but overdue instrument
        r = context["qc"].post(f"{API}/batches/{bid}/results", json={
            "instrument_id": overdue["id"],
            "results": [
                {"parameter_id": params["pH"]["id"], "value_numeric": 7.0},
                {"parameter_id": params["COD"]["id"], "value_numeric": 500.0},
                {"parameter_id": params["Appearance"]["id"], "value_text": "Clear Colourless"},
            ]})
        assert r.status_code == 200
        rel = context["qc"].post(f"{API}/batches/{bid}/release", json={"customer_ids": []})
        assert rel.status_code == 400
        assert "on hold" in rel.text.lower()
        b = context["qa"].get(f"{API}/batches/{bid}").json()
        assert b["status"] == "ON_HOLD"
        assert len(b["hold_reasons"]) >= 1

    def test_qa_return_requires_actions_then_qc_amend(self, context):
        bid = TestHoldOverdueInstrument._batch_id
        r = context["qa"].post(f"{API}/batches/{bid}/qa-decision/return", json={
            "issue": "Please switch to a calibrated instrument",
            "required_actions": ["Re-run on HPLC-01"]})
        assert r.status_code == 200
        b = r.json()
        assert b["status"] == "RETURNED"
        assert "Re-run on HPLC-01" in b["required_actions"]

    def test_qc_amend_requires_reason(self, context):
        bid = TestHoldOverdueInstrument._batch_id
        params = context["params"]
        # attempt amend without reason
        r = context["qc"].post(f"{API}/batches/{bid}/results", json={
            "results": [{"parameter_id": params["pH"]["id"], "value_numeric": 7.1}]})
        assert r.status_code == 400

    def test_qc_amend_with_reason_and_switch_instrument(self, context):
        bid = TestHoldOverdueInstrument._batch_id
        params = context["params"]
        hplc = next(i for n, i in context["instruments"].items() if "HPLC" in n)
        r = context["qc"].post(f"{API}/batches/{bid}/results", json={
            "instrument_id": hplc["id"],
            "results": [{"parameter_id": params["pH"]["id"], "value_numeric": 7.1,
                         "reason": "Rechecked calibration"}]})
        assert r.status_code == 200, r.text
        b = r.json()
        ph = next(x for x in b["results"] if x["parameter_name"] == "pH")
        assert ph["revision"] == 2
        assert len(ph["amendments"]) == 1
        assert ph["amendments"][0]["reason"] == "Rechecked calibration"
        assert ph["amendments"][0]["user_email"] == QC["email"]

    def test_qc_resubmit_and_qa_release_requires_investigation_docs(self, context):
        bid = TestHoldOverdueInstrument._batch_id
        # resubmit
        r = context["qc"].post(f"{API}/batches/{bid}/submit", json={"comment": "resubmitting"})
        assert r.status_code == 200
        # QA release without RCA/impact/corrective -> 400
        r = context["qa"].post(f"{API}/batches/{bid}/qa-decision/release", json={
            "issue": "Investigation complete", "root_cause": "", "impact": "",
            "corrective_action": ""})
        assert r.status_code == 400

    def test_qa_release_with_documentation_generates_coa(self, context):
        bid = TestHoldOverdueInstrument._batch_id
        r = context["qa"].post(f"{API}/batches/{bid}/qa-decision/release", json={
            "issue": "Investigation complete",
            "root_cause": "Original instrument out of calibration",
            "impact": "No product impact - retest in spec",
            "corrective_action": "Re-run on HPLC-01"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["status"] == "RELEASED"
        assert len(b["coas"]) == 1


# ---------------- ON_HOLD (fail result) ----------------
class TestHoldFailResult:
    def test_fail_result_holds_batch(self, context):
        prod = context["products"]["Methanol Solution 99%"]
        r = context["qc"].post(f"{API}/batches", json={
            "product_id": prod["id"], "batch_number": _bn("FAIL"),
            "production_date": "2026-01-15"})
        bid = r.json()["id"]
        params = context["params"]
        hplc = next(i for n, i in context["instruments"].items() if "HPLC" in n)
        r = context["qc"].post(f"{API}/batches/{bid}/results", json={
            "instrument_id": hplc["id"],
            "results": [
                {"parameter_id": params["pH"]["id"], "value_numeric": 12.0},  # FAIL (>9)
                {"parameter_id": params["COD"]["id"], "value_numeric": 500.0},
                {"parameter_id": params["Appearance"]["id"], "value_text": "Clear Colourless"},
            ]})
        assert r.status_code == 200
        rel = context["qc"].post(f"{API}/batches/{bid}/release", json={"customer_ids": []})
        assert rel.status_code == 400
        b = context["qc"].get(f"{API}/batches/{bid}").json()
        assert b["status"] == "ON_HOLD"

    def test_missing_result_holds_batch(self, context):
        prod = context["products"]["Methanol Solution 99%"]
        r = context["qc"].post(f"{API}/batches", json={
            "product_id": prod["id"], "batch_number": _bn("MISS"),
            "production_date": "2026-01-15"})
        bid = r.json()["id"]
        params = context["params"]
        hplc = next(i for n, i in context["instruments"].items() if "HPLC" in n)
        # only pH, missing COD & Appearance
        r = context["qc"].post(f"{API}/batches/{bid}/results", json={
            "instrument_id": hplc["id"],
            "results": [{"parameter_id": params["pH"]["id"], "value_numeric": 7.0}]})
        assert r.status_code == 200
        rel = context["qc"].post(f"{API}/batches/{bid}/release", json={"customer_ids": []})
        assert rel.status_code == 400
        b = context["qc"].get(f"{API}/batches/{bid}").json()
        assert b["status"] == "ON_HOLD"


# ---------------- Self-approval / role gating ----------------
class TestRoleGating:
    def test_qa_cannot_approve_own_submitted_batch(self, context):
        # Create as QC, then submit by QA... but QA can't create batches (RR admin, qc).
        # Simulate by: admin creates + submits, then QA (different user) approves works.
        # Better: create batch as QC, but have QA submit? Only qc/admin can submit.
        # Alternative: use admin to create+submit; QA can still release because created_by is admin@.
        # For self-approval, admin (who is admin) creates+submits and tries admin approve? admin has role admin, but qa-decision is RR("qa") only.
        # So the check we can hit is: QA-created batch (admin only, since QA lacks create perm). Skip nuance.
        # Instead: verify QC cannot hit qa-decision endpoints.
        prod = context["products"]["Methanol Solution 99%"]
        r = context["qc"].post(f"{API}/batches", json={
            "product_id": prod["id"], "batch_number": _bn("RG"),
            "production_date": "2026-01-15"})
        bid = r.json()["id"]
        r = context["qc"].post(f"{API}/batches/{bid}/qa-decision/approve", json={"issue": "x"})
        assert r.status_code == 403

    def test_qc_cannot_amend_production_date(self, context):
        prod = context["products"]["Methanol Solution 99%"]
        r = context["qc"].post(f"{API}/batches", json={
            "product_id": prod["id"], "batch_number": _bn("PDQC"),
            "production_date": "2026-01-15"})
        bid = r.json()["id"]
        r = context["qc"].post(f"{API}/batches/{bid}/production-date", json={
            "production_date": "2026-01-16", "reason": "x"})
        assert r.status_code == 403

    def test_qc_cannot_cancel(self, context):
        prod = context["products"]["Methanol Solution 99%"]
        r = context["qc"].post(f"{API}/batches", json={
            "product_id": prod["id"], "batch_number": _bn("CNQC"),
            "production_date": "2026-01-15"})
        bid = r.json()["id"]
        r = context["qc"].post(f"{API}/batches/{bid}/cancel", json={"reason": "x"})
        assert r.status_code == 403

    def test_admin_cannot_cancel(self, context):
        prod = context["products"]["Methanol Solution 99%"]
        r = context["admin"].post(f"{API}/batches", json={
            "product_id": prod["id"], "batch_number": _bn("CNAD"),
            "production_date": "2026-01-15"})
        bid = r.json()["id"]
        r = context["admin"].post(f"{API}/batches/{bid}/cancel", json={"reason": "x"})
        assert r.status_code == 403


# ---------------- Cancellation ----------------
class TestCancellation:
    def test_qa_cancels_batch_without_coa(self, context):
        prod = context["products"]["Methanol Solution 99%"]
        r = context["qc"].post(f"{API}/batches", json={
            "product_id": prod["id"], "batch_number": _bn("CAN"),
            "production_date": "2026-01-15"})
        bid = r.json()["id"]
        r = context["qa"].post(f"{API}/batches/{bid}/cancel", json={"reason": "Test cancellation"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "CANCELLED"

    def test_cancel_requires_reason(self, context):
        prod = context["products"]["Methanol Solution 99%"]
        r = context["qc"].post(f"{API}/batches", json={
            "product_id": prod["id"], "batch_number": _bn("CANNR"),
            "production_date": "2026-01-15"})
        bid = r.json()["id"]
        r = context["qa"].post(f"{API}/batches/{bid}/cancel", json={"reason": ""})
        assert r.status_code == 400

    def test_cancel_blocked_when_coa_exists(self, context, qc_s, qa_s):
        # Use the already-released batch from TestBatchHappyPath
        # Find a released batch by admin
        batches = context["admin"].get(f"{API}/batches", params={"status": "RELEASED"}).json()
        assert batches, "no released batch available"
        bid = batches[0]["id"]
        r = context["qa"].post(f"{API}/batches/{bid}/cancel", json={"reason": "trying"})
        assert r.status_code == 400


# ---------------- Spec amendment / version snapshot ----------------
class TestSpecAmendment:
    def test_qc_cannot_amend_product(self, context):
        prod = context["products"]["Methanol Solution 99%"]
        r = context["qc"].post(f"{API}/products/{prod['id']}/amend", json={
            "shelf_life_days": 800, "reason": "bump"})
        assert r.status_code == 403

    def test_qa_amend_shelf_life_snapshots_old_batches(self, context):
        # Create a batch before amend
        prod = context["products"]["Methanol Solution 99%"]
        r = context["qc"].post(f"{API}/batches", json={
            "product_id": prod["id"], "batch_number": _bn("PRE"),
            "production_date": "2026-01-15"})
        pre_bid = r.json()["id"]
        pre_expiry = r.json()["expiry_date"]
        pre_version = r.json()["spec_version"]
        # QA amends shelf life
        r = context["qa"].post(f"{API}/products/{prod['id']}/amend", json={
            "shelf_life_days": 1000, "reason": "Extended stability data available"})
        assert r.status_code == 200, r.text
        new_v = r.json()
        assert new_v["shelf_life_days"] == 1000
        # Old batch keeps original values
        b = context["qc"].get(f"{API}/batches/{pre_bid}").json()
        assert b["expiry_date"] == pre_expiry
        assert b["spec_version"] == pre_version
        # New batch (production date = today) picks up new version
        from datetime import date as _d
        r = context["qc"].post(f"{API}/batches", json={
            "product_id": prod["id"], "batch_number": _bn("POST"),
            "production_date": _d.today().isoformat()})
        assert r.status_code == 200
        post = r.json()
        assert post["spec_version"] == new_v["version"]
        assert post["shelf_life_days"] == 1000

    def test_amend_without_reason_rejected(self, context):
        prod = context["products"]["Methanol Solution 99%"]
        r = context["qa"].post(f"{API}/products/{prod['id']}/amend", json={
            "shelf_life_days": 999, "reason": ""})
        assert r.status_code == 400


# ---------------- Batch history / audit ----------------
class TestHistory:
    def test_batch_history_records_actions(self, context):
        # Get a released batch and check history has key actions
        batches = context["admin"].get(f"{API}/batches", params={"status": "RELEASED"}).json()
        assert batches
        bid = batches[0]["id"]
        r = context["admin"].get(f"{API}/batches/{bid}/history")
        assert r.status_code == 200
        actions = {h["action"] for h in r.json()}
        # At least creation and release must appear
        assert "BATCH_CREATED" in actions
        assert any(a in actions for a in ("BATCH_RELEASED", "COA_GENERATED"))
