# Support and acceptance boundaries

This implementation is a development handover, not a production-ready native
Fivetran Oracle connector. It uses a bounded SQL_REDO parser with explicit scalar
literal support; unsupported types, expressions or LogMiner status fail closed.

- Oracle 19.32, thin-mode SID access, single redo thread and SSH are live-tested.
  RAC, multitenant deployment, listener redirects, nested bastions, Oracle thick
  mode and connection pooling are not certified.
- Tables require enabled primary keys. Numeric and text keys, including composite
  keys, are live-tested. RAW keys cannot be serialized by the snapshot cursor;
  temporal key moves are unproven. Simple and composite key values may move;
  changing the primary-key **definition** requires a reviewed resync/contract.
- Schema discovery receives configuration without saved state. Incompatible
  selected-type or primary-key definition changes must be planned while paused;
  independent discovery can advertise current source metadata before the update
  guard rejects the change. Review destination schema during recovery.
- Explicit column arrays are required for fixed client schema behavior. Wildcard
  and legacy discovery modes are retained for exploration, not fixed-schema DDL
  acceptance. Source/table/column scope changes require connection resync.
- LOB, LONG, LONG RAW, BFILE and XMLTYPE payloads are excluded. A large CLOB mixed
  with scalar updates was tested. Every LOB/XML variant, compressed/securefile
  behavior and unsupported mixed operations are not exhaustively proven.
- DDL performs full historical reconciliation of all selected tables; destination
  schema evolution is excluded. There can be a temporary partially soft-deleted
  destination. Flashback-invalidating DDL during a running snapshot stops it.
- Selected drops/renames, narrowing, destination type changes, replaced objects,
  complex partition/redefinition DDL and undecodable historical online-catalog
  redo stop processing. They must not be skipped by editing cursors.
- Undo is necessary for historical pages and key-move after-images. Redo is
  necessary from capture start and every unresolved transaction start. Expired
  versions/logs require reviewed recovery or resync.
- Delivery is at least once, with idempotent final row operations. Destination
  transaction atomicity and exactly-once event history are not provided. Consumers
  can observe intermediate transaction/reload states. Large production workloads,
  prolonged outages and Hybrid sizing remain unproven.
- SDK DECIMAL declarations include the selected source precision/scale. Changes
  to those parameters require a reviewed destination contract; they are not
  automatically propagated by the CDC path. Unconstrained non-key NUMBER maps
  to FLOAT and can lose exact decimal precision. Timezone-bearing timestamp
  columns and timestamp declarations above six
  fractional digits are rejected during discovery. Offset-preserving timezone
  fetches and nanosecond serialization are not implemented. Ordinary DATE and
  TIMESTAMP through six fractional digits remain supported.
- Sandbox cloud execution and state checkpoints are verified separately from
  local destination values. Cloud destination row-level SQL assertions were
  explicitly excluded by the user and remain required before production acceptance.
