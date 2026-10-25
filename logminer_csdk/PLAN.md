# Oracle LogMiner connector for Fivetran Connector SDK — implementation plan

# Approved scope amendment — 2026-10-01

The user approved multiple primary-keyed tables, selected scalar columns only,
primary-key value changes as old-key soft-delete/new-key full-row insert, and
historical reconciliation when source DDL is detected. Destination DDL/schema
propagation and LOB replication are excluded. An explicit checkpointed DDL
resnapshot may establish a new SCN; existing snapshot pages must never silently
switch SCNs. Every reconciliation uses one SCN for all selected tables and
retains fixed selected-column contracts. The original safety, bounded execution,
redo/undo availability, transaction and checkpoint requirements below still apply.

Verified SDK 2.10.3 uses direct Operations calls from ordinary callbacks, rather
than yielding operations from a generator. SSH uses session-scoped transport
threads only; no redo poller or persistent worker runs between invocations.

Below is the fully consolidated Codex prompt.

You are implementing a production-oriented Fivetran Connector SDK connector for Oracle replication using:

1. Oracle Flashback Query for historical sync.
2. Oracle LogMiner for incremental change capture.
3. Fivetran Connector SDK state for durable checkpoints.
4. Scheduled, finite `update()` invocations rather than a persistent streaming daemon.
5. Online schema evolution for supported `ADD COLUMN` and compatible data-type changes.
6. At-least-once delivery with replay-safe recovery.

Build the connector in the current repository. Inspect the repository before modifying files.

Do not copy Debezium source code but reimplement the relevant design concepts cleanly in Python that meets the ConnectorSDK requirements

Inspect the existing implementation in `logminer_connector/`, review prior work, and apply the verified SDK contracts and correctness requirements in this plan.

# Phase 0: install the Fivetran Connector SDK Codex plugin

Install and use the official Fivetran Connector SDK Codex plugin from:

```text
https://github.com/fivetran/connector_sdk_tools/tree/main/codex
```

Before installing:

1. Inspect the plugin directory.
2. Read its README and installation instructions.
3. Follow the documented Codex installation method exactly.
4. Do not invent an installation path, skill format, configuration file or command.
5. Verify that Codex can discover and use the plugin.
6. Record the repository commit or plugin version in `docs/sdk_assumptions.md`.

Also determine whether the installed Fivetran CLI supports installing the Codex plugin through:

```bash
fivetran init
```

Prefer the official CLI installation path when it works with the installed CLI and SDK version.

If the project is already initialized and `fivetran init` could overwrite files:

1. Do not overwrite existing connector code.
2. Use a temporary directory to inspect generated files.
3. Copy or install only the plugin-related files required by the official instructions.
4. Document the exact installation process.

Do not begin core connector implementation until the plugin has been installed and verified.

# Critical Connector SDK execution model

This connector is not a continuously running Debezium-style process.

Fivetran invokes the connector’s `update(configuration, state)` generator according to the connection sync frequency.

Each invocation must:

```text
1. Load state.
2. Connect to Oracle.
3. Perform phase-appropriate validation.
4. Establish a fixed amount of work for the invocation.
5. Perform bounded snapshot or LogMiner processing.
6. Yield Fivetran operations incrementally.
7. Yield checkpoints only at safe boundaries.
8. Return normally.
```

Do not implement:

```python
while running:
    mine()
    sleep()
```

Do not create:

- a persistent daemon;
- an endless polling loop;
- background threads;
- background processes;
- internal schedulers;
- heartbeat loops;
- sleeping waits for new redo.

A loop inside one `update()` invocation is permitted only when bounded by explicit limits, such as:

```text
fixed invocation target SCN
maximum invocation duration
maximum mining windows
maximum snapshot rows
maximum memory budget
end of current table
completion of the historical snapshot
```

Every successful `update()` call must terminate.

# Invocation target model

At the beginning of an incremental invocation:

```text
start_scn = persisted replay-safe low watermark
target_scn = current Oracle SCN captured once
```

Process toward that fixed target.

Do not continually refresh the target SCN during the invocation. On an active database, that could prevent the function from ever finishing.

Conceptually:

```python
def update(configuration, state):
    runtime = RuntimeBudget.start(configuration)

    validate_configuration(configuration)

    client = OracleClient.connect(configuration)

    parsed_state = ConnectorState.load(state)

    if parsed_state.requires_snapshot:
        validate_snapshot_requirements(client, parsed_state)
        yield from run_bounded_snapshot(
            client=client,
            state=parsed_state,
            runtime=runtime,
        )
        return

    validate_streaming_requirements(client, parsed_state)

    target_scn = client.current_scn()

    yield from run_bounded_logminer_sync(
        client=client,
        state=parsed_state,
        target_scn=target_scn,
        runtime=runtime,
    )

    return
```

If the invocation cannot reach `target_scn`, checkpoint a safe replay position and return. Continue from that position on the next scheduled invocation.

# Inspect the actual SDK before implementing

Before writing connector logic:

1. Determine the installed `fivetran-connector-sdk` version.
2. Inspect the installed package.
3. Inspect official examples.
4. Read the installed Fivetran Codex plugin instructions.
5. Verify the exact API and behavior of:
   - `Connector`;
   - `schema()`;
   - `update()`;
   - `op.upsert()`;
   - `op.delete()`;
   - `op.checkpoint()`;
   - schema definitions;
   - configuration fields;
   - encrypted configuration fields;
   - logging;
   - local testing;
   - deployment.
6. Confirm supported Python versions.
7. Confirm current execution time and memory constraints.
8. Confirm operation-size constraints.
9. Confirm checkpoint and operation ordering behavior.
10. Confirm whether an `upsert` containing a subset of columns preserves omitted destination values or replaces the whole row.
11. Confirm whether schema changes can be published during `update()`, or only through a future `schema()` execution.
12. Confirm whether Fivetran invokes `schema()` automatically after a schema-related failure.

Do not invent SDK APIs.

Write all verified findings to:

```text
docs/sdk_assumptions.md
```

Include source references for each important assumption.

# No separate validation callback

Do not create a fictitious Connector SDK callback such as:

```python
validate()
test_connection()
```

Perform validation through `schema()` and `update()`.

## Validation in `schema()`

Validate only what is needed for deterministic schema discovery:

```text
configuration completeness
Oracle connectivity
included and excluded schema filters
included and excluded table filters
table accessibility
column discovery
primary-key discovery
supported Oracle types
keyless-table policy
```

Avoid starting LogMiner from `schema()` unless required by a verified SDK workflow.

## Validation in `update()`

At the beginning of the relevant phase, validate:

```text
Oracle version
ARCHIVELOG mode
supplemental logging
LogMiner privileges
dynamic performance view access
Flashback Query support
required redo availability
persisted low-watermark recoverability
object identity consistency
pending schema-change state
```

Raise actionable errors naming the exact:

```text
privilege
Oracle setting
view
table
column
object ID
SCN
redo-log range
configuration field
unsupported type
```

# Runtime and deployment profiles

Support two explicit deployment profiles.

## Fivetran SaaS runtime

Assume approximately:

```text
Memory: about 1 GB
CPU: less than 0.5 vCPU
Local disk: ephemeral
```

Treat the currently documented limits as hard constraints after verifying them from official documentation.

The SaaS implementation must:

```text
yield rows immediately
avoid table-level accumulation
avoid large page accumulation
strictly bound transaction buffering
strictly bound deferred DDL buffering
strictly bound LOB sizes
strictly bound operation size
avoid relying on local disk for correctness
terminate predictably
fail safely before memory exhaustion
```

## Hybrid Deployment

Hybrid Deployment is strongly recommended when:

```text
transactions can be large
transactions are long-running
LogMiner output volume is high
source lag may require substantial catch-up
large LOBs must be replicated
transaction buffers can exceed SaaS memory
schema-change replay windows can be large
```

Document prominently:

> Correct LogMiner replication requires buffering a complete transaction until commit. The standard SaaS runtime may be unsuitable for Oracle workloads with large or long-running transactions. Hybrid Deployment is strongly recommended for those workloads.

Do not claim Hybrid Deployment is unlimited. Keep memory and transaction controls configurable.

# Oracle driver requirements

Use:

```text
python-oracledb in thin mode
```

For the SaaS runtime, treat thick mode as unsupported unless official runtime documentation proves Oracle Instant Client is available.

Do not:

```text
automatically fall back to thick mode
bundle Oracle Instant Client without explicit support
assume native Oracle libraries are installed
```

Verify thin mode at startup where appropriate:

```python
oracledb.is_thin_mode()
```

Document thin-mode limitations for:

```text
LOB handling
Oracle-specific types
authentication modes
advanced networking
some legacy database versions
some type conversion edge cases
```

Fail clearly for unsupported thin-mode functionality.

# Connector configuration

Stay below the Connector SDK configuration-field limit.

Use encrypted configuration fields for credentials.

Do not design a separate secrets-object API.

Start with a compact configuration such as:

```text
host
port
service_name
username
password

include_schemas
exclude_schemas
include_tables
exclude_tables

snapshot_mode
snapshot_fetch_size
snapshot_rows_per_invocation
snapshot_surrogate_keys

logminer_batch_initial_scn_span
logminer_batch_min_scn_span
logminer_batch_max_scn_span
max_mining_windows_per_invocation
max_invocation_seconds

archive_log_only

max_open_transactions
max_transaction_events
max_transaction_buffer_bytes
max_single_transaction_bytes

max_deferred_ddl_events
max_deferred_ddl_bytes

max_lob_bytes
max_operation_bytes
oversized_value_policy
lob_handling_mode

keyless_table_policy
schema_change_policy
deployment_profile

transaction_lookback_scn
```

Do not add speculative options.

Only add a field when:

```text
the implementation uses it
it has tests
its operational consequences are documented
```

Do not include:

```text
logminer_sleep_seconds
heartbeat_interval_seconds
```

Fivetran scheduling controls invocation frequency.

# Suggested project structure

Follow repository conventions, but prefer modular code similar to:

```text
connector.py
configuration.py
oracle_client.py
schema_discovery.py
snapshot.py
state.py
runtime_budget.py
type_mapping.py
identifiers.py
errors.py
logging_utils.py

logminer/
    session.py
    redo_log_selector.py
    query_builder.py
    continuation.py
    parser.py
    transaction_buffer.py
    watermarks.py
    models.py

schema_evolution/
    schema_history.py
    schema_diff.py
    ddl_detector.py
    ddl_transition.py
    type_compatibility.py
    schema_publisher.py
    models.py

tests/
    unit/
    integration/
    fixtures/

docs/
    architecture.md
    sdk_assumptions.md
    oracle_setup.md
    deployment_profiles.md
    state_model.md
    schema_evolution.md
    operational_runbook.md
```

# State model

Implement a compact versioned state object.

A representative model is:

```json
{
  "state_version": 1,
  "phase": "snapshot",
  "snapshot": {
    "snapshot_scn": "123456",
    "stream_start_scn": "123400",
    "table_index": 0,
    "current_table": "HR.EMPLOYEES",
    "last_key": ["1001"],
    "completed": false,
    "schema_fingerprints": {
      "HR.EMPLOYEES": "abc123"
    }
  },
  "streaming": {
    "low_watermark_scn": "123400",
    "processed_through_scn": "123900",
    "high_watermark_commit_scn": "123850"
  },
  "schema_history": {
    "HR.EMPLOYEES": {
      "previous": null,
      "active": {
        "version_id": "schema-v1",
        "valid_from_scn": "123456",
        "fingerprint": "abc123"
      },
      "pending": null
    }
  },
  "pending_schema_change": null
}
```

Use strings for SCNs if required for safe serialization.

Do not persist full transaction-event buffers in Connector SDK state.

Do not persist unbounded schema history in state.

Assume any in-memory transaction buffer or deferred DDL queue is lost when `update()` exits or crashes.

Therefore:

```text
replay from a safe low watermark
never checkpoint past unresolved transactions
never checkpoint past unresolved DDL
accept duplicate processing
never accept gaps
```

Implement:

```text
state serialization
state deserialization
version validation
state migrations
corruption detection
size tests
round-trip tests
```

# Oracle prerequisites

Determine and document the minimum required access.

Evaluate access to objects such as:

```text
V$DATABASE
V$LOG
V$LOGFILE
V$ARCHIVED_LOG
V$LOGMNR_CONTENTS
V$TRANSACTION
V$SESSION
V$MYSTAT
V$STATNAME
ALL_OBJECTS
ALL_TABLES
ALL_TAB_COLUMNS
ALL_CONSTRAINTS
ALL_CONS_COLUMNS
DBA_OBJECTS where genuinely required
DBMS_LOGMNR
DBMS_LOGMNR_D
```

Do not require broader privileges than needed.

Validate:

```text
ARCHIVELOG mode
supplemental logging
Flashback Query access
LogMiner package execution
dynamic performance views
captured-table access
primary-key metadata
redo retention
```

Document exact setup SQL in:

```text
docs/oracle_setup.md
```

# Historical sync

Historical sync must read all selected tables at one consistent SCN.

## Snapshot initialization

On the first snapshot invocation:

```text
1. Discover included tables.
2. Discover exact columns and primary keys.
3. Capture one Oracle snapshot SCN.
4. Capture immutable snapshot schema metadata.
5. Determine a safe streaming start SCN.
6. Persist snapshot state before substantial work.
7. Begin bounded table reads.
```

All tables must use the same:

```text
snapshot_scn
```

## Snapshot schema consistency

At snapshot initialization, persist:

```text
ordered explicit column list
Oracle types
precision and scale
nullability
primary key
object ID
data object ID where relevant
schema fingerprint
```

Reuse this exact projection across every scheduled snapshot invocation.

Do not rediscover and replace the snapshot projection midway through the snapshot.

If later DDL makes the original projection unavailable:

```text
stop
raise a resnapshot-required error
do not silently select a new SCN
```

## Flashback Query

Use explicit columns:

```sql
SELECT
    <explicit column list>
FROM <quoted owner>.<quoted table>
AS OF SCN :snapshot_scn
WHERE <keyset continuation predicate>
ORDER BY <stable key columns>
```

Do not use:

```text
SELECT *
OFFSET pagination
```

Use keyset pagination.

For composite keys, generate a correct lexicographic continuation predicate.

Yield each row immediately through the appropriate SDK operation.

Do not accumulate whole tables.

## Bounded snapshot invocations

A snapshot may span many `update()` calls.

Stop when reaching one or more limits:

```text
snapshot_rows_per_invocation
max_invocation_seconds
end of current table
end of all tables
```

Checkpoint:

```text
snapshot_scn
stream_start_scn
table index
current table
last emitted key
schema fingerprint
phase
```

Never capture a new snapshot SCN midway through the historical sync.

Document:

> A snapshot spanning multiple scheduled invocations requires Oracle undo to retain row versions for the original snapshot SCN for the full elapsed duration.

If Oracle raises:

```text
ORA-01555: snapshot too old
```

raise a typed `SnapshotTooOldError` that requires a controlled resnapshot.

## Snapshot row operation

Use the exact SDK operation verified from the installed SDK.

Historical rows will typically be emitted as idempotent `op.upsert()` operations keyed by the Oracle primary key.

Do not invent a historical-record API.

# Transactions open at the snapshot boundary

A transaction may:

```text
begin before the snapshot SCN
modify a captured row before the snapshot SCN
commit after the snapshot SCN
```

Example:

```text
transaction starts at SCN 90
transaction modifies row at SCN 95
snapshot SCN is 100
transaction commits at SCN 110
```

Starting LogMiner at SCN 100 could miss the early redo for that transaction.

Where reliable active transaction metadata is available, capture:

```text
transaction ID -> start SCN
```

Calculate:

```text
stream_start_scn =
    min(
        snapshot_scn,
        oldest relevant active transaction start SCN
    )
```

If reliable active-transaction discovery cannot be guaranteed, use a conservative configured lookback strategy:

```text
stream_start_scn = snapshot_scn - transaction_lookback_scn
```

Document:

```text
possible duplicate processing
required archive retention
remaining correctness limitations
```

Never choose a later start SCN merely to reduce replay.

# Snapshot completion

When the final table is complete:

```text
1. Yield a checkpoint marking snapshot completion.
2. Set phase to streaming.
3. Preserve the original stream_start_scn.
4. Return from update().
```

Start LogMiner on the next invocation.

Do not combine a long final snapshot step with an unbounded CDC catch-up step.

# Incremental LogMiner sync

Each invocation is a bounded catch-up operation.

## Invocation start

At the beginning of streaming:

```text
1. Load the replay-safe low watermark.
2. Validate that required redo is available.
3. Capture one fixed target SCN.
4. Initialize bounded in-memory transaction state.
5. Initialize schema-history state.
6. Process bounded SCN windows.
```

## Bounded mining loop

Use a finite loop conceptually like:

```python
target_scn = client.current_scn()
windows_processed = 0

while (
    state.streaming.processed_through_scn < target_scn
    and windows_processed < config.max_mining_windows_per_invocation
    and not runtime.nearly_exhausted()
):
    start_scn = choose_start_scn(state)
    end_scn = choose_window_end(
        start_scn=start_scn,
        target_scn=target_scn,
    )

    yield from process_logminer_window(
        start_scn=start_scn,
        end_scn=end_scn,
    )

    windows_processed += 1

yield safe_checkpoint()
return
```

Do not sleep.

Do not refresh the target SCN during the invocation.

# Adaptive SCN windows

Mine bounded SCN ranges.

Adapt within configured limits:

```text
low record volume:
    increase SCN span

high record volume:
    decrease SCN span
```

Track:

```text
start SCN
end SCN
records returned
DML records
commits
rollbacks
open transaction count
buffer bytes
oldest open transaction age
schema transitions
source lag
```

# Redo-log selection

Determine which online and archived logs cover:

```text
[start_scn, end_scn]
```

Support RAC only after explicitly testing thread ordering.

Detect missing redo and raise an error containing:

```text
required start SCN
required end SCN
oldest available SCN
affected redo thread
archive gap
whether resnapshot is required
```

Never silently skip unavailable redo.

# LogMiner session

Isolate session operations in a dedicated component.

Support:

```text
registering logs
starting LogMiner
ending LogMiner
querying V$LOGMNR_CONTENTS
session recreation
cleanup after failure
Oracle error classification
```

Keep procedure calls out of high-level orchestration.

# LogMiner ordering

Inspect the actual columns available in the supported Oracle versions.

Use deterministic ordering considering fields such as:

```text
SCN
COMMIT_SCN
RS_ID
SSN
CSF
XID
THREAD#
SEQUENCE#
```

Do not assume ordering solely by SCN is sufficient.

# Continuation records

Handle LogMiner continuation records such as those indicated by `CSF`.

Support:

```text
single-fragment records
two-fragment records
many-fragment records
restart around an incomplete fragment
```

Do not emit or parse incomplete logical SQL.

If an invocation ends with an incomplete continuation sequence:

```text
do not checkpoint beyond its first required SCN
replay it on the next invocation
```

# Transaction buffering

The default implementation must emit only committed changes.

Maintain a bounded transaction buffer:

```text
transaction ID
transaction start SCN
ordered DML events
estimated bytes
event count
last seen SCN
```

On DML:

```text
append to the relevant transaction buffer
```

On commit:

```text
order transaction events
resolve the applicable schema version for every event
emit all operations
advance high-watermark commit SCN
remove the transaction
```

On rollback:

```text
discard the transaction
```

Never emit uncommitted data.

# Cross-invocation transactions

A transaction may start in one invocation and commit in another.

Example:

```text
Invocation target SCN: 500

T1 starts at 100 and remains open.
T2 starts at 300 and commits at 400.
```

T2 can be emitted.

T1 cannot be emitted.

Checkpoint state:

```text
processed_through_scn = 500
high_watermark_commit_scn = 400
low_watermark_scn = 100
```

The next invocation must remine from SCN 100 to reconstruct T1.

It may see T2 again.

Destination correctness must be maintained through:

```text
idempotent upserts
idempotent soft deletes
safe replay
```

Never advance the low watermark beyond the oldest unresolved transaction.

# Transaction memory limits

Enforce:

```text
max_open_transactions
max_transaction_events
max_transaction_buffer_bytes
max_single_transaction_bytes
```

Estimate memory incrementally.

When a limit is exceeded:

```text
do not emit a partial transaction
do not discard events
do not advance the low watermark
raise a deterministic TransactionBufferLimitError
```

Include in the error:

```text
transaction ID
transaction start SCN
observed event count
estimated bytes
configured limit
deployment profile
recommendation to use Hybrid Deployment or smaller source transactions
```

Do not provide a `warn_and_continue` mode if it could cause data loss.

Do not use ephemeral local disk as a durability mechanism.

# Watermark model

Track distinct positions:

```text
processed_through_scn
high_watermark_commit_scn
low_watermark_scn
invocation_target_scn
```

## `processed_through_scn`

Highest redo position inspected.

It is not necessarily a safe restart position.

## `high_watermark_commit_scn`

Highest commit SCN whose complete transaction operations have been yielded.

## `low_watermark_scn`

Earliest redo SCN that may still be needed to reconstruct:

```text
open transactions
incomplete continuation records
pending schema transitions
deferred post-DDL DML
```

Conceptually:

```text
low_watermark_scn =
    min(
        next unread SCN,
        oldest unresolved transaction start SCN,
        earliest incomplete continuation SCN,
        earliest unresolved DDL replay SCN
    )
```

## `invocation_target_scn`

Fixed source target selected for the current invocation.

Do not treat it as the authoritative restart position.

# Checkpoint correctness

Yield `op.checkpoint()` only at replay-safe boundaries.

Do not checkpoint beyond:

```text
an unresolved transaction
an incomplete continuation record
an unresolved DDL
an unpublished schema change
a partially emitted transaction
a missing schema version
```

Checkpoint after:

```text
bounded snapshot chunks
completed snapshot tables
snapshot completion
fully processed mining windows
fully emitted committed transactions
successful schema transitions
runtime-budget early exits
target SCN completion
```

Verify actual SDK ordering guarantees between yielded operations and checkpoints.

Document the verified behavior.

# Fivetran operation semantics

Use the exact installed SDK API.

Expected mapping:

```text
historical row -> op.upsert()
Oracle INSERT -> op.upsert()
Oracle UPDATE -> op.upsert()
Oracle DELETE -> op.delete()
```

Fivetran deletes are soft deletes.

`op.delete()` marks:

```text
_fivetran_deleted = TRUE
```

Do not describe this as physical deletion.

Ensure primary-key values are included in delete operations.

Repeated upserts and deletes must be logically idempotent.

# Partial update semantics

Oracle LogMiner may report only changed columns.

The internal event model must distinguish:

```text
column absent from redo
column explicitly set to NULL
column present with a value
```

Use an explicit sentinel:

```python
UNSET = object()
```

Do not convert an absent column to `None`.

Verify how the installed SDK handles omitted fields in `op.upsert()`.

If omitted fields preserve existing destination values, emit only the safely known fields plus the key.

If `op.upsert()` replaces the whole row:

```text
reconstruct a complete after-image safely
or reject partial update processing
```

Do not guess.

# Primary keys and keyless tables

For each table:

```text
discover the source primary key
use it as the Fivetran primary key
validate type support
```

Default keyless-table policy:

```text
reject
```

Optional explicitly configured policies may include:

```text
surrogate snapshot key
append-only mode where valid
ROWID with documented limitations
```

Do not infer a key from all columns.

# Oracle type mapping

Implement a dedicated type mapping layer.

Support and test:

```text
NUMBER
FLOAT
BINARY_FLOAT
BINARY_DOUBLE
VARCHAR2
NVARCHAR2
CHAR
NCHAR
RAW
DATE
TIMESTAMP
TIMESTAMP WITH TIME ZONE
TIMESTAMP WITH LOCAL TIME ZONE
CLOB
NCLOB
BLOB
INTERVAL YEAR TO MONTH
INTERVAL DAY TO SECOND
XMLTYPE
JSON where supported
```

Preserve Oracle `NUMBER` precision and scale.

Do not convert arbitrary precision through Python binary floating point.

Classify mappings as:

```text
fully supported
supported with limits
lossy
unsupported
```

Fail schema discovery for unsupported included columns unless an explicit policy allows omission.

# LOB and operation-size limits

Verify the current SDK operation-size limit.

Assume a 128 MB transport ceiling only if confirmed by official documentation.

Implement smaller safety limits:

```text
max_lob_bytes
max_operation_bytes
```

Leave overhead for:

```text
serialization
column names
other row values
protobuf framing
Python object duplication
SDK processing
```

Apply limits to:

```text
BLOB
CLOB
NCLOB
RAW
XML
JSON
total serialized record size
```

Supported oversized-value policies may include:

```text
fail
set null and emit a warning
truncate text with an explicit marker
```

Default to:

```text
fail
```

Do not silently truncate or omit values.

# SQL_REDO parsing

Treat SQL redo parsing as a high-risk correctness component.

Do not use regular expressions as the only parser.

Create a parser abstraction supporting:

```text
quoted identifiers
escaped strings
NULL
numeric literals
Oracle dates
Oracle timestamps
hex values
changed-column updates
delete keys
continuation records
LOB operations
unsupported expressions
```

Prefer structured LogMiner columns where they avoid parsing.

For unsupported or ambiguous redo:

```text
do not guess
do not emit
do not advance beyond the required replay point
raise a typed RedoParseError
redact sensitive SQL from logs
```

Use real or representative LogMiner fixtures.

# Robust online DDL support

Implement online schema evolution for:

```text
ADD COLUMN
compatible data-type changes
```

The connector must guarantee:

```text
pre-DDL DML uses the old schema
post-DDL DML uses the new schema
the Fivetran schema is updated before post-DDL values are emitted
no stale metadata is used
```

# Supported online DDL scope

Initially support:

```text
ADD nullable column without a default
ADD nullable column with a deterministic literal default, only if fully tested
increase VARCHAR2 length
increase NVARCHAR2 length
increase CHAR length
increase NCHAR length
increase RAW length
compatible NUMBER precision increase
compatible NUMBER scale increase
compatible timestamp precision increase
```

Fail safely by default for:

```text
DROP COLUMN
RENAME COLUMN
ADD or DROP primary key
change primary-key columns
type-family changes
type narrowing
precision reduction
scale reduction
nullable to NOT NULL
non-deterministic defaults
sequence-based defaults
LOB-to-non-LOB changes
non-LOB-to-LOB changes
table rename
drop and recreate
TRUNCATE TABLE
partition exchange
online redefinition
object identity changes
```

# Schema-version model

Maintain immutable schema versions per table.

Each schema version must include:

```text
owner
table name
object ID
data object ID where relevant
schema version ID
valid-from SCN
valid-to SCN
ordered columns
Oracle column IDs
Oracle types
length
precision
scale
character semantics
nullability
default metadata
primary key
Connector SDK type mapping
fingerprint
```

Support:

```python
schema_for(
    table_identity,
    event_scn,
    commit_scn,
)
```

Never decode replayed redo solely using current `ALL_TAB_COLUMNS`.

# Schema-history retention

Connector state must remain compact.

Initially retain at least:

```text
previous schema
active schema
pending schema
validity SCNs
fingerprints
object identity
```

If replay requires a schema version no longer available:

```text
raise SchemaHistoryUnavailableError
require a controlled resnapshot
do not decode using the current schema
```

For Hybrid Deployment, optionally support an external durable schema-history store.

# DDL detection

Detect DDL in `V$LOGMNR_CONTENTS`.

Capture:

```text
DDL SCN
DDL commit SCN where available
owner
table name
object ID
data object ID where available
operation
SQL_REDO or equivalent
thread
sequence
RS_ID
SSN
```

Do not identify the affected table solely by parsing SQL text.

Use LogMiner and Oracle metadata fields where available.

# DDL transition barrier

When supported DDL affects an included table:

```text
1. Open a per-table transition barrier.
2. Stop checkpoint advancement beyond the DDL.
3. Complete only unambiguously pre-DDL work.
4. Defer or replay post-DDL work.
5. Rediscover the full table schema.
6. Compare old and new metadata.
7. Classify the change.
8. Publish or trigger publication of the Connector SDK schema.
9. Activate the new schema version.
10. Resume post-DDL DML.
```

While the barrier is open:

```text
pre-DDL DML:
    may use the old schema

post-DDL DML for the affected table:
    must not be emitted

unaffected tables:
    may continue only when transaction and checkpoint ordering remains safe
```

Barrier state must include:

```text
table identity
DDL SCN
DDL commit SCN
old schema version
candidate new version
publication status
safe replay SCN
deferred transaction IDs
deferred event count
```

# DDL ordering

Use verified Oracle and LogMiner ordering semantics.

Consider:

```text
event SCN
transaction start SCN
transaction commit SCN
DDL SCN
DDL commit SCN
RS_ID
SSN
redo thread
redo sequence
```

Do not select a schema based merely on whichever Oracle metadata is currently visible.

Add real Oracle integration tests for ordering.

# Schema rediscovery after DDL

After detecting DDL:

```text
1. Query fresh Oracle metadata.
2. Rediscover the complete table.
3. Rediscover columns.
4. Rediscover primary keys.
5. Retrieve object identity.
6. Compare with the active schema.
7. Confirm that the observed difference matches the detected DDL.
8. Build a candidate immutable schema version.
```

Do not patch only the parsed DDL column.

Always compare the complete table definition.

Reject unrelated or ambiguous differences.

# Connector SDK schema publication

Inspect the actual SDK and plugin to determine the supported workflow.

Do not invent:

```python
op.alter_schema(...)
```

Use one of two verified strategies.

## Strategy A: schema publication during `update()` is supported

If the SDK provides a documented mechanism:

```text
1. Build the new SDK table schema.
2. Publish it through the documented API.
3. Verify successful publication.
4. Persist the schema version and fingerprint.
5. Release the DDL barrier.
6. Emit post-DDL DML.
```

Do not release DML merely because a call was attempted.

## Strategy B: schema changes require a future `schema()` execution

If schema changes are published only through `schema()`:

```text
1. Detect the DDL.
2. Stop before emitting post-DDL DML.
3. Persist a pending-schema-change marker.
4. Checkpoint at or before the DDL.
5. Raise a typed SchemaRefreshRequiredError.
6. Ensure the next schema() includes the new definition.
7. On the next update(), verify the new schema fingerprint.
8. Remine from the safe replay SCN.
9. Reprocess the DDL and post-DDL DML.
```

Do not advance the low watermark beyond the DDL while publication is pending.

# Pending schema-change state

Persist compact state such as:

```json
{
  "pending_schema_change": {
    "table_identity": {
      "owner": "HR",
      "table": "EMPLOYEES",
      "object_id": "12345"
    },
    "ddl_scn": "987650",
    "ddl_commit_scn": "987655",
    "change_kind": "ADD_COLUMN",
    "old_fingerprint": "abc123",
    "expected_new_fingerprint": "def456",
    "publication_status": "required",
    "safe_replay_scn": "987640"
  }
}
```

On restart:

```text
1. Detect pending schema state.
2. Rediscover the Oracle table.
3. Verify the expected fingerprint.
4. Verify the Fivetran schema is ready.
5. Remine from safe_replay_scn.
6. Reprocess the transition.
7. Clear pending state only after safe activation.
```

# Online ADD COLUMN support

Support:

```sql
ALTER TABLE HR.EMPLOYEES
ADD FAVOURITE_COLOUR VARCHAR2(50)
```

Required behavior:

```text
1. Detect the DDL.
2. Open the table barrier.
3. Rediscover the full table schema.
4. Verify exactly one supported column addition.
5. Map the Oracle type to an SDK type.
6. Add the column to the Connector SDK schema.
7. Create a new schema version.
8. Set its valid-from boundary.
9. Remine or resume post-DDL DML.
10. Capture INSERT and UPDATE values for the new column.
```

## Existing rows after column addition

A new nullable column without a default does not require a full table resnapshot.

Existing destination rows may remain null until:

```text
the row changes
a targeted backfill runs
a table resync is requested
```

For deterministic literal defaults, do not invent existing-row values.

Support one explicit policy:

```text
new DML only
targeted incremental backfill
require controlled table resync
```

Default first implementation:

```text
ADD nullable column without default
```

# Partial updates after ADD COLUMN

When the new column is absent from an update record:

```text
do not treat absence as NULL
do not overwrite the destination value
```

When explicitly set to null:

```text
emit NULL
```

Use the `UNSET` sentinel internally.

# Online data-type change support

Support compatible changes such as:

```sql
ALTER TABLE HR.EMPLOYEES
MODIFY NOTES VARCHAR2(4000)
```

Required behavior:

```text
1. Detect the DDL.
2. Open a transition barrier.
3. Rediscover the full table schema.
4. Identify the exact changed column.
5. Compare old and new Oracle definitions.
6. Determine compatibility.
7. Determine the new SDK type.
8. Publish the SDK schema change.
9. Activate the new schema version.
10. Decode post-DDL DML using the new converter.
```

# Type compatibility engine

Implement:

```python
assess_type_change(
    old_oracle_type,
    new_oracle_type,
    old_sdk_type,
    new_sdk_type,
) -> TypeChangeDecision
```

Return:

```text
SAFE_SAME_DESTINATION_TYPE
SAFE_DESTINATION_WIDENING
REQUIRES_RESYNC
UNSUPPORTED
```

Potentially safe examples:

```text
VARCHAR2(100) -> VARCHAR2(500)
NVARCHAR2(100) -> NVARCHAR2(500)
CHAR(10) -> CHAR(20)
RAW(100) -> RAW(500)
NUMBER(10,0) -> NUMBER(18,0)
NUMBER(10,2) -> NUMBER(18,4), after validation
TIMESTAMP(3) -> TIMESTAMP(6)
```

Unsupported by default:

```text
VARCHAR2 -> NUMBER
NUMBER -> DATE
DATE -> TIMESTAMP WITH TIME ZONE
precision reduction
scale reduction
length reduction
CLOB -> VARCHAR2
VARCHAR2 -> CLOB
BLOB -> RAW
RAW -> BLOB
```

# SDK type remains the same

Example:

```text
Oracle:
    VARCHAR2(100) -> VARCHAR2(500)

SDK:
    STRING -> STRING
```

Required behavior:

```text
update Oracle schema metadata
create a new schema version
republish schema if required
continue emitting STRING
```

# SDK type changes

Example:

```text
Oracle:
    NUMBER(9,0) -> NUMBER(20,0)

SDK:
    INT -> DECIMAL
```

Required behavior:

```text
verify that SDK and destination support the transition
publish the changed SDK schema
do not emit new DECIMAL values before publication
decode pre-DDL replay using INT
decode post-DDL values using DECIMAL
```

If the transition is not supported:

```text
stop at the barrier
raise SchemaChangeRequiresResyncError
do not emit post-DDL DML
do not advance the low watermark
```

# DML parsing after schema changes

Pass an explicit schema version into the parser:

```python
parse_logminer_record(
    record=record,
    schema_version=schema_history.resolve(
        table_identity=record.table_identity,
        event_scn=record.scn,
        commit_scn=record.commit_scn,
    ),
)
```

Do not let the parser query current metadata implicitly.

Each internal event should include:

```text
schema version ID
table identity
object ID
event SCN
commit SCN
column presence map
typed values
transaction ID
transaction sequence
```

Validate emitted values against the active SDK schema.

# Deferred DML during schema publication

Prefer replay over in-memory deferral on SaaS.

## Preferred replay strategy

```text
1. Stop at the DDL barrier.
2. Keep the low watermark at or before the DDL.
3. Publish or request schema refresh.
4. Return from update().
5. Remine the DDL and post-DDL changes later.
```

## Bounded synchronous deferral

Only when schema publication is synchronous and verified:

```text
max_deferred_ddl_events
max_deferred_ddl_bytes
```

On limit breach:

```text
discard nothing
advance no checkpoint
return or fail safely
replay from the DDL
```

Do not depend on local disk.

# Schema fingerprinting

Normalize and fingerprint:

```text
ordered column names
Oracle column IDs
Oracle data types
length
precision
scale
character semantics
nullability
default metadata where relevant
primary key
object ID
data object ID
SDK type mapping
```

Exclude volatile metadata such as statistics and analysis timestamps.

The same logical schema must produce the same fingerprint.

# Schema-change checkpoint rules

Do not checkpoint beyond a DDL until:

```text
the new Oracle schema is rediscovered
the diff is classified as supported
the Connector SDK schema is published or verified
the schema version is durable
post-DDL DML can be replayed and decoded safely
```

A checkpoint while transition is pending must remain:

```text
at or before the DDL replay SCN
```

# Errors

Implement typed errors such as:

```text
ConfigurationError
OracleConnectivityError
MissingPrivilegeError
UnsupportedOracleVersionError
SnapshotTooOldError
MissingRedoLogError
LogMinerSessionError
RedoParseError
SchemaMismatchError
SchemaHistoryUnavailableError
SchemaRefreshRequiredError
SchemaChangeRequiresResyncError
UnsupportedSchemaChangeError
TransactionBufferLimitError
DeferredDdlLimitError
OperationSizeLimitError
UnsupportedThinModeFeatureError
IncompatibleStateError
ResnapshotRequiredError
```

Classify each as:

```text
retryable
non-retryable
requires resnapshot
requires schema refresh
requires Hybrid Deployment
requires source change
```

# Structured logging

Log structured fields such as:

```text
phase
snapshot SCN
start SCN
end SCN
low watermark
processed-through SCN
commit SCN
target SCN
table
object ID
transaction ID
redo thread
batch size
open transaction count
buffer bytes
DDL kind
DDL SCN
schema version
schema fingerprint
lag seconds
```

Do not log:

```text
passwords
connection strings with credentials
full row values by default
LOB contents
unredacted sensitive SQL
```

# Unit tests

Add unit tests for:

```text
configuration validation
state serialization
state migration
identifier quoting
table filtering
Oracle type mapping
SCN comparisons
redo selection
adaptive windows
transaction buffering
commit ordering
rollback handling
watermark calculation
continuation assembly
SQL_REDO parsing
snapshot pagination
schema fingerprints
schema diffs
ADD COLUMN classification
type compatibility
pending schema-change recovery
DDL barrier behavior
partial update UNSET handling
operation-size estimation
```

# SDK contract tests

Verify:

```text
Connector initialization
schema() signature
update() signature
op.upsert()
op.delete()
op.checkpoint()
soft-delete semantics
configuration parsing
encrypted fields
operation ordering
checkpoint ordering
schema publication behavior
partial upsert semantics
```

# Scheduled invocation tests

Verify:

```text
update() always terminates
target SCN remains fixed
target is reached in one invocation
target is reached across invocations
runtime budget returns safely
maximum mining-window limit works
no sleeping occurs
no daemon is created
```

# Snapshot tests

Verify:

```text
all tables use one SCN
snapshot resumes across invocations
rows are yielded incrementally
keyset pagination
composite keys
ORA-01555 handling
snapshot schema remains immutable
DDL during snapshot does not silently change projection
snapshot completion transitions to streaming
```

# Transaction tests

Verify:

```text
commit within one invocation
transaction across invocations
transaction starts before snapshot and commits after
transaction starts before snapshot and rolls back after
long-running transaction pins low watermark
overlapping transactions
memory limit failure
buffer-limit failure does not advance checkpoint
```

# Restart tests

Inject failure:

```text
after reading redo
during continuation assembly
during transaction buffering
after some operations in a transaction
after all transaction operations
before checkpoint
after checkpoint
before DDL
after DDL detection
after schema publication
before post-DDL checkpoint
between invocations
```

Verify:

```text
no committed change is missed
replay can occur
destination state remains correct
no DDL boundary is skipped
```

# ADD COLUMN integration tests

Use real Oracle LogMiner output where possible.

Test:

```text
add nullable VARCHAR2
add nullable NUMBER
add nullable TIMESTAMP
DDL followed immediately by INSERT
DDL followed immediately by UPDATE
column explicitly set to NULL
new column absent from partial update
DDL while another transaction is open
DDL between scheduled invocations
restart immediately before DDL
restart immediately after DDL
restart after schema publication
multiple post-DDL transactions
```

Verify:

```text
SDK schema contains the new column
no post-DDL row is emitted early
pre-DDL DML uses the old schema
post-DDL DML uses the new schema
UNSET differs from NULL
replay misses no changes
```

# Data-type-change integration tests

Test:

```text
VARCHAR2 length increase
NVARCHAR2 length increase
NUMBER precision increase
supported NUMBER scale increase
TIMESTAMP precision increase
Oracle type changes while SDK type stays the same
Oracle type change requires SDK widening
unsupported type-family change
type narrowing
restart on both sides of DDL
multiple nearby DDL changes
```

Verify:

```text
SDK schema is updated when required
old events use the old converter
new events use the new converter
unsupported changes stop safely
the low watermark remains replay-safe
```

# Schema-publication failure tests

Test:

```text
SDK schema publication fails
schema() refresh is delayed
Oracle metadata does not match DDL
table changes again before publication
expected fingerprint does not match
destination rejects a type change
deferred DDL memory limit is exceeded
```

Verify no post-DDL DML is lost or emitted using the wrong schema.

# Oracle integration environment

Where licensing permits, provide documented integration testing against Oracle Free.

Create scenarios covering:

```text
primary keys
composite keys
inserts
updates
deletes
rollbacks
large transactions
long-running transactions
LOBs
archive-log rotation
missing redo
DDL changes
connector restart
RAC ordering if supported
```

If Oracle cannot run in CI:

```text
provide deterministic fake LogMiner tests
document manual Oracle integration steps
keep real LogMiner fixtures
```

# Documentation

Create:

## `docs/architecture.md`

Explain:

```text
scheduled invocation model
historical sync
snapshot SCN
stream handoff
LogMiner catch-up
transactions
watermarks
replay
delivery semantics
```

## `docs/sdk_assumptions.md`

Document:

```text
plugin installation
SDK version
verified APIs
runtime constraints
operation limits
schema publication behavior
partial upsert behavior
checkpoint behavior
```

## `docs/oracle_setup.md`

Document:

```text
required privileges
ARCHIVELOG
supplemental logging
LogMiner setup
Flashback Query
redo retention
validation SQL
```

## `docs/deployment_profiles.md`

Compare:

```text
SaaS
Hybrid Deployment
transaction limits
LOB limits
resource risks
```

## `docs/state_model.md`

Document every state field.

## `docs/schema_evolution.md`

Explain:

```text
schema versions
DDL barriers
ADD COLUMN
type changes
publication workflow
restart behavior
unsupported DDL
```

## `docs/operational_runbook.md`

Cover:

```text
snapshot too old
missing redo
pinned low watermark
large transaction failure
Hybrid Deployment migration
LOB-size failures
schema refresh required
unsupported DDL
schema-history unavailable
forced resnapshot
state reset
lag investigation
```

# Implementation phases

Complete work in this order.

## Phase 0: plugin and SDK verification

Deliver:

```text
plugin installed
plugin verified
SDK version identified
SDK APIs verified
runtime limits verified
docs/sdk_assumptions.md
```

## Phase 1: connector skeleton

Deliver:

```text
configuration
schema()
bounded update()
state model
thin-mode connection
basic validation
unit tests
```

## Phase 2: resumable historical sync

Deliver:

```text
single-SCN Flashback snapshot
keyset pagination
scheduled invocation resume
snapshot schema persistence
undo-retention errors
tests
```

## Phase 3: bounded LogMiner foundation

Deliver:

```text
fixed target SCN
redo discovery
LogMiner sessions
finite SCN windows
continuation records
mocked tests
```

## Phase 4: transaction correctness

Deliver:

```text
transaction buffering
commit and rollback
cross-invocation replay
watermarks
memory protection
restart tests
```

## Phase 5: online DDL support

Deliver:

```text
schema versions
DDL detection
DDL barriers
ADD COLUMN
compatible type changes
schema publication
post-DDL parsing
restart tests
Oracle integration tests
```

## Phase 6: types and LOB hardening

Deliver:

```text
complete type mapping
LOB limits
operation-size estimation
thin-mode constraints
tests
```

## Phase 7: production hardening

Deliver:

```text
adaptive windows
structured logging
error classification
deployment documentation
operational runbook
full integration test suite
```

# Coding rules

1. Use Python type hints.
2. Use dataclasses or immutable models.
3. Keep Oracle SQL isolated.
4. Keep watermark calculations pure.
5. Keep schema compatibility calculations pure.
6. Avoid global mutable state.
7. Use dependency injection for Oracle access, time and logging.
8. Yield snapshot rows immediately.
9. Never emit uncommitted DML.
10. Never decode with stale schema metadata.
11. Never silently skip unavailable redo.
12. Never checkpoint beyond unresolved transactions.
13. Never checkpoint beyond unresolved DDL.
14. Never rely on local ephemeral disk for correctness.
15. Never sleep inside `update()`.
16. Make every loop finite.
17. Use explicit column lists.
18. Validate and quote identifiers.
19. Redact sensitive values from logs.
20. Prefer replay and duplicates over gaps.
21. Keep Connector SDK state compact.
22. Do not claim exactly-once delivery.
23. Do not claim production readiness before real Oracle tests pass.
24. Do not copy Debezium implementation code.
25. Respect all licenses of consulted projects.

# Expected final output

Provide:

1. Confirmation that the Fivetran Codex plugin was installed.
2. Installation method and plugin commit.
3. Verified Connector SDK version.
4. Verified SDK API contracts.
5. Architecture summary.
6. Deployment suitability assessment.
7. State model.
8. Historical-sync implementation.
9. Incremental LogMiner implementation.
10. Online ADD COLUMN implementation.
11. Online compatible type-change implementation.
12. Unit tests.
13. Oracle integration-test instructions.
14. Oracle setup documentation.
15. SaaS and Hybrid limitations.
16. Thin-mode limitations.
17. Transaction-size limitations.
18. LOB and operation-size limitations.
19. Data-loss risk review.
20. Duplicate-delivery risk review.
21. Restart-safety review.
22. DDL-safety review.
23. A list of unproven assumptions.
24. A list of unsupported Oracle behavior.

Do not label the connector production-ready until all of the following pass:

```text
snapshot consistency tests
cross-invocation transaction tests
restart and replay tests
missing-redo tests
transaction memory-limit tests
LOB and operation-size tests
ADD COLUMN integration tests
data-type-change integration tests
schema-publication failure tests
real Oracle LogMiner integration tests
```