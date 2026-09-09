"""Create LIMS test accounts. TEST ENVIRONMENTS ONLY.

This script is never imported by the application and is not run at startup.
It refuses to run unless LIMS_ENABLE_TEST_ACCOUNTS=true, and it never changes
the password of an account that already exists.

Usage:  LIMS_ENABLE_TEST_ACCOUNTS=true python3 /app/scripts/seed_test_accounts.py
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
sys.path.insert(0, str(ROOT / "backend"))

from test_isolation import DatabaseSafetyError, validate_test_database_name

TEST_ACCOUNTS = [
    ("admin@lims.local", "Admin@123", "System Administrator", "SA", "admin"),
    ("qa@lims.local", "Qa@12345", "Quality Assurance", "QA", "qa"),
    ("qc@lims.local", "Qc@12345", "Mark Furnace", "MF", "qc"),
]


async def main() -> int:
    if os.environ.get("LIMS_ENABLE_TEST_ACCOUNTS", "false").lower() != "true":
        print("Refusing to run: set LIMS_ENABLE_TEST_ACCOUNTS=true in a test environment only.")
        return 1
    preview_db_name = os.environ.get("LIMS_PREVIEW_DB_NAME") or os.environ.get("DB_NAME")
    test_db_name = os.environ.get("LIMS_TEST_DB_NAME", "")
    try:
        resolved_db_name = validate_test_database_name(test_db_name, preview_db_name)
    except DatabaseSafetyError as error:
        raise RuntimeError(
            "seed_test_accounts.py is limited to a validated disposable test database."
        ) from error
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[resolved_db_name]
    created, skipped = [], []
    for email, password, name, initials, role in TEST_ACCOUNTS:
        if await db.users.find_one({"email": email}):
            skipped.append(email)
            continue
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "email": email, "name": name, "initials": initials,
            "role": role, "active": True, "must_change_password": False,
            "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
            "created_at": datetime.now(timezone.utc).isoformat(), "created_via": "TEST_SEED"})
        created.append(email)
    print(f"created={created} skipped_existing={skipped}")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
