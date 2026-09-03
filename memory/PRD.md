# SYNTH LIMS — PRD

## Original problem statement
Based on an Excel workbook (LIMS_v0.5.4.4 - Validation and state tracking.xlsm), create a fully functioning LIMS: multiple users, sample types and specifications, secure login (QC/QA/Admin) with role-controlled access, fully auditable data entries. Extended by follow-up requirements into a complete batch release / Certificate of Analysis workflow.

## User choices
- JWT email/password auth with roles
- Light, data-dense enterprise UI
- Generic editable sample types/specs

## Architecture
- Backend: FastAPI — `/app/backend/server.py` (auth, users, samples, specs, audit) + `/app/backend/batches.py` (products/spec versions, instruments, customers, batches, C of A, deliveries)
- MongoDB (motor), bcrypt + PyJWT, httpOnly cookies with Bearer fallback
- Frontend: React + Tailwind + shadcn/ui, react-router, recharts, sonner
- Collections: users, sample_points, parameters, specifications, samples, products, spec_versions, instruments, customers, batches, audit_trail, oos_log, login_attempts

## Roles
- QC: register samples/batches, enter and amend results, confirm instrument, submit to QA, release when all checks pass
- QA: review, return with required actions, investigate, approve/release/reject, amend production date, authorise replacement C of A, record C of A delivery, cancel batches (pre-C of A only)
- Admin: users, customers and contacts, instruments, product specifications

## Implemented
### Iteration 1 (sample workflow)
- Login with brute-force lockout, role-gated nav and routes
- Samples with REC-YYYYMMDD-NNNN ids, spec-driven PASS/WARN/FAIL evaluation, QA sign-off locking, OOS log, dashboard KPIs, versioned specifications, audit trail, admin user management, CoA print view

### Iteration 2 (batch release & C of A)
- Statuses: DRAFT, SUBMITTED, RETURNED, APPROVED, RELEASED, ON_HOLD, CANCELLED
- Product specifications with fixed shelf-life period + shelf_life_required flag; amendments effective immediately, versioned with original/new value, reason, user, time
- Production date entered by QC selects the spec version active on that date; expiry auto-calculated and read-only; QA-only production date amendment with reason recalculates expiry
- Batch keeps applied spec version, shelf-life and expiry permanently; later spec changes never alter existing batches
- Instrument register with calibration/service dates; release blocked when overdue
- QC release only when all results in spec, all checks present and instrument in date; otherwise batch goes ON_HOLD for QA
- QA investigation: issue, root cause, impact, corrective action, decision; return to QC with required actions; QC amendments retain original value, new value, mandatory reason, user, time; only QA releases or rejects afterwards
- Self-approval prevented; QC cannot use QA endpoints
- C of A revisions: replacement authorised by QA supersedes the original with link and reason; active certificate shows "Ready for QA to Send"; superseded certificates can never be sent
- Manual delivery records per recipient (saved contacts or manual), with revision, QA user and timestamp; resends create new records
- Customers/contacts Admin-only for writes, viewable and selectable by QC/QA
- Customer locked at batch creation (exclusive products); multi-customer products issue separate C of As per customer
- Cancellation QA-only with reason, status at cancellation and optional replacement batch link; blocked once a C of A exists (post-release handled outside the LIMS)
- Full batch history plus global audit trail for every action

### Iteration 3 (reporting & oversight)
- Certificate of Analysis PDF per revision (reportlab): active certificates render full data, superseded revisions are stamped "SUPERSEDED — NOT VALID FOR ISSUE", products without shelf life omit shelf-life/expiry rows; downloads logged as COA_PDF_DOWNLOADED
- QA Work Queues screen: batches awaiting review, on hold/returned, certificates ready for QA to send, and replacement-C-of-A-to-authorise callout
- Stability alerts on the dashboard and `/api/alerts/expiring`: released shelf-life batches with days remaining and WARNING/CRITICAL/EXPIRED severity
- Batch report CSV export covering status, dates, shelf life, spec version, customer, instrument, results, release, holds, certificate revisions, deliveries and cancellations; audited as EXPORT_BATCH_REPORT

## Verification
- iteration_1.json: 33/33 backend, frontend 100%
- iteration_2.json: 70/70 backend, frontend 100%
- iteration_3.json: 88/88 backend, frontend 100%, no open issues
- iteration_4.json: code-review remediation regression — 88/88 backend, frontend 100% (one low-priority duplicate React key reported and then fixed)

## Code quality remediation (iteration 4)
- Auth token no longer persisted in localStorage: httpOnly cookies plus an in-memory Bearer fallback (`setAccessToken`)
- AuthContext value memoized, logout failure logged instead of silently swallowed
- BatchDetail split into `BatchHeader`, `CoaSection`, `BatchHistory`; recipient list memoized; stable list keys
- Effect dependencies made exhaustive via `useCallback` loaders (Batches, Samples, Specifications)
- Backend complexity split: `validate_qa_decision` / `qa_updates_for`, `build_result` / `confirm_instrument`, `_coa_summary_rows` / `_coa_result_rows`, `batch_csv_row`, `evaluate_numeric`; `audit()` argument list reduced
- Hold reasons now name the specific missing parameter

## QA OOS disposition workflow (iteration 7)
- Recorded results outside the applied specification stay `FAIL` permanently; batches now carry `overall_result` and `release_basis`
- QC release is refused whenever an unresolved OOS exists; the batch is forced to `ON_HOLD` with `investigation_required`
- The ordinary QA `release` decision also refuses an OOS batch and points to the disposition route
- `POST /api/batches/{id}/disposition/release-after-investigation` (QA only, server-enforced) requires issue, investigation conclusion, scientific/technical impact assessment, release justification, corrective action (or explicit not-applicable), at least one evidence/specialist reference, and explicit confirmation that the OOS result is accepted without changing its FAIL classification; QA cannot disposition their own work
- Release checks are partitioned: only the explicitly dispositioned specification failures are accepted; missing results, overdue/invalid instruments, missing shelf-life data and other controls still block
- Immutable record: `dispositions[]` + `active_disposition` retain the original value, original specification, spec version, original FAIL classification, investigation, justification, evidence, QA identity and timestamp; the earlier `BATCH_HELD_FOR_QA` event and the OOS log entry are retained
- C of A shows the result as FAIL, flags `contains_dispositioned_oos` with a `DISP-…` reference, and withholds confidential investigation detail unless `COA_INCLUDE_INVESTIGATION_DETAILS=true`
- CSV report gained Release basis, Dispositioned OOS reference and Dispositioned OOS parameters
- New suite `/app/backend/tests/test_oos_disposition.py` (37 tests) including the mineral acceptance scenario (spec 9.8–14.0 mg/g, result 9.6 mg/g, nutritional specialist assessment)
- iteration_7.json: 125/125 backend, frontend disposition surface 100%, no open issues

## Code quality remediation round 2 (iteration 6)
- Frontend decomposition: `useBatch` hook (loading, refresh, memoized lookups) plus `BatchHeader`, `BatchResultsTable`, `QcActionsPanel`, `QaActionsPanel`, `CoaSection`, `BatchHistory`, `SendCoaDialog`/`ReissueCoaDialog`, `NewBatchDialog`, `BatchTable`, `CustomerCard`, customer/instrument dialogs, `LoginForm`/`DemoAccounts`, `Sidebar`/`TopBar` — BatchDetail 634 → ~200 lines
- Backend decomposition: `release_checks` → `_result_problems`/`_instrument_problems`/`_shelf_life_problems`; `validate_qa_decision` → `_assert_decision_allowed`/`_assert_investigation_documented`; `amend_product` → `merged_spec_data`; `create_coa` → `coa_snapshot`/`supersede_existing`; `send_coa` → `_assert_coa_sendable`/`_delivery_record`; `save_results` → `build_sample_result`/`overall_result`; `startup` → `seed_indexes`/`seed_users`/`seed_reference_data`/`seed_specifications`
- Reviewed and rejected as false positives: `server.py:579` "undefined `s`" (list-comprehension variable) and the 25 "identity vs equality" hits (all are correct `is None` / `is not None` checks)
- iteration_6.json: 88/88 backend, frontend regression 100%, zero console errors, no open issues

## Backlog
- P1: per-day batch/record counters, stability alert email digest, QA queue filters
- P2: derived/calculated parameters, e-signature meaning statements, change control register, trend pages per sample point, split server.py into routers, FastAPI lifespan migration
