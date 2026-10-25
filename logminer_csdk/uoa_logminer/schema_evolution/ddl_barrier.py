"""Legacy barrier reference; active replication uses historical reconciliation."""

from errors import SchemaRefreshRequiredError, UnsupportedSchemaChangeError
from schema_evolution.schema_diff import (
    SchemaChangeKind,
    classify_schema_change,
)
from schema_models import TableSchema
from state import ConnectorState


def open_schema_change_barrier(
    state: ConnectorState,
    old_schema: TableSchema,
    new_schema: TableSchema,
    ddl_scn: int,
    safe_replay_scn: int,
) -> None:
    diff = classify_schema_change(old_schema, new_schema)
    if diff.kind == SchemaChangeKind.NONE:
        return
    if diff.kind == SchemaChangeKind.UNSUPPORTED:
        raise UnsupportedSchemaChangeError(
            diff.reason or "DDL did not produce a supported schema change"
        )
    state.pending_schema_change = {
        "table_identity": {
            "owner": old_schema.owner,
            "table": old_schema.name,
            "object_id": str(old_schema.object_id),
        },
        "ddl_scn": str(ddl_scn),
        "change_kind": diff.kind.value,
        "old_fingerprint": old_schema.fingerprint,
        "expected_new_fingerprint": new_schema.fingerprint,
        "publication_status": "required",
        "safe_replay_scn": str(safe_replay_scn),
        "candidate_schema": new_schema.to_dict(),
    }
    state.streaming.low_watermark_scn = str(
        min(
            int(state.streaming.low_watermark_scn or safe_replay_scn),
            safe_replay_scn,
        )
    )
    raise SchemaRefreshRequiredError(
        f"Schema refresh required for {old_schema.source_key} at DDL SCN {ddl_scn}"
    )
