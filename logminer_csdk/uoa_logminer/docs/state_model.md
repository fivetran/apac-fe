# State model

State version **4** stores SCNs as decimal strings and contains:

| Field | Purpose |
| --- | --- |
| `phase` | `snapshot` or `streaming` |
| `scope_fingerprint` | Database endpoint and selected table/column scope hash |
| `source_identity` | Oracle DBID and RESETLOGS incarnation |
| `snapshot.capture_boundary_scn` | Immutable Flashback SCN shared by all tables |
| `snapshot.capture_start_scn` | Earlier boundary/oldest-open-transaction SCN |
| `snapshot.tables` | Source-keyed metadata, typed last key and completion flag |
| `snapshot.table_order`, `table_index` | Deterministic resumable table traversal |
| `snapshot.reconcile`, `contracts`, `reason` | Explicit DDL historical reload and frozen contracts |
| `snapshot.table_schema`, `last_key` | Legacy single-table compatibility fields |
| `streaming.low_watermark_scn` | Earliest redo still required |
| `streaming.processed_through_scn` | Highest inspected window end |
| `streaming.high_watermark_commit_scn` | Highest emitted captured commit |
| `schema_history` | Bounded schema metadata used for selected redo decoding |
| `pending_schema_change` | Legacy marker migrated into historical reconciliation |

No credentials, private keys, SQL_REDO, LOBs or transaction buffers are saved.
State is limited to 9 MiB. Unknown versions and invalid phases/shapes fail.
Confirm the original source before migrating older state that lacks source
identity, or use a controlled resync. Version 3 preserves its single-table cursor; an unfinished version 2
capture-first snapshot requires controlled resync. Legacy publication barriers
become explicit historical-reconciliation requests.

Changing source identity or configured selections requires an explicit connection
resync; do not edit cursor fields to bypass the check. A DDL request retains old
watermarks until its new historical boundary is checkpointed. Failure before that
checkpoint replays initialization and truncate; failure after it resumes pages.
