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

Deployment through the official plugin passed in an authorized sandbox;
setup was connected on Python 3.13. Account, destination, group, connection,
package and completed-sync identifiers are omitted from this public report.

The cloud suite completed successfully, with completed sync-history records
retained in private local evidence. Final safety guards were verified locally
and deployed, followed by SDK and cloud smoke checks. Destination SQL queries
were outside the scope of those runs. Counts below are expected results,
not queried destination assertions. Initial source/snapshot count was **80**:
64 baseline rows + 8 composite-key test rows + 8 simple-key test rows. During history,
one update, one insert and one delete leave **80 active rows**, with one expected
soft-deleted row in the dedicated test tables after CDC handoff.

| Stage | End phase | Expected active rows |
| --- | --- | --- |
| handover-history-1 | snapshot | batch in progress |
| handover-history-2 | snapshot | 80 |
| handover-history-3 | streaming | 80 |
| handover-history-handoff | streaming | 80 |
| handover-cdc-insert | streaming | 81 |
| handover-cdc-null | streaming | 81 |
| handover-cdc-rollback | streaming | 81 |
| handover-cdc-delete | streaming | 80 |
| handover-cdc-key-moves | streaming | 80 |
| handover-cdc-lob | streaming | 80 |
| handover-checkpoint-replay | streaming | 80 |
| handover-ddl-detect | snapshot | batch in progress |
| handover-ddl-history | streaming | 80 |
| handover-ddl-handoff | streaming | 80 |
| handover-ddl-cleanup-detect | snapshot | batch in progress |
| handover-ddl-cleanup-history | streaming | 80 |
| handover-ddl-cleanup-handoff | streaming | 80 |
| handover-owned-row-cleanup | streaming | 64 |
| handover-restored-history | streaming | 64 |
| handover-restored-cdc | streaming | 64 |
| handover-final-package | streaming | 64 |

All listed new-build cloud syncs completed successfully. The connection is paused
with its original baseline-table scope restored using an explicit six-column
selection.
An additional historical reload and CDC check aligned the restored scope and state.
The baseline table remains at 64 rows; both owned test tables are retained empty.
Temporary
DDL test columns were removed; the tested VARCHAR widening remains on the empty,
task-owned table. Approved archive retention remains 24 hours.


The CDC SCN span was explicitly set to 100 using the validated names
`logminer_initial_scn_span`, `logminer_min_scn_span`, and `logminer_max_scn_span`.
Earlier sandbox scripts used misspelled names; strict configuration validation
now rejects those instead of silently testing default spans. Seventeen previous
single-table SSH syncs are retained as earlier evidence, not new-build results.

Source LogMiner confirmed temporary-column ADD and DROP DDL records, both
with status 0. Environment-specific SCNs are retained in private test evidence.
Final package safety checks reject changes
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
