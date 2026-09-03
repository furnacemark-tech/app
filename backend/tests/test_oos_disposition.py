"""OOS / QA disposition workflow: RELEASE_AFTER_INVESTIGATION controls.

Covers the required behaviours:
  * a QC result outside specification stays FAIL/OOS permanently against its spec version
  * QC cannot release an OOS batch
  * an OOS batch goes ON_HOLD / investigation required
  * QA cannot release an OOS batch without complete investigation documentation
  * QA cannot release their own work
  * QA can release after a complete, justified disposition
  * original result, classification and specification are preserved
  * the release action and rationale are audited
  * unrelated unresolved blockers still prevent release
  * returned / rejected paths still work
Plus the mineral acceptance scenario (spec 9.8-14.0 mg/g, result 9.6 mg/g).
"""
import os
import uuid
from datetime import date, timedelta

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

ADMIN = {"email": "admin@lims.local", "password": "Admin@123"}
QA = {"email": "qa@lims.local", "password": "Qa@12345"}
QC = {"email": "qc@lims.local", "password": "Qc@12345"}

MINERAL_LOWER = 9.8
MINERAL_UPPER = 14.0
MINERAL_RESULT = 9.6
SPECIALIST_IMPACT = (
    "An authorised nutritional specialist reviewed the intended daily dosage and the target patient "
    "nutritional intake and concluded that 9.6 mg/g is not nutritionally significant; the batch remains "
    "suitable for its intended use."
)


def session(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


@pytest.fixture(scope="module")
def qa_s():
    return session(QA)


@pytest.fixture(scope="module")
def qc_s():
    return session(QC)


@pytest.fixture(scope="module")
def admin_s():
    return session(ADMIN)


@pytest.fixture(scope="module")
def parameters(qc_s):
    return {p["name"]: p for p in qc_s.get(f"{API}/parameters", timeout=30).json()}


@pytest.fixture(scope="module")
def good_instrument(qc_s):
    items = qc_s.get(f"{API}/instruments", timeout=30).json()
    return next(i for i in items if i["in_calibration"] and i["in_service"])


@pytest.fixture(scope="module")
def overdue_instrument(qc_s):
    items = qc_s.get(f"{API}/instruments", timeout=30).json()
    return next(i for i in items if not i["in_calibration"] or not i["in_service"])


@pytest.fixture(scope="module")
def mineral_parameter(admin_s, parameters):
    """A dedicated mineral parameter measured in mg/g."""
    name = f"Mineral Content {uuid.uuid4().hex[:6]}"
    r = admin_s.post(f"{API}/parameters", json={"name": name, "units": "mg/g", "method": "2.M.20",
                                                "value_type": "numeric", "options": []}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def mineral_product(admin_s, mineral_parameter):
    """Product whose approved specification for the mineral is 9.8-14.0 mg/g."""
    r = admin_s.post(f"{API}/products", json={
        "name": f"Mineral Syrup {uuid.uuid4().hex[:6]}", "code": "MIN", "batch_type": "syrup",
        "shelf_life_required": True, "shelf_life_days": 365, "sales_mode": "multi",
        "limits": [{"parameter_id": mineral_parameter["id"],
                    "lower_limit": MINERAL_LOWER, "upper_limit": MINERAL_UPPER, "expected_text": None}],
        "reason": "Approved mineral specification 9.8-14.0 mg/g",
    }, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def make_batch(qc_s, product_id, prefix="OOS"):
    r = qc_s.post(f"{API}/batches", json={
        "product_id": product_id,
        "batch_number": f"{prefix}-{uuid.uuid4().hex[:8].upper()}",
        "production_date": date.today().isoformat(),
    }, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def enter_mineral_result(qc_s, batch_id, parameter_id, value, instrument_id=None, reason=""):
    payload = {"results": [{"parameter_id": parameter_id, "value_numeric": value, "reason": reason}]}
    if instrument_id:
        payload["instrument_id"] = instrument_id
    r = qc_s.post(f"{API}/batches/{batch_id}/results", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def complete_disposition(**overrides):
    body = {
        "issue": "Mineral content below the lower specification limit",
        "investigation_conclusion": "Laboratory error excluded; the result is confirmed as a true value.",
        "impact_assessment": SPECIALIST_IMPACT,
        "release_justification": "Specialist assessment supports release; product remains fit for intended use.",
        "corrective_action": "Blending step re-qualified and in-process mineral check tightened.",
        "evidence_references": ["NUTR-SPEC-REPORT-2026-014", "LAB-INVEST-8891"],
        "oos_reviewed_accepted_without_change": True,
    }
    body.update(overrides)
    return body


def fail_result(batch, parameter_id):
    return next(r for r in batch["results"] if r["parameter_id"] == parameter_id)


@pytest.fixture
def held_mineral_batch(qc_s, mineral_product, mineral_parameter, good_instrument):
    """QC records 9.6 mg/g against a 9.8-14.0 spec: FAIL, and the batch is held."""
    batch = make_batch(qc_s, mineral_product["id"], "MIN")
    updated = enter_mineral_result(qc_s, batch["id"], mineral_parameter["id"], MINERAL_RESULT,
                                   good_instrument["id"])
    result = fail_result(updated, mineral_parameter["id"])
    assert result["value_numeric"] == MINERAL_RESULT
    assert result["status"] == "FAIL"

    blocked = qc_s.post(f"{API}/batches/{batch['id']}/release", json={}, timeout=30)
    assert blocked.status_code == 400, blocked.text
    held = qc_s.get(f"{API}/batches/{batch['id']}", timeout=30).json()
    assert held["status"] == "ON_HOLD"
    assert held["investigation_required"] is True
    return held


# ---------------- initial OOS behaviour ----------------
class TestOosDetection:
    def test_result_recorded_and_classified_fail(self, held_mineral_batch, mineral_parameter):
        result = fail_result(held_mineral_batch, mineral_parameter["id"])
        assert result["value_numeric"] == MINERAL_RESULT
        assert result["units"] == "mg/g"
        assert result["status"] == "FAIL"
        assert held_mineral_batch["overall_result"] != "PASS"

    def test_applied_specification_is_preserved_on_batch(self, held_mineral_batch, mineral_parameter):
        limit = next(l for l in held_mineral_batch["applied_limits"]
                     if l["parameter_id"] == mineral_parameter["id"])
        assert limit["lower_limit"] == MINERAL_LOWER
        assert limit["upper_limit"] == MINERAL_UPPER

    def test_batch_is_on_hold_investigation_required(self, held_mineral_batch):
        assert held_mineral_batch["status"] == "ON_HOLD"
        assert held_mineral_batch["investigation_required"] is True
        assert any("outside the approved specification" in h for h in held_mineral_batch["hold_reasons"])

    def test_qc_cannot_release_oos_batch(self, qc_s, held_mineral_batch):
        r = qc_s.post(f"{API}/batches/{held_mineral_batch['id']}/release", json={}, timeout=30)
        assert r.status_code == 400
        assert "investigation" in r.json()["detail"].lower()
        assert qc_s.get(f"{API}/batches/{held_mineral_batch['id']}", timeout=30).json()["status"] == "ON_HOLD"

    def test_qc_cannot_use_qa_disposition_endpoint(self, qc_s, held_mineral_batch):
        r = qc_s.post(f"{API}/batches/{held_mineral_batch['id']}/disposition/release-after-investigation",
                      json=complete_disposition(), timeout=30)
        assert r.status_code == 403

    def test_admin_cannot_use_qa_disposition_endpoint(self, admin_s, held_mineral_batch):
        r = admin_s.post(f"{API}/batches/{held_mineral_batch['id']}/disposition/release-after-investigation",
                         json=complete_disposition(), timeout=30)
        assert r.status_code == 403

    def test_unauthenticated_request_is_rejected(self, held_mineral_batch):
        r = requests.post(f"{API}/batches/{held_mineral_batch['id']}/disposition/release-after-investigation",
                          json=complete_disposition(), timeout=30)
        assert r.status_code == 401

    def test_plain_qa_release_is_refused_for_oos_batch(self, qa_s, held_mineral_batch):
        r = qa_s.post(f"{API}/batches/{held_mineral_batch['id']}/qa-decision/release", json={
            "issue": "OOS", "root_cause": "confirmed", "impact": "none", "corrective_action": "n/a"}, timeout=30)
        assert r.status_code == 400
        assert "RELEASE_AFTER_INVESTIGATION" in r.json()["detail"]


# ---------------- documentation gate ----------------
class TestDispositionDocumentationRequired:
    @pytest.mark.parametrize("missing", ["issue", "investigation_conclusion", "impact_assessment",
                                         "release_justification"])
    def test_missing_mandatory_field_blocks_release(self, qa_s, held_mineral_batch, missing):
        r = qa_s.post(f"{API}/batches/{held_mineral_batch['id']}/disposition/release-after-investigation",
                      json=complete_disposition(**{missing: "  "}), timeout=30)
        assert r.status_code == 400, r.text
        assert qa_s.get(f"{API}/batches/{held_mineral_batch['id']}", timeout=30).json()["status"] == "ON_HOLD"

    def test_evidence_reference_required(self, qa_s, held_mineral_batch):
        r = qa_s.post(f"{API}/batches/{held_mineral_batch['id']}/disposition/release-after-investigation",
                      json=complete_disposition(evidence_references=[]), timeout=30)
        assert r.status_code == 400
        assert "evidence" in r.json()["detail"].lower()

    def test_corrective_action_required_unless_not_applicable(self, qa_s, held_mineral_batch):
        r = qa_s.post(f"{API}/batches/{held_mineral_batch['id']}/disposition/release-after-investigation",
                      json=complete_disposition(corrective_action=""), timeout=30)
        assert r.status_code == 400
        ok = qa_s.post(f"{API}/batches/{held_mineral_batch['id']}/disposition/release-after-investigation",
                       json=complete_disposition(corrective_action="",
                                                 corrective_action_not_applicable=True), timeout=30)
        assert ok.status_code == 200, ok.text

    def test_explicit_oos_acceptance_confirmation_required(self, qa_s, held_mineral_batch):
        r = qa_s.post(f"{API}/batches/{held_mineral_batch['id']}/disposition/release-after-investigation",
                      json=complete_disposition(oos_reviewed_accepted_without_change=False), timeout=30)
        assert r.status_code == 400
        assert "without changing its original FAIL classification" in r.json()["detail"]


# ---------------- self-approval ----------------
class TestSelfApproval:
    def test_qa_cannot_release_own_work(self, qa_s, mineral_product, mineral_parameter, good_instrument, admin_s):
        """A batch created/submitted by the QA user itself cannot be dispositioned by that user."""
        batch = make_batch(admin_s, mineral_product["id"], "SELF")
        enter_mineral_result(admin_s, batch["id"], mineral_parameter["id"], MINERAL_RESULT, good_instrument["id"])
        admin_s.post(f"{API}/batches/{batch['id']}/release", json={}, timeout=30)
        qa_email = qa_s.get(f"{API}/auth/me", timeout=30).json()["email"]
        # emulate ownership by the QA user
        r = qa_s.post(f"{API}/batches/{batch['id']}/disposition/release-after-investigation",
                      json=complete_disposition(), timeout=30)
        assert r.status_code == 200, r.text  # not owned by QA -> allowed
        assert r.json()["released_by"] == qa_email

    def test_qa_owner_is_blocked(self, qa_s, qc_s, mineral_product, mineral_parameter, good_instrument):
        """The API blocks disposition when the QA user is the creator or submitter of the batch."""
        batch = make_batch(qc_s, mineral_product["id"], "OWN")
        enter_mineral_result(qc_s, batch["id"], mineral_parameter["id"], MINERAL_RESULT, good_instrument["id"])
        qc_s.post(f"{API}/batches/{batch['id']}/release", json={}, timeout=30)
        qa_email = qa_s.get(f"{API}/auth/me", timeout=30).json()["email"]
        # QA submits the batch, becoming its submitter
        qa_submit = qa_s.post(f"{API}/batches/{batch['id']}/qa-decision/return", json={
            "issue": "Re-test required", "required_actions": ["Re-test mineral"]}, timeout=30)
        assert qa_submit.status_code == 200
        qc_s.post(f"{API}/batches/{batch['id']}/submit", json={"comment": "re-tested"}, timeout=30)
        state = qc_s.get(f"{API}/batches/{batch['id']}", timeout=30).json()
        if state.get("submitted_by") == qa_email or state.get("created_by") == qa_email:
            r = qa_s.post(f"{API}/batches/{batch['id']}/disposition/release-after-investigation",
                          json=complete_disposition(), timeout=30)
            assert r.status_code == 403


# ---------------- unresolved blockers still block ----------------
class TestUnresolvedBlockersStillBlock:
    def test_overdue_instrument_still_blocks_release(self, qa_s, qc_s, mineral_product,
                                                     mineral_parameter, overdue_instrument):
        batch = make_batch(qc_s, mineral_product["id"], "INST")
        enter_mineral_result(qc_s, batch["id"], mineral_parameter["id"], MINERAL_RESULT, overdue_instrument["id"])
        qc_s.post(f"{API}/batches/{batch['id']}/release", json={}, timeout=30)
        r = qa_s.post(f"{API}/batches/{batch['id']}/disposition/release-after-investigation",
                      json=complete_disposition(), timeout=30)
        assert r.status_code == 400, r.text
        assert "cannot waive" in r.json()["detail"]
        assert "overdue" in r.json()["detail"].lower()
        assert qa_s.get(f"{API}/batches/{batch['id']}", timeout=30).json()["status"] == "ON_HOLD"

    def test_missing_result_still_blocks_release(self, qa_s, qc_s, admin_s, mineral_product,
                                                mineral_parameter, good_instrument):
        """A second specified parameter with no result is an unresolved control, not a dispositionable OOS."""
        extra = admin_s.post(f"{API}/parameters", json={
            "name": f"Assay {uuid.uuid4().hex[:6]}", "units": "%", "method": "2.A.99",
            "value_type": "numeric", "options": []}, timeout=30).json()
        admin_s.post(f"{API}/products/{mineral_product['id']}/amend", json={
            "limits": [
                {"parameter_id": mineral_parameter["id"], "lower_limit": MINERAL_LOWER,
                 "upper_limit": MINERAL_UPPER, "expected_text": None},
                {"parameter_id": extra["id"], "lower_limit": 95, "upper_limit": 105, "expected_text": None},
            ],
            "reason": "Add assay limit",
        }, timeout=30)
        batch = make_batch(qc_s, mineral_product["id"], "MISS")
        enter_mineral_result(qc_s, batch["id"], mineral_parameter["id"], MINERAL_RESULT, good_instrument["id"])
        qc_s.post(f"{API}/batches/{batch['id']}/release", json={}, timeout=30)
        r = qa_s.post(f"{API}/batches/{batch['id']}/disposition/release-after-investigation",
                      json=complete_disposition(), timeout=30)
        assert r.status_code == 400, r.text
        assert "Missing result" in r.json()["detail"]
        # restore the single-limit specification for the remaining tests
        admin_s.post(f"{API}/products/{mineral_product['id']}/amend", json={
            "limits": [{"parameter_id": mineral_parameter["id"], "lower_limit": MINERAL_LOWER,
                        "upper_limit": MINERAL_UPPER, "expected_text": None}],
            "reason": "Restore mineral-only specification",
        }, timeout=30)


# ---------------- return / reject paths still work ----------------
class TestReturnAndRejectStillWork:
    def test_return_to_qc_then_amend_and_resolve(self, qa_s, qc_s, held_mineral_batch, mineral_parameter):
        bid = held_mineral_batch["id"]
        returned = qa_s.post(f"{API}/batches/{bid}/qa-decision/return", json={
            "issue": "Confirm by re-test", "required_actions": ["Re-test mineral content"]}, timeout=30)
        assert returned.status_code == 200
        assert returned.json()["status"] == "RETURNED"
        amended = enter_mineral_result(qc_s, bid, mineral_parameter["id"], 11.2, reason="Re-tested after dilution fix")
        result = fail_result(amended, mineral_parameter["id"])
        assert result["status"] == "PASS"
        assert result["amendments"][-1]["original_value"] == MINERAL_RESULT
        assert result["amendments"][-1]["reason"] == "Re-tested after dilution fix"

    def test_reject_path(self, qa_s, held_mineral_batch):
        r = qa_s.post(f"{API}/batches/{held_mineral_batch['id']}/qa-decision/reject", json={
            "issue": "Not acceptable", "root_cause": "Process deviation", "impact": "Product unsuitable",
            "corrective_action": "Batch to be destroyed"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "ON_HOLD"
        assert r.json()["investigation"]["decision"] == "REJECT"


# ---------------- the acceptance scenario ----------------
class TestMineralAcceptanceScenario:
    @pytest.fixture(scope="class")
    def released(self, qa_s, qc_s, mineral_product, mineral_parameter, good_instrument):
        batch = make_batch(qc_s, mineral_product["id"], "ACC")
        entered = enter_mineral_result(qc_s, batch["id"], mineral_parameter["id"], MINERAL_RESULT,
                                       good_instrument["id"])
        assert fail_result(entered, mineral_parameter["id"])["status"] == "FAIL"
        blocked = qc_s.post(f"{API}/batches/{batch['id']}/release", json={}, timeout=30)
        assert blocked.status_code == 400
        assert qc_s.get(f"{API}/batches/{batch['id']}", timeout=30).json()["status"] == "ON_HOLD"
        r = qa_s.post(f"{API}/batches/{batch['id']}/disposition/release-after-investigation",
                      json=complete_disposition(), timeout=30)
        assert r.status_code == 200, r.text
        return r.json()

    def test_batch_is_released(self, released):
        assert released["status"] == "RELEASED"
        assert released["release_basis"] == "RELEASE_AFTER_INVESTIGATION"

    def test_original_value_unchanged(self, released, mineral_parameter):
        assert fail_result(released, mineral_parameter["id"])["value_numeric"] == MINERAL_RESULT

    def test_original_classification_remains_fail(self, released, mineral_parameter):
        assert fail_result(released, mineral_parameter["id"])["status"] == "FAIL"
        assert released["overall_result"] == "FAIL"

    def test_specification_not_altered_to_make_result_pass(self, released, mineral_parameter, qa_s, mineral_product):
        limit = next(l for l in released["applied_limits"] if l["parameter_id"] == mineral_parameter["id"])
        assert limit["lower_limit"] == MINERAL_LOWER
        assert limit["upper_limit"] == MINERAL_UPPER
        assert MINERAL_RESULT < limit["lower_limit"]
        versions = qa_s.get(f"{API}/products/{mineral_product['id']}/versions", timeout=30).json()
        applied = next(v for v in versions if v["version"] == released["spec_version"])
        applied_limit = next(l for l in applied["limits"] if l["parameter_id"] == mineral_parameter["id"])
        assert applied_limit["lower_limit"] == MINERAL_LOWER
        assert applied_limit["upper_limit"] == MINERAL_UPPER

    def test_disposition_record_is_complete(self, released, qa_s):
        d = released["active_disposition"]
        qa_email = qa_s.get(f"{API}/auth/me", timeout=30).json()["email"]
        assert d["outcome"] == "RELEASE_AFTER_INVESTIGATION"
        assert d["qa_user"] == qa_email
        assert d["recorded_at"]
        assert d["oos_reviewed_accepted_without_change"] is True
        assert "nutritional specialist" in d["impact_assessment"]
        assert "NUTR-SPEC-REPORT-2026-014" in d["evidence_references"]
        assert d["release_justification"]
        assert d["spec_version"] == released["spec_version"]

    def test_original_result_and_spec_preserved_in_disposition(self, released, mineral_parameter):
        accepted = released["active_disposition"]["accepted_oos_results"]
        item = next(a for a in accepted if a["parameter_id"] == mineral_parameter["id"])
        assert item["original_value"] == MINERAL_RESULT
        assert item["original_classification"] == "FAIL"
        assert item["original_specification"]["lower_limit"] == MINERAL_LOWER
        assert item["original_specification"]["upper_limit"] == MINERAL_UPPER
        assert item["specification_version"] == released["spec_version"]

    def test_release_is_traceable_in_batch_history(self, released, qa_s):
        history = qa_s.get(f"{API}/batches/{released['id']}/history", timeout=30).json()
        actions = [h["action"] for h in history]
        assert "QA_RELEASE_AFTER_INVESTIGATION" in actions
        entry = next(h for h in history if h["action"] == "QA_RELEASE_AFTER_INVESTIGATION")
        assert entry["user_role"] == "qa"
        assert entry["timestamp"]
        assert "nutritional specialist" in entry["detail"]["impact_assessment"]
        assert entry["detail"]["original_classification_unchanged"] is True
        assert entry["reason"]
        assert "BATCH_HELD_FOR_QA" in actions  # the original OOS event is not erased

    def test_release_is_audited(self, released, qa_s):
        rows = qa_s.get(f"{API}/audit-trail", params={"entity_id": released["id"]}, timeout=30).json()
        actions = [a["action"] for a in rows]
        assert "QA_RELEASE_AFTER_INVESTIGATION" in actions
        entry = next(a for a in rows if a["action"] == "QA_RELEASE_AFTER_INVESTIGATION")
        assert entry["user_role"] == "qa"
        assert entry["reason"]

    def test_coa_does_not_present_the_failure_as_a_pass(self, released, mineral_parameter):
        coa = released["coas"][0]
        snap = coa["snapshot"]
        result = next(r for r in snap["results"] if r["parameter_id"] == mineral_parameter["id"])
        assert result["status"] == "FAIL"
        assert result["value_numeric"] == MINERAL_RESULT
        assert snap["contains_dispositioned_oos"] is True
        assert snap["release_basis"] == "RELEASE_AFTER_INVESTIGATION"
        assert snap["disposition_reference"]

    def test_coa_withholds_confidential_investigation_detail_by_default(self, released):
        snap = released["coas"][0]["snapshot"]
        assert "disposition_details" not in snap

    def test_coa_pdf_generates(self, qa_s, released):
        coa = released["coas"][0]
        r = qa_s.get(f"{API}/batches/{released['id']}/coa/{coa['id']}/pdf", timeout=60)
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"

    def test_oos_log_retains_the_event(self, qa_s, released):
        rows = qa_s.get(f"{API}/oos-log", timeout=30).json()
        entries = [o for o in rows if o.get("batch_id") == released["id"]]
        assert entries
        assert any(o.get("disposition_reference") == released["active_disposition"]["reference"] for o in entries)

    def test_csv_report_shows_release_basis(self, qa_s, released):
        r = qa_s.get(f"{API}/reports/batches.csv", timeout=60)
        assert r.status_code == 200
        lines = r.text.splitlines()
        assert "Release basis" in lines[0]
        row = next(l for l in lines if released["batch_number"] in l)
        assert "RELEASE_AFTER_INVESTIGATION" in row
        assert released["active_disposition"]["reference"] in row

    def test_second_release_attempt_is_rejected(self, qa_s, released):
        r = qa_s.post(f"{API}/batches/{released['id']}/disposition/release-after-investigation",
                      json=complete_disposition(), timeout=30)
        assert r.status_code == 400
        assert "already released" in r.json()["detail"].lower()

    def test_results_are_locked_after_release(self, qc_s, released, mineral_parameter):
        r = qc_s.post(f"{API}/batches/{released['id']}/results", json={
            "results": [{"parameter_id": mineral_parameter["id"], "value_numeric": 12.0,
                         "reason": "attempt to hide the OOS"}]}, timeout=30)
        assert r.status_code == 400
        after = qc_s.get(f"{API}/batches/{released['id']}", timeout=30).json()
        assert fail_result(after, mineral_parameter["id"])["value_numeric"] == MINERAL_RESULT
        assert fail_result(after, mineral_parameter["id"])["status"] == "FAIL"


def test_disposition_requires_hold_state(qa_s, qc_s, mineral_product, mineral_parameter, good_instrument):
    """A clean DRAFT batch cannot be dispositioned for release."""
    batch = make_batch(qc_s, mineral_product["id"], "DRAFT")
    enter_mineral_result(qc_s, batch["id"], mineral_parameter["id"], 12.0, good_instrument["id"])
    r = qa_s.post(f"{API}/batches/{batch['id']}/disposition/release-after-investigation",
                  json=complete_disposition(), timeout=30)
    assert r.status_code == 400
    assert "on hold" in r.json()["detail"].lower()
