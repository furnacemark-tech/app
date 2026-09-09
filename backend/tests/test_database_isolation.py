"""Regression coverage for fail-closed disposable test-database isolation."""
import os

import pytest

from conftest import run_db
from database import db
from test_isolation import (
    DatabaseSafetyError,
    collection_counts,
    drop_disposable_database,
    validate_test_database_name,
)


class RecordingClient:
    def __init__(self):
        self.dropped = []

    def drop_database(self, database_name):
        self.dropped.append(database_name)


def test_startup_refuses_the_preview_database_name():
    preview = os.environ["LIMS_PREVIEW_DB_NAME"]
    with pytest.raises(DatabaseSafetyError, match="never equal"):
        validate_test_database_name(preview, preview)


@pytest.mark.parametrize("candidate", ["", "lims_sandbox", "lims_testing_abcdef123456"])
def test_startup_refuses_missing_or_invalid_test_markers(candidate):
    with pytest.raises(DatabaseSafetyError):
        validate_test_database_name(candidate, os.environ["LIMS_PREVIEW_DB_NAME"])


def test_disposable_database_is_active_and_preview_counts_do_not_change():
    preview_name = os.environ["LIMS_PREVIEW_DB_NAME"]
    before = collection_counts(os.environ["MONGO_URL"], preview_name)
    run_id = os.environ["LIMS_TEST_RUN_ID"]
    run_db(
        lambda: db.test_isolation_probes.insert_one(
            {"test_run_id": run_id, "scope": "disposable_database_only"}
        )
    )
    probe = run_db(lambda: db.test_isolation_probes.find_one({"test_run_id": run_id}))
    after = collection_counts(os.environ["MONGO_URL"], preview_name)
    assert os.environ["DB_NAME"] == os.environ["LIMS_TEST_DB_NAME"]
    assert os.environ["DB_NAME"] != preview_name
    assert probe["scope"] == "disposable_database_only"
    assert before == after


def test_cleanup_runs_when_a_test_operation_fails():
    client = RecordingClient()
    safe_name = "lims_test_deadbeefcafe"
    with pytest.raises(RuntimeError, match="intentional failure"):
        try:
            raise RuntimeError("intentional failure")
        finally:
            drop_disposable_database(client, safe_name, os.environ["LIMS_PREVIEW_DB_NAME"])
    assert client.dropped == [safe_name]


def test_cleanup_refuses_an_unsafe_database_name():
    client = RecordingClient()
    preview = os.environ["LIMS_PREVIEW_DB_NAME"]
    with pytest.raises(DatabaseSafetyError):
        drop_disposable_database(client, preview, preview)
    assert client.dropped == []