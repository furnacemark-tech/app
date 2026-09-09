"""Iteration 8 focused verification of the review-request items."""
import os
import time
import pytest
import requests

from conftest import run_db
from database import db

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = ("admin@lims.local", "Admin@123")
QA = ("qa@lims.local", "Qa@12345")
QC = ("qc@lims.local", "Qc@12345")

@pytest.fixture(autouse=True)
def clear_login_attempts():
    run_db(lambda: db.login_attempts.delete_many({}))
    yield


def clear_must_change(email):
    run_db(
        lambda: db.users.update_one(
            {"email": email},
            {"$set": {"must_change_password": False}},
        )
    )


def login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    return s, r


def auth(session, token):
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


def test_provisioning_status():
    r = requests.get(f"{BASE}/auth/provisioning-status")
    assert r.status_code == 200
    data = r.json()
    assert data.get("administrator_exists") is True
    assert data.get("first_run_available") is False


def test_first_run_403_for_strong_and_weak():
    r = requests.post(f"{BASE}/auth/first-run", json={
        "email": "someone@example.com", "name": "X", "initials": "SO",
        "password": "Str0ngP@ss123!"})
    assert r.status_code == 403
    r = requests.post(f"{BASE}/auth/first-run", json={
        "email": "someone@example.com", "name": "X", "initials": "SO",
        "password": "abc"})
    assert r.status_code == 403


def test_default_credentials_rejected():
    for pw in ["admin123", "password", "changeme", "Admin123", "Password1", "admin"]:
        r = requests.post(f"{BASE}/auth/login",
                          json={"email": "unknown_user@example.com", "password": pw})
        assert r.status_code in (401, 429), f"pw {pw} returned {r.status_code}"


def test_no_password_in_login_me_users():
    _, r = login(*ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "password" not in body.get("user", {})
    assert "password_hash" not in body.get("user", {})
    tok = body["access_token"]
    s = auth(requests.Session(), tok)
    me = s.get(f"{BASE}/auth/me")
    assert me.status_code == 200
    j = me.json()
    assert "password" not in j and "password_hash" not in j
    ur = s.get(f"{BASE}/users")
    assert ur.status_code == 200
    for u in ur.json():
        assert "password" not in u
        assert "password_hash" not in u


def test_qa_cannot_create_user_or_change_role():
    clear_must_change("qa@lims.local")
    s, r = login(*QA)
    assert r.status_code == 200, r.text
    auth(s, r.json()["access_token"])
    cr = s.post(f"{BASE}/users", json={"email": "TEST_hax@example.com",
                                       "name": "x", "initials": "XX", "role": "qc"})
    assert cr.status_code == 403
    # role change attempt on qc user id (get from admin listing) - QA should be forbidden
    admin_s, ar = login(*ADMIN)
    auth(admin_s, ar.json()["access_token"])
    users = admin_s.get(f"{BASE}/users").json()
    qc_id = next(u["id"] for u in users if u["email"] == "qc@lims.local")
    rr = s.patch(f"{BASE}/users/{qc_id}", json={"role": "admin"})
    assert rr.status_code == 403


def test_unauthenticated_users_401():
    assert requests.get(f"{BASE}/users").status_code == 401


def test_logout_revokes_access_and_refresh_cookie():
    s, r = login(*ADMIN)
    tok = r.json()["access_token"]
    refresh_cookies = {k: v for k, v in s.cookies.items()}
    auth(s, tok)
    assert s.get(f"{BASE}/auth/me").status_code == 200
    lo = s.post(f"{BASE}/auth/logout")
    assert lo.status_code == 200
    # Bearer no longer works
    s.headers.update({"Authorization": f"Bearer {tok}"})
    s.cookies.clear()
    assert s.get(f"{BASE}/auth/me").status_code == 401
    # Replay refresh cookie in a fresh session
    s2 = requests.Session()
    for k, v in refresh_cookies.items():
        s2.cookies.set(k, v)
    rr = s2.post(f"{BASE}/auth/refresh")
    assert rr.status_code == 401


def test_refresh_rotation_old_refresh_rejected():
    s, r = login(*ADMIN)
    old_cookies = {k: v for k, v in s.cookies.items()}
    r1 = s.post(f"{BASE}/auth/refresh")
    assert r1.status_code == 200, r1.text
    s2 = requests.Session()
    for k, v in old_cookies.items():
        s2.cookies.set(k, v)
    rr = s2.post(f"{BASE}/auth/refresh")
    assert rr.status_code == 401
    # cleanup
    auth(s, r1.json().get("access_token", ""))
    s.post(f"{BASE}/auth/logout")


def _create_user(admin_session, email, role="qc"):
    return admin_session.post(f"{BASE}/users", json={
        "email": email, "name": "T", "initials": "TT", "role": role})


def test_temp_password_flow():
    admin_s, ar = login(*ADMIN)
    auth(admin_s, ar.json()["access_token"])
    email = f"TEST_temp_{int(time.time()*1000)}@example.com"
    cr = _create_user(admin_s, email)
    assert cr.status_code in (200, 201), cr.text
    body = cr.json()
    assert body.get("temporary_password_issued") is True
    assert "password" not in body
    assert "password_hash" not in body
    uid = body["id"]
    # Set a known temp password by admin PATCH so we can exercise the flow
    known_temp = "Tmp#Aa12345!"
    upd = admin_s.patch(f"{BASE}/users/{uid}", json={"password": known_temp})
    assert upd.status_code == 200, upd.text
    upd_body = upd.json() if upd.text else {}
    assert "password" not in upd_body
    assert "password_hash" not in upd_body

    # Login user with temp password
    us, ur = login(email, known_temp)
    assert ur.status_code == 200, ur.text
    assert ur.json().get("must_change_password") is True
    utok = ur.json()["access_token"]
    auth(us, utok)
    # Any protected call besides auth/me,logout,change-password should be blocked with 403 "temporary password"
    blocked = us.get(f"{BASE}/samples")
    assert blocked.status_code == 403
    assert "temporary" in blocked.text.lower()

    # Wrong current password -> 401, unchanged
    bad = us.post(f"{BASE}/auth/change-password",
                  json={"current_password": "wrong-pw", "new_password": "NewStrong#Pw123"})
    assert bad.status_code == 401
    # Temp password still works
    _, verify = login(email, known_temp)
    assert verify.status_code == 200

    # Correct change
    new_pw = "NewStrong#Pw123"
    ok = us.post(f"{BASE}/auth/change-password",
                 json={"current_password": known_temp, "new_password": new_pw})
    assert ok.status_code == 200, ok.text

    # Old temporary no longer works
    fail = requests.post(f"{BASE}/auth/login", json={"email": email, "password": known_temp})
    assert fail.status_code in (401, 429)

    # New password works and normal API access restored
    us2, ur2 = login(email, new_pw)
    assert ur2.status_code == 200
    auth(us2, ur2.json()["access_token"])
    me = us2.get(f"{BASE}/auth/me")
    assert me.status_code == 200
    # Not blocked anymore
    samples = us2.get(f"{BASE}/samples")
    assert samples.status_code == 200

    # cleanup: deactivate
    admin_s.patch(f"{BASE}/users/{uid}", json={"active": False})


def test_deactivate_invalidates_sessions_and_blocks_login():
    admin_s, ar = login(*ADMIN)
    auth(admin_s, ar.json()["access_token"])
    email = f"TEST_deact_{int(time.time()*1000)}@example.com"
    cr = _create_user(admin_s, email)
    uid = cr.json()["id"]
    temp = "Tmp#Aa12345!"
    admin_s.patch(f"{BASE}/users/{uid}", json={"password": temp})
    us, ur = login(email, temp)
    assert ur.status_code == 200
    auth(us, ur.json()["access_token"])
    assert us.get(f"{BASE}/auth/me").status_code == 200
    admin_s.patch(f"{BASE}/users/{uid}", json={"active": False})
    assert us.get(f"{BASE}/auth/me").status_code == 401
    lr = requests.post(f"{BASE}/auth/login", json={"email": email, "password": temp})
    assert lr.status_code == 403
