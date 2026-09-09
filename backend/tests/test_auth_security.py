"""Authentication and account provisioning security tests."""
import os
import time
import uuid
from pathlib import Path

import pytest
import jwt
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from conftest import run_db
from database import db

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / "frontend" / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


def clear_lockouts():
    """Brute-force lockout is intentional; these tests deliberately trigger it, so clear it between tests."""
    run_db(lambda: db.login_attempts.delete_many({}))


@pytest.fixture(autouse=True)
def no_lockout():
    clear_lockouts()
    yield
    clear_lockouts()

ADMIN = {"email": "admin@lims.local", "password": "Admin@123"}
QA = {"email": "qa@lims.local", "password": "Qa@12345"}
QC = {"email": "qc@lims.local", "password": "Qc@12345"}
DEFAULTS_THAT_MUST_NOT_WORK = ["admin123", "password", "Admin123", "changeme", "admin", "Password1"]


def login(creds):
    """Retries transient gateway errors (the restart test bounces the backend mid-suite)."""
    for attempt in range(15):
        try:
            r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
        except requests.RequestException:
            time.sleep(2)
            continue
        if r.status_code not in (502, 503, 504):
            return r
        time.sleep(2)
    return r


def request_with_retry(method, url, **kwargs):
    for attempt in range(15):
        try:
            r = requests.request(method, url, timeout=30, **kwargs)
        except requests.RequestException:
            time.sleep(2)
            continue
        if r.status_code not in (502, 503, 504):
            return r
        time.sleep(2)
    return r


def retrying_session():
    """Session that transparently retries gateway errors caused by the deliberate restart test."""
    s = requests.Session()
    retry = Retry(total=8, backoff_factor=1.0, status_forcelist=(502, 503, 504),
                  allowed_methods=frozenset({"GET", "POST", "PATCH", "DELETE"}))
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def session(creds):
    clear_lockouts()
    s = retrying_session()
    r = login(creds)
    assert r.status_code == 200, r.text
    s.cookies.update(r.cookies)
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


@pytest.fixture(scope="module")
def admin_s():
    return session(ADMIN)


def create_account(admin_session, prefix="tmp", role="qc"):
    """Create a dedicated account (with its temporary password already changed) for isolated tests."""
    email = unique_email(prefix)
    temp = f"Temp-{uuid.uuid4().hex[:12]}"
    created = admin_session.post(f"{API}/users", json={
        "email": email, "password": temp, "name": "Isolated Test User",
        "initials": "IT", "role": role}, timeout=30)
    assert created.status_code == 200, created.text
    first = login({"email": email, "password": temp})
    assert first.status_code == 200
    s = retrying_session()
    s.headers["Authorization"] = f"Bearer {first.json()['access_token']}"
    password = f"Live-{uuid.uuid4().hex[:12]}"
    assert s.post(f"{API}/auth/change-password", json={
        "current_password": temp, "new_password": password}, timeout=30).status_code == 200
    return {"id": created.json()["id"], "email": email, "password": password}


def unique_email(prefix="user"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}@lims.test"


class TestNoStartupCredentialReset:
    def test_existing_password_survives_restart(self, admin_s, restart_isolated_test_server):
        """Change a user's password, restart the backend, and prove startup did not restore anything."""
        account = create_account(admin_s, "restart")
        rotated = f"Rotated-{uuid.uuid4().hex[:12]}"
        assert admin_s.patch(f"{API}/users/{account['id']}",
                             json={"password": rotated}, timeout=30).status_code == 200
        assert login({"email": account["email"], "password": account["password"]}).status_code == 401

        restart_isolated_test_server()
        for _ in range(60):
            if login(ADMIN).status_code in (200, 401, 403, 429):
                break
            time.sleep(2)
        time.sleep(2)

        assert login({"email": account["email"], "password": account["password"]}).status_code == 401, \
            "startup restored a previous password"
        after = login({"email": account["email"], "password": rotated})
        assert after.status_code == 200
        assert after.json()["must_change_password"] is True  # admin reset forces a change
        assert login(ADMIN).status_code == 200  # existing accounts are untouched by the restart

    def test_no_default_credentials_accepted(self, admin_s):
        account = create_account(admin_s, "defaults")
        for password in DEFAULTS_THAT_MUST_NOT_WORK:
            for email in (account["email"], "admin@example.com", "root@lims.local"):
                r = login({"email": email, "password": password})
                assert r.status_code in (401, 403, 429), f"{email}/{password} was accepted"
            clear_lockouts()
        assert login({"email": account["email"], "password": account["password"]}).status_code == 200

    def test_no_plaintext_password_in_source(self):
        for path in (
            PROJECT_ROOT / "backend" / "server.py",
            PROJECT_ROOT / "backend" / "batches.py",
        ):
            content = path.read_text(encoding="utf-8")
            for secret in ("Qa@12345", "Qc@12345", "Admin@123", "ADMIN_PASSWORD"):
                assert secret not in content, f"{secret} found in {path}"


class TestFirstRunProvisioning:
    def test_status_reports_disabled_when_admin_exists(self):
        r = request_with_retry("GET", f"{API}/auth/provisioning-status")
        assert r.status_code == 200
        assert r.json()["administrator_exists"] is True
        assert r.json()["first_run_available"] is False

    def test_first_run_blocked_once_admin_exists(self):
        r = request_with_retry(
            "POST",
            f"{API}/auth/first-run",
            json={
                "email": unique_email("root"),
                "password": "AVeryLongPassword123!",
                "name": "Second Admin",
            },
        )
        assert r.status_code == 403
        assert "already exists" in r.json()["detail"]

    def test_first_run_is_unauthenticated_but_still_guarded(self):
        r = request_with_retry("POST", f"{API}/auth/first-run", json={
            "email": unique_email("root2"), "password": "short", "name": "X"})
        assert r.status_code == 403  # guard runs before validation of the weak password


class TestPasswordsNeverExposed:
    def test_login_response_has_no_password(self):
        body = login(ADMIN).json()
        assert "password" not in body["user"]
        assert "password_hash" not in body["user"]
        assert "password" not in str(body).lower().replace("must_change_password", "")

    def test_me_and_user_list_have_no_password(self, admin_s):
        me = admin_s.get(f"{API}/auth/me", timeout=30).json()
        assert "password_hash" not in me
        for u in admin_s.get(f"{API}/users", timeout=30).json():
            assert "password_hash" not in u and "password" not in u

    def test_audit_trail_never_records_password_values(self, admin_s):
        email = unique_email("audit")
        secret = f"Sup3r-{uuid.uuid4().hex[:10]}"
        created = admin_s.post(f"{API}/users", json={
            "email": email, "password": secret, "name": "Audit Probe", "initials": "AP", "role": "qc"}, timeout=30)
        assert created.status_code == 200, created.text
        assert "password" not in created.json() or created.json().get("temporary_password_issued")
        rows = admin_s.get(f"{API}/audit-trail", params={"entity_id": created.json()["id"]}, timeout=30).json()
        assert rows
        assert secret not in str(rows)
        assert "password_hash" not in str(rows)


class TestTemporaryPasswordFlow:
    def test_created_user_must_change_password_then_can_work(self, admin_s):
        email = unique_email("temp")
        temp = f"Temp-{uuid.uuid4().hex[:10]}"
        created = admin_s.post(f"{API}/users", json={
            "email": email, "password": temp, "name": "Temp User", "initials": "TU", "role": "qc"}, timeout=30)
        assert created.status_code == 200, created.text
        assert created.json()["must_change_password"] is True

        first = login({"email": email, "password": temp})
        assert first.status_code == 200
        assert first.json()["must_change_password"] is True
        s = retrying_session()
        s.headers["Authorization"] = f"Bearer {first.json()['access_token']}"

        blocked = s.get(f"{API}/samples", timeout=30)
        assert blocked.status_code == 403
        assert "temporary password" in blocked.json()["detail"].lower()

        new_password = f"Fresh-{uuid.uuid4().hex[:10]}"
        changed = s.post(f"{API}/auth/change-password", json={
            "current_password": temp, "new_password": new_password}, timeout=30)
        assert changed.status_code == 200, changed.text

        assert login({"email": email, "password": temp}).status_code == 401  # temp no longer usable
        after = login({"email": email, "password": new_password})
        assert after.status_code == 200
        assert after.json()["must_change_password"] is False
        s2 = retrying_session()
        s2.headers["Authorization"] = f"Bearer {after.json()['access_token']}"
        assert s2.get(f"{API}/samples", timeout=30).status_code == 200

    def test_generated_temporary_password_is_not_returned(self, admin_s):
        email = unique_email("gen")
        created = admin_s.post(f"{API}/users", json={
            "email": email, "name": "Generated", "initials": "GN", "role": "qc"}, timeout=30)
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["must_change_password"] is True
        assert "password" not in body and "password_hash" not in body
        assert body["temporary_password_issued"] is True

    def test_change_password_rejects_wrong_current_password(self, admin_s):
        account = create_account(admin_s, "wrongpw")
        creds = {"email": account["email"], "password": account["password"]}
        s = session(creds)
        r = s.post(f"{API}/auth/change-password", json={
            "current_password": "not-my-password", "new_password": "Whatever-123456"}, timeout=30)
        assert r.status_code == 401
        assert login(creds).status_code == 200  # unchanged


class TestAuthorisationBoundaries:
    def test_non_admin_cannot_create_users(self):
        for creds in (QA, QC):
            s = session(creds)
            r = s.post(f"{API}/users", json={
                "email": unique_email("nope"), "password": "Password-123", "name": "N", "initials": "N",
                "role": "admin"}, timeout=30)
            assert r.status_code == 403

    def test_non_admin_cannot_change_roles(self, admin_s):
        target = next(u for u in admin_s.get(f"{API}/users", timeout=30).json() if u["email"] == QC["email"])
        s = session(QA)
        assert s.patch(f"{API}/users/{target['id']}", json={"role": "admin"}, timeout=30).status_code == 403

    def test_unauthenticated_cannot_list_or_create_users(self):
        assert request_with_retry("GET", f"{API}/users").status_code == 401
        assert request_with_retry("POST", f"{API}/users", json={
            "email": unique_email(), "password": "Password-123", "name": "N", "initials": "N"}).status_code == 401

    def test_deactivated_user_cannot_authenticate(self, admin_s):
        email = unique_email("deact")
        temp = f"Temp-{uuid.uuid4().hex[:10]}"
        created = admin_s.post(f"{API}/users", json={
            "email": email, "password": temp, "name": "Deact", "initials": "DE", "role": "qc"}, timeout=30).json()
        assert login({"email": email, "password": temp}).status_code == 200
        assert admin_s.patch(f"{API}/users/{created['id']}", json={"active": False},
                             timeout=30).status_code == 200
        r = login({"email": email, "password": temp})
        assert r.status_code == 403
        assert "inactive" in r.json()["detail"].lower()

    def test_deactivation_revokes_existing_sessions(self, admin_s):
        email = unique_email("revoke")
        temp = f"Temp-{uuid.uuid4().hex[:10]}"
        created = admin_s.post(f"{API}/users", json={
            "email": email, "password": temp, "name": "Revoke", "initials": "RV", "role": "qc"}, timeout=30).json()
        first = login({"email": email, "password": temp}).json()
        s = retrying_session()
        s.headers["Authorization"] = f"Bearer {first['access_token']}"
        s.post(f"{API}/auth/change-password", json={"current_password": temp,
                                                    "new_password": f"Ok-{uuid.uuid4().hex[:10]}"}, timeout=30)
        admin_s.patch(f"{API}/users/{created['id']}", json={"active": False}, timeout=30)
        assert s.get(f"{API}/auth/me", timeout=30).status_code == 401


class TestSessionRevocation:
    def test_access_token_session_must_belong_to_token_user(self, admin_s):
        owner = create_account(admin_s, "sidowner")
        other = create_account(admin_s, "sidother")

        owner_login = login({"email": owner["email"], "password": owner["password"]})
        assert owner_login.status_code == 200
        payload = jwt.decode(
            owner_login.json()["access_token"],
            os.environ["JWT_SECRET"],
            algorithms=["HS256"])
        payload["sub"] = other["id"]
        payload["email"] = other["email"]
        mismatched = jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")

        r = request_with_retry(
            "GET", f"{API}/auth/me",
            headers={"Authorization": f"Bearer {mismatched}"})
        assert r.status_code == 401

    def test_refresh_session_must_belong_to_token_user(self, admin_s):
        owner = create_account(admin_s, "refreshowner")
        other = create_account(admin_s, "refreshother")

        owner_login = login({"email": owner["email"], "password": owner["password"]})
        assert owner_login.status_code == 200
        owner_access = owner_login.json()["access_token"]
        owner_refresh = owner_login.cookies.get("refresh_token")
        assert owner_refresh

        payload = jwt.decode(
            owner_refresh,
            os.environ["JWT_SECRET"],
            algorithms=["HS256"])
        payload["sub"] = other["id"]
        mismatched = jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")

        r = request_with_retry(
            "POST", f"{API}/auth/refresh",
            cookies={"refresh_token": mismatched})
        assert r.status_code == 401

        # Rejecting the mismatched token must not revoke its owner's session.
        owner_check = request_with_retry(
            "GET", f"{API}/auth/me",
            headers={"Authorization": f"Bearer {owner_access}"})
        assert owner_check.status_code == 200

    def test_logout_revokes_the_session(self, admin_s):
        account = create_account(admin_s, "logout")
        r = login({"email": account["email"], "password": account["password"]}).json()
        s = retrying_session()
        s.headers["Authorization"] = f"Bearer {r['access_token']}"
        assert s.get(f"{API}/auth/me", timeout=30).status_code == 200
        assert s.post(f"{API}/auth/logout", timeout=30).status_code == 200
        assert s.get(f"{API}/auth/me", timeout=30).status_code == 401

    def test_refresh_cookie_cannot_be_reused_after_logout(self, admin_s):
        account = create_account(admin_s, "replay")
        s = retrying_session()
        assert s.post(f"{API}/auth/login", json={
            "email": account["email"], "password": account["password"]}, timeout=30).status_code == 200
        refresh_cookie = s.cookies.get("refresh_token")
        assert refresh_cookie
        assert s.post(f"{API}/auth/logout", timeout=30).status_code == 200
        replay = request_with_retry("POST", f"{API}/auth/refresh", cookies={"refresh_token": refresh_cookie})
        assert replay.status_code == 401
        assert "revoked" in replay.json()["detail"].lower()

    def test_refresh_rotates_and_invalidates_the_previous_refresh_token(self, admin_s):
        account = create_account(admin_s, "rotatetok")
        s = retrying_session()
        s.post(f"{API}/auth/login", json={
            "email": account["email"], "password": account["password"]}, timeout=30)
        old = s.cookies.get("refresh_token")
        assert s.post(f"{API}/auth/refresh", timeout=30).status_code == 200
        assert request_with_retry("POST", f"{API}/auth/refresh",
                                  cookies={"refresh_token": old}).status_code == 401

    def test_password_change_revokes_other_sessions(self, admin_s):
        account = create_account(admin_s, "rotate")
        creds = {"email": account["email"], "password": account["password"]}
        s1 = session(creds)
        s2 = session(creds)
        replacement = f"Next-{uuid.uuid4().hex[:12]}"
        assert s1.post(f"{API}/auth/change-password", json={
            "current_password": account["password"], "new_password": replacement}, timeout=30).status_code == 200
        assert s2.get(f"{API}/auth/me", timeout=30).status_code == 401
        assert login(creds).status_code == 401
        assert login({"email": account["email"], "password": replacement}).status_code == 200
