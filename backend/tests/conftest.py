import asyncio
import os
import sys
from pathlib import Path

import pytest

# Add backend directory to Python path so 'from database import db' works
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from test_isolation import (
    IsolatedTestServer,
    DatabaseSafetyError,
    drop_disposable_database,
    validate_test_database_name,
)

PREVIEW_DB_NAME = os.environ.get("LIMS_PREVIEW_DB_NAME") or os.environ.get("DB_NAME")
TEST_DB_NAME = validate_test_database_name(
    os.environ.get("LIMS_TEST_DB_NAME", ""),
    PREVIEW_DB_NAME,
)
TEST_SERVER_PORT = int(os.environ.get("LIMS_TEST_SERVER_PORT", "0"))
TEST_RUN_ID = os.environ.get("LIMS_TEST_RUN_ID", "")
MONGO_URL = os.environ.get("MONGO_URL", "")
if not MONGO_URL or not TEST_SERVER_PORT or not TEST_RUN_ID:
    raise DatabaseSafetyError(
        "The isolated test runner must provide Mongo, port, and test-run values."
    )

os.environ["DB_NAME"] = TEST_DB_NAME
os.environ["REACT_APP_BACKEND_URL"] = f"http://127.0.0.1:{TEST_SERVER_PORT}"

from database import client, db

DB_LOOP = asyncio.new_event_loop()


def run_db(operation):
    async def run_operation():
        return await operation()

    return DB_LOOP.run_until_complete(run_operation())


@pytest.fixture(scope="session", autouse=True)
def isolated_test_server():
    server = IsolatedTestServer(
        backend_dir=str(backend_dir),
        mongo_url=MONGO_URL,
        preview_db_name=PREVIEW_DB_NAME,
        test_db_name=TEST_DB_NAME,
        port=TEST_SERVER_PORT,
        test_run_id=TEST_RUN_ID,
    )
    server.start()
    try:
        yield server
    finally:
        server.stop()
        drop_disposable_database(client, TEST_DB_NAME, PREVIEW_DB_NAME)


@pytest.fixture
def restart_isolated_test_server(isolated_test_server):
    return isolated_test_server.restart
