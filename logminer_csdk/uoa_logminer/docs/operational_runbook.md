# Operational runbook

| Condition | Action |
| --- | --- |
| DDL requests historical reconciliation | Allow the next scheduled callbacks to reload all selected tables; account for temporary soft deletes |
| Snapshot undo expired or DDL invalidates Flashback | Stop; arrange controlled resync, never substitute a new SCN in the current snapshot |
| Required redo aged out or MISSING_SCN | Restore logs if possible; otherwise review and resync; do not advance cursors |
| Current redo not archived | Normal archive-only wait; retry next schedule with unchanged cursor |
| Low watermark pinned | Check source open transactions and continuation records; retain required archives |
| Transaction/continuation/operation limit exceeded | Reduce source batches or size measured limits; never skip data |
| Database call timeout or invocation budget exhausted | Retry from last acknowledged checkpoint; investigate source execution time |
| Key-move Flashback image unavailable | Retain undo and retry; otherwise controlled resync |
| Selected-column/PK definition incompatible | Restore compatible metadata or review destination contract and configuration, then resync |
| Rollback compensation mismatch | Verify complete redo and row identity; never discard flagged records |
| Unsupported scalar grammar/status/type | Stop and add proven support before replay |
| Configured scope/source incarnation changed | Explicit connection resync; do not patch fingerprints to bypass validation |
| Bastion host key mismatch | Verify replacement via trusted administration; no automatic acceptance or direct fallback |

A deployed connection state reset starts a historical sync and affects all selected
tables. Local `fivetran reset` affects only local tester state. Keep raw test
artifacts and credentials outside delivered code. Incident reports should contain
SCNs, phases, error classes and durations, without row values or SQL_REDO.

Expected source counts plus successful cloud checkpoints prove execution and
expected results, not destination row-level correctness. Query destination values
and `_fivetran_deleted` before production acceptance.
