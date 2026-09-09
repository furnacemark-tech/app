# Sensitive recovery instructions

This archive can contain credentials, password hashes, session data, audit data, and laboratory data. Keep it outside Git.

Restore only to a new, empty `recovery_` database—not preview. Verify the target name and counts first.

```bash
mongorestore --uri="$MONGO_URL" --archive="preview_database_backup_2026-09-09.archive.gz" --gzip --nsFrom="test_database.*" --nsTo="$RECOVERY_DB.*"
```

Do not restore over preview without approved change control.
