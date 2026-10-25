# Verified Connector SDK contracts and implementation scope

Reverified on 2026-10-01 against installed SDK 2.10.3. Official Codex plugin
2026.9.18.1 is installed and enabled; revision
`f4e1025abfaf0fb3043c05b0aaec574e5d46e142`.

`Connector(update, schema=None, configuration_form=None)` uses plain callbacks.
`Operations.upsert(table,data)`, `update(table,modified)`, `delete(table,keys)`,
`truncate(table)` and `checkpoint(state)` are direct calls, not generators.
The connector is a module-level variable named `connector`.
Partial updates preserve omitted fields; upsert nulls omitted fields. Deletes
and truncates are soft deletes. All primary-key columns must be included.
State contains JSON metadata and SCNs, never credentials or transaction payloads.
DECIMAL schema dictionaries explicitly carry precision/scale; installed SDK
`process_columns` writes both into gRPC decimal parameters. Frozen contracts reject
parameter changes even when the SDK type name remains DECIMAL.

The installed SDK has a 128 MiB gRPC ceiling and a 4 GiB local tester limiter.
Current deployment documentation specifies 4 GB SaaS RAM; connector safety
limits are deliberately smaller. Local Python 3.12 and deployed Python 3.13
are tested. Runtime dependencies are python-oracledb 4.0.2 and Paramiko 4.0.0;
SDK itself is supplied by Fivetran and omitted from runtime requirements.

User-approved scope superseding the original PLAN:
- Multiple primary-keyed tables and explicit column selection.
- Exclude LOB/LONG/XML payloads.
- DDL triggers historical reconciliation, retaining selected destination columns.
- Primary-key value moves soft-delete old keys and insert complete selected rows.
- No automatic propagation of destination schema changes.
- Bounded continuation assembly, database calls and scheduled invocations.

Material design: DDL causes an explicit checkpointed transition to a new
single-SCN historical reconciliation. This is not a silent SCN replacement
inside an existing snapshot. Every selected table is soft-truncated once at
initialization of that reconciliation; subsequent rows reactivate current keys.
Commit-SCN Flashback reads reconstruct full rows for key-moving transactions.
Required undo and redo must remain available; errors stop without skipping data.
Pre-snapshot commits encountered during replay are ignored, because the snapshot
already includes them. Post-snapshot commits still apply.

Earlier sandbox evidence: 17 deployed SSH syncs passed for the single-table
build. Fresh results for the amended scope are recorded in [validation](validation.md).
Cloud counts are expected, not destination-queried.

Sources:
- https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-operations
- https://fivetran.com/docs/connector-sdk/deploying-connectors
- https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOGMNR_CONTENTS.html
- https://python-oracledb.readthedocs.io/en/v4.0.2/api_manual/connection.html
- https://docs.paramiko.org/en/4.0/api/client.html

Installation verification: the official plugin was already installed through the
Codex plugin system and enabled. `codex plugin list` confirmed its version and
revision; no project reinitialization or plugin replacement was needed. Python
inspection confirmed SDK signatures and its DECIMAL/gRPC conversion code.

Installed CLI `fivetran deploy --help` was verified: it accepts destination and
connection names, `--python`/`--python-version`, and `--non-interactive`; it has
no `--connection-id` flag. The official plugin wrapper accepts a connection ID
and resolves deployment values. Installed CLI defaults to Python 3.13 while
current online documentation says 3.14; explicitly select tested Python 3.13.

Timestamp guard: default python-oracledb timestamp fetches do not retain timezone
information, and Python/SDK datetime representation is limited to microseconds.
Selected timezone-bearing timestamps and precision above six digits therefore
fail during discovery. Unselected types can remain in source metadata. See the
[driver SQL execution reference](https://python-oracledb.readthedocs.io/en/v4.0.0/user_guide/sql_execution.html).
