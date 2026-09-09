# Isolated Backend Test Execution

Run backend tests only through:

```bash
python /app/scripts/run_isolated_backend_tests.py tests
```

The runner captures preview counts read-only, generates a full-match disposable
database name, starts a local test API server on a non-preview port, and drops
only that exact test database in `finally` cleanup.

`pytest` refuses to collect without all runner-provided values. Independent API
verification must use the runner's local URL. Browser verification against the
preview application must remain read-only and must not submit, approve, release,
or create records.