# Validation report

Validated on 2026-10-01. This is development/sandbox evidence and does not certify
production workloads or replace destination acceptance testing.

## Local verification

| Check | Result |
| --- | --- |
| Ruff lint and formatting | Passed |
| Mypy | Passed, 28 runtime source files and 2 packaging/deployment tools |
| Regression suite, including real loopback SSH | 195 passed, 1 Oracle test deselected |
| Read-only Oracle integration through SSH | 1 passed against the final restored source configuration |
| Installed SDK | 2.10.3; direct Operations calls verified |
| Local/deployed Python | 3.12 / 3.13 |
| Runtime dependencies | oracledb 4.0.2; Paramiko 4.0.0 |
| Oracle source | 19.32, thin mode, ARCHIVELOG, key supplemental logging |
| Official plugin | 2026.9.18.1, revision f4e1025abfaf0fb3043c05b0aaec574e5d46e142 |

Commands run from the connector directory:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy --ignore-missing-imports connector.py configuration.py errors.py identifiers.py oracle_client.py runtime_budget.py schema_models.py selection.py snapshot.py state.py type_mapping.py ssh_tunnel.py logminer schema_evolution tools
.venv/bin/pytest -q -m "not oracle"
ORACLE_TEST_CONFIGURATION=<ignored-local-configuration> .venv/bin/pytest -q -m oracle
```

The official plugin runner executed `fivetran debug` in an isolated source project.
Its DuckDB destination contained 64 baseline rows plus 8 rows in each of two
owned tables. Actual SDK operations for a simple and composite key-moving
transaction were 4 deletes and 2 complete upserts. The old composite key was
soft deleted, the new key retained unchanged scalar values and exact decimal
values, and restoration of those test keys also passed. SDK-reported Python debug peak memory
was approximately 0.07 GB for these small fixtures.

Live callback tests against Oracle passed: one SCN across resumed table snapshots,
concurrent historical update/insert/delete and CDC handoff, simple/composite key
moves, large excluded CLOB mixed with scalar updates, independent insert, explicit
null, rollback, delete, checkpoint replay, DDL historical reconciliation, removal
of an unselected column, and compatible VARCHAR widening. The mutation harness
reopened a connection after its own 120-second SSH lifetime expired; bounded
connector invocations retained their normal limit.

## Fivetran sandbox

Account `Fivetran_Sales_Sandbox`; destination `yev_apac_offsite`; group
`inactive_beware`; task connection `axe_joke`, name/schema
`oracle_logminer_csdk_dev_20260725`. Only this task-created connection was updated.
Deployment through the official plugin passed; setup was connected on Python 3.13.

Current new-build suite status: **passed**. Completed cloud syncs below are
matched to their completed sync-history IDs, not just success timestamps.
The matrix ran on package `wretch_uppermost`. Final safety guards were locally
verified and deployed as `fastness_regulation`; its final SDK and cloud smoke
checks are recorded separately. Cloud destination SQL queries were explicitly
excluded. Counts are expectations,
not queried destination assertions. Initial source/snapshot count was **80**:
64 HOUSEWARES + 8 composite-key test rows + 8 simple-key test rows. During history,
one update, one insert and one delete leave **80 active rows**, with one expected
soft-deleted row in the dedicated test tables after CDC handoff.

| Stage | Completed sync ID | End phase | Expected active rows |
| --- | --- | --- | --- |
| handover-history-1 | `dff05cb6-422a-4a63-b0a5-3cabb91ad3ec` | snapshot | batch in progress |
| handover-history-2 | `9c2975cd-e55e-48ef-a808-186d4eedc66e` | snapshot | 80 |
| handover-history-3 | `b9ff788b-c45c-4b52-8435-e312cc5fae93` | streaming | 80 |
| handover-history-handoff | `96c8f984-f0b8-4e08-97c7-27784db92ab7` | streaming | 80 |
| handover-cdc-insert | `15572a30-db4b-49b7-82f9-70c886b9848b` | streaming | 81 |
| handover-cdc-null | `e2fca012-2d74-4736-b336-fc4644e18241` | streaming | 81 |
| handover-cdc-rollback | `3dd34c04-881a-40f0-903f-92183c083890` | streaming | 81 |
| handover-cdc-delete | `e5db1cb4-b039-434b-98be-96d8e99fe301` | streaming | 80 |
| handover-cdc-key-moves | `4316c19b-728a-41e3-afbb-1133825a8893` | streaming | 80 |
| handover-cdc-lob | `ca466f64-b2b4-4399-9110-a11545c47bf6` | streaming | 80 |
| handover-checkpoint-replay | `cdbc3417-7f9d-40cc-8189-917f4402aaed` | streaming | 80 |
| handover-ddl-detect | `44398b1e-34cb-48fd-a14b-9d6c9195fc83` | snapshot | batch in progress |
| handover-ddl-history | `f0453f43-9839-4920-bc1d-2ae59864da12` | streaming | 80 |
| handover-ddl-handoff | `d864f355-81a0-4e55-ab52-ab100d731a3f` | streaming | 80 |
| handover-ddl-cleanup-detect | `158cb2d8-328b-4584-8711-40bb0b870914` | snapshot | batch in progress |
| handover-ddl-cleanup-history | `32c581f7-9054-48ae-8676-02be32996304` | streaming | 80 |
| handover-ddl-cleanup-handoff | `68162c1f-481b-4096-8a49-a464c69716f2` | streaming | 80 |
| handover-owned-row-cleanup | `0ebe2cfb-f0ee-40fc-bb81-973f405c5efd` | streaming | 64 |
| handover-restored-history | `cf0c661b-f864-4459-b010-47796e37bc91` | streaming | 64 |
| handover-restored-cdc | `80d1f129-8911-496c-b87f-22f40a702a77` | streaming | 64 |
| handover-final-package | `0a64eec8-3baa-4749-a12d-8bbf798ebf14` | streaming | 64 |

All listed new-build cloud syncs completed successfully. The connection is paused
with its original HOUSEWARES scope restored using an explicit six-column selection.
An additional historical reload and CDC check aligned the restored scope and state.
HOUSEWARES remains at 64 rows; both owned test tables are retained empty. Temporary
DDL test columns were removed; the tested VARCHAR widening remains on the empty,
task-owned table. Approved archive retention remains 24 hours.


The CDC SCN span was explicitly set to 100 using the validated names
`logminer_initial_scn_span`, `logminer_min_scn_span`, and `logminer_max_scn_span`.
Earlier sandbox scripts used misspelled names; strict configuration validation
now rejects those instead of silently testing default spans. Seventeen previous
single-table SSH syncs are retained as earlier evidence, not new-build results.

Source LogMiner confirmed temporary-column DDL records at SCNs `3161356` (ADD)
and `3162548` (DROP), both status 0. Final package safety checks reject changes
to DECIMAL parameters, preserve secret whitespace, and reject timezone-bearing
or submicrosecond timestamp types before historical emission.

Raw Oracle/SDK/cloud evidence is retained in ignored local test results. These
contain metadata and source identifiers and are intentionally omitted from the
client archive. Credentials/private keys were redacted and excluded from reports.

## Risks and remaining acceptance work

Delivery is at least once. Replay can repeat operations but should converge to
correct rows. Expired undo/redo, unsupported scalar grammar, incompatible selected
schema changes and missing privileges stop without advancing a new checkpoint.
Do not bypass failures by editing SCNs. DDL reloads can temporarily soft-delete
all selected rows; consumers must accommodate reconciliation.

Before production: query destination row values/deletion flags, size and stress
real workloads, validate recovery over outage/retention intervals, test complex
DDL/LOB variants applicable to the source, and confirm supported Oracle topology.
RAC, Hybrid sizing and destination transaction atomicity remain unproven. See
[limitations](limitations.md) and [operations](operational_runbook.md).
