# Architecture

Each scheduled `update(configuration, state)` invocation is finite. One Oracle
thin connection is opened, through a session-scoped SSH tunnel when enabled.
The connector captures one phase-specific target and returns within configured
work limits. The transport uses bounded worker threads; no redo poller or daemon
runs between callbacks.

## Historical load

Discover all selected tables and record one SCN plus the oldest open transaction
SCN. Recheck metadata before the initial checkpoint. Project only selected scalar
columns and all keys. Every table and page uses `AS OF SCN` at that same boundary.
Lexicographic primary-key pagination and per-table progress support restarts.

On completion, mine from the earlier capture/open-transaction SCN. Ignore commits
at or before the snapshot boundary, which are already represented by historical
rows. Apply later commits, including transactions opened before the boundary.
Undo must cover the whole snapshot duration; redo must cover capture and catchup.

## Incremental sync

Capture current SCN once. Validate contiguous redo coverage in the current
RESETLOGS incarnation and mine bounded windows. Multi-thread RAC redo fails
closed. Archive-only mode returns unchanged when the current online log is not
yet archived. It never forces a source log switch or sleeps to poll for redo.

Assemble bounded continuation fragments, tokenize selected scalar literals, and
buffer changes by transaction ID across all selected tables. Emit only committed
transactions. Full rollback discards changes; savepoint compensation removes the
matching buffered row change. Unmatched compensation stops processing.

Inserts use complete upserts, ordinary updates preserve omitted fields, explicit
nulls clear them, and deletes are soft deletes. Any transaction containing a key
move reconciles every touched key: all deletes precede commit-SCN Flashback reads
and complete upserts. This handles swaps and repeated moves without erasing the
final row. Required undo loss stops the transaction without a new checkpoint.

LOB/XML-only operation codes are excluded before continuation assembly, and
SQL_REDO for those codes is not fetched. Regular scalar DML from the same
transaction is still parsed. Unsupported scalar grammar/status stops replication.

## Checkpoints and DDL

Unresolved transactions and incomplete continuations pin the global low
watermark. In-memory buffers are rebuilt from redo after each invocation.
Uncheckpointed operations can replay, so delivery is at least once; operations
are idempotent by complete primary key. Destination transactions are not atomic
across tables or all emitted rows.

DDL or a metadata difference checkpoints an explicit historical-reconciliation
request. The next callback validates the frozen selected-column contract, obtains
one new SCN, soft-truncates all selected destination tables and checkpoints that
initialization. Remaining callbacks resume pages without another truncate.
Current source keys reactivate through upsert; absent keys remain soft deleted.
No destination schema-publication acknowledgement is needed.
