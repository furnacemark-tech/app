# Sensitive dry-run cleanup summary — no deletion executed

- Candidates: `9507`
- Confidence: `{'STRONG': 8251, 'CERTAIN': 1256}`
- AMBIGUOUS retained: `1`
- Orphans after dry run: `0`

## Child-to-parent order
1. `audit_trail` — 6237 delete, 2891 retain
2. `auth_sessions` — 505 delete, 2099 retain
3. `oos_log` — 86 delete, 18 retain
4. `spec_versions` — 122 delete, 16 retain
5. `samples` — 436 delete, 16 retain
6. `specifications` — 387 delete, 28 retain
7. `batches` — 724 delete, 0 retain
8. `instruments` — 70 delete, 4 retain
9. `parameters` — 219 delete, 7 retain
10. `customers` — 13 delete, 2 retain
11. `products` — 96 delete, 3 retain
12. `sample_points` — 318 delete, 6 retain
13. `users` — 294 delete, 14 retain

All Final Effluent records, unresolved OOS, shared seed-user evidence, seed masters, and AMBIGUOUS records remain excluded.
