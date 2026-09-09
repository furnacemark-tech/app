"""Fail-closed utilities for disposable backend test databases."""
import re
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Dict

import requests
from pymongo import MongoClient


TEST_DATABASE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,47}_test_[a-f0-9]{12,32}$")


class DatabaseSafetyError(RuntimeError):
    """Raised when a test database name cannot be proven safe."""


def validate_test_database_name(test_db_name: str, preview_db_name: str) -> str:
    if not preview_db_name or not preview_db_name.strip():
        raise DatabaseSafetyError("The preview database name must be resolved before tests run.")
    if not test_db_name or not test_db_name.strip():
        raise DatabaseSafetyError("LIMS_TEST_DB_NAME is required for every backend test run.")

    resolved_name = test_db_name.strip()
    if resolved_name == preview_db_name.strip():
        raise DatabaseSafetyError(
            "The disposable test database must never equal the preview database."
        )
    if "_test_" not in resolved_name or not TEST_DATABASE_PATTERN.fullmatch(resolved_name):
        raise DatabaseSafetyError(
            "The test database must match ^[a-z][a-z0-9_]{0,47}_test_[a-f0-9]{12,32}$ exactly."
        )
    return resolved_name


def make_disposable_database_name(preview_db_name: str) -> str:
    if not preview_db_name or not re.fullmatch(r"[a-z][a-z0-9_]{0,47}", preview_db_name):
        raise DatabaseSafetyError(
            "The preview database name is unresolved or cannot form a safe test name."
        )
    candidate = f"{preview_db_name}_test_{uuid.uuid4().hex}"
    return validate_test_database_name(candidate, preview_db_name)


def reserve_test_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def collection_counts(mongo_url: str, database_name: str) -> Dict[str, int]:
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=10_000)
    try:
        database = client[database_name]
        return {
            collection: database[collection].count_documents({})
            for collection in sorted(database.list_collection_names())
        }
    finally:
        client.close()


def database_exists(mongo_url: str, database_name: str) -> bool:
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=10_000)
    try:
        return database_name in client.list_database_names()
    finally:
        client.close()


def drop_disposable_database(client: MongoClient, test_db_name: str, preview_db_name: str) -> None:
    resolved_name = validate_test_database_name(test_db_name, preview_db_name)
    client.drop_database(resolved_name)


@dataclass
class IsolatedTestServer:
    backend_dir: str
    mongo_url: str
    preview_db_name: str
    test_db_name: str
    port: int
    test_run_id: str
    process: subprocess.Popen | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        environment = {
            "MONGO_URL": self.mongo_url,
            "DB_NAME": self.test_db_name,
            "LIMS_TEST_DB_NAME": self.test_db_name,
            "LIMS_TEST_RUN_ID": self.test_run_id,
            "COOKIE_SECURE": "false",
        }
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--log-level",
                "warning",
            ],
            cwd=self.backend_dir,
            env={**__import__("os").environ, **environment},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        health_url = f"{self.base_url}/api/auth/provisioning-status"
        for _ in range(50):
            if self.process.poll() is not None:
                raise RuntimeError("The isolated test server exited before becoming healthy.")
            try:
                if requests.get(health_url, timeout=1).status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(0.2)
        self.stop()
        raise RuntimeError("The isolated test server did not become healthy.")

    def stop(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)

    def restart(self) -> None:
        self.stop()
        self.start()