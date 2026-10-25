# Source DDL policy

The client scope does **not** propagate new columns or destination type changes.
Use explicit selected-column lists in `tables`. Primary-key columns are added
automatically. Legacy single-table discovery is retained for migration; convert
legacy settings to explicit lists before client use so schema discovery cannot
introduce newly added source columns.

Any captured DDL record after the historical boundary requests a full historical
reconciliation. Changed source metadata detected before mining does the same.
This deliberately reloads all selected tables at one consistent SCN, including
tables unaffected by the DDL. An in-progress snapshot invalidated by DDL stops
and needs a controlled resync rather than silently changing its SCN.

On initialization, `op.truncate` soft-deletes previously synced destination rows;
then current selected columns are loaded and post-boundary commits replayed.
Destination keys missing at the new SCN remain soft deleted. Until the reload
finishes, consumers can observe a partially restored destination.

| Source change | Result |
| --- | --- |
| Add/drop/change an unselected column | Historical reload; column remains excluded |
| Selected VARCHAR/RAW length widening with same SDK type | Reload, retaining the destination contract |
| Selected numeric/timestamp change with same proven SDK type | Reload when classified compatible |
| Source truncate, unchanged table object and keys | Reload; old keys soft deleted |
| Drop/rename selected column, narrowing, type-family change | Stop for reviewed contract/configuration change |
| Destination numeric type widening required | Stop; no automatic destination DDL |
| Change primary-key constraint columns | Stop; cannot preserve the original identity contract |
| Change primary-key values in DML | Old key soft delete plus complete new-key upsert |
| Replace/drop selected table | Stop |

Online-catalog LogMiner may mark older DML undecodable after structural DDL.
Such records fail closed even when columns are excluded. Rapid DDL, partition
exchange/redefinition and other complex DDL are unproven. Restore compatible
metadata or use a reviewed source/configuration change and connection resync.
