# Oracle setup

Use python-oracledb thin mode and exactly one of service name or SID. Validate
connectivity and read-only metadata before changing a source database.

Required access includes selected tables (SELECT and Flashback), `V$VERSION`,
`V$DATABASE`, `V$TRANSACTION`, `V$LOG`, `V$LOGFILE`, `V$ARCHIVED_LOG`,
`V$LOGMNR_CONTENTS`, `ALL_OBJECTS`, `ALL_TAB_COLUMNS`, `ALL_CONSTRAINTS`,
`ALL_CONS_COLUMNS`, and execute on `DBMS_LOGMNR`. Oracle 19c also requires the
applicable LogMiner/session privileges. Verify exact grants with the database
administrator; dictionary access alone does not prove all mining privileges.

ARCHIVELOG and minimal database supplemental logging are required. Enable
primary-key supplemental logging for each selected table. Verify it in
`ALL_LOG_GROUPS` and ensure real SQL_REDO contains every key and complete selected
insert after-images. Tables require an enabled primary key; composite keys work.

```sql
SELECT LOG_MODE, SUPPLEMENTAL_LOG_DATA_MIN, CURRENT_SCN FROM V$DATABASE;
SELECT LOG_GROUP_TYPE, ALWAYS FROM ALL_LOG_GROUPS
WHERE OWNER = 'SOURCE_SCHEMA' AND TABLE_NAME = 'SOURCE_TABLE';
-- DBA-approved example; do not repeat if already enabled:
ALTER TABLE SOURCE_SCHEMA.SOURCE_TABLE
  ADD SUPPLEMENTAL LOG DATA (PRIMARY KEY) COLUMNS;
```

On Amazon RDS, database minimal logging is configured through the authorized
`rdsadmin.rdsadmin_util.alter_supplemental_logging` procedure. Database logging
and retention changes require explicit administrator authorization.

Retain redo throughout historical load, catchup, oldest open transactions and
retries. Retain undo throughout snapshots and key-move commit-SCN reads. The
sandbox's approved archive retention is 24 hours; production sizing depends on
workload and downtime. Retention cannot recover already deleted redo.

Before source mutation tests, inspect metadata, keys and counts and capture
restorable test data. Use dedicated tables and uniquely identified rows. Never
truncate/drop a shared source table or delete unrelated rows. LOB source columns
can exist but are excluded from projection and destination replication.
