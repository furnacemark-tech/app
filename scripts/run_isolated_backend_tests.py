"""Run backend tests against one disposable database and local API server."""
import argparse
import os
import subprocess
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from test_isolation import (
    IsolatedTestServer,
    collection_counts,
    database_exists,
    drop_disposable_database,
    make_disposable_database_name,
    reserve_test_port,
    validate_test_database_name,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pytest_args", nargs="*", default=["tests"])
    arguments = parser.parse_args()

    load_dotenv(BACKEND_DIR / ".env")
    mongo_url = os.environ.get("MONGO_URL")
    preview_db_name = os.environ.get("DB_NAME")
    if not mongo_url or not preview_db_name:
        raise RuntimeError("MONGO_URL and DB_NAME must resolve before isolated tests can start.")

    test_db_name = make_disposable_database_name(preview_db_name)
    test_db_name = validate_test_database_name(test_db_name, preview_db_name)
    test_run_id = uuid.uuid4().hex
    port = reserve_test_port()
    preview_before = collection_counts(mongo_url, preview_db_name)
    print(f"PREVIEW_COUNTS_BEFORE={preview_before}")
    print(f"ISOLATED_TEST_DB={test_db_name}")
    print(f"ISOLATED_TEST_SERVER=http://127.0.0.1:{port}")

    environment = os.environ.copy()
    environment.update(
        {
            "LIMS_PREVIEW_DB_NAME": preview_db_name,
            "LIMS_TEST_DB_NAME": test_db_name,
            "LIMS_TEST_RUN_ID": test_run_id,
            "LIMS_TEST_SERVER_PORT": str(port),
            "COOKIE_SECURE": "false",
        }
    )
    result = None
    try:
        seed_result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "seed_test_accounts.py")],
            cwd=ROOT,
            env={**environment, "LIMS_ENABLE_TEST_ACCOUNTS": "true"},
            check=False,
        )
        if seed_result.returncode != 0:
            return seed_result.returncode
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-n", "0", *arguments.pytest_args],
            cwd=BACKEND_DIR,
            env=environment,
            check=False,
        )
    finally:
        if database_exists(mongo_url, test_db_name):
            client = MongoClient(mongo_url, serverSelectionTimeoutMS=10_000)
            try:
                drop_disposable_database(client, test_db_name, preview_db_name)
            finally:
                client.close()

        preview_after = collection_counts(mongo_url, preview_db_name)
        print(f"PREVIEW_COUNTS_AFTER={preview_after}")
        print(f"PREVIEW_COUNTS_UNCHANGED={preview_before == preview_after}")
        print(f"DISPOSABLE_DATABASE_REMOVED={not database_exists(mongo_url, test_db_name)}")

    return result.returncode if result else 1


if __name__ == "__main__":
    raise SystemExit(main())