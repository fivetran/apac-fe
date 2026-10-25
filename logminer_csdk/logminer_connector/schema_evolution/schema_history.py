"""Compact activation of schema versions that need no SDK schema publication."""

from errors import SchemaHistoryUnavailableError
from schema_models import TableSchema
from state import ConnectorState


def resolve_schema_version(
    state: ConnectorState, table_key: str, event_scn: int
) -> tuple[TableSchema, str]:
    history = state.schema_history.get(table_key, {})
    versions = [history.get("previous"), history.get("active")]
    valid = sorted((v for v in versions if v), key=lambda v: int(v["valid_from_scn"]))
    for index, version in enumerate(valid):
        start = int(version["valid_from_scn"])
        end = (
            int(valid[index + 1]["valid_from_scn"]) if index + 1 < len(valid) else None
        )
        if start <= event_scn and (end is None or event_scn < end):
            schema = TableSchema.from_dict(version["schema"])
            if schema.fingerprint != version.get("fingerprint"):
                raise SchemaHistoryUnavailableError(
                    "Retained schema fingerprint is corrupt"
                )
            return schema, str(version["version_id"])
    raise SchemaHistoryUnavailableError(
        f"No retained schema for {table_key} at event SCN {event_scn}"
    )


def activate_schema_version(
    state: ConnectorState,
    schema: TableSchema,
    valid_from_scn: int,
    reason: str,
) -> str:
    history = state.schema_history.setdefault(
        schema.source_key,
        {"previous": None, "active": None, "pending": None},
    )
    active = history.get("active")
    version_id = f"{reason}-{valid_from_scn}-{schema.fingerprint[:12]}"
    if (
        active
        and active.get("version_id") == version_id
        and active.get("fingerprint") == schema.fingerprint
    ):
        state.snapshot.table_schema = schema.to_dict()
        return version_id
    if (
        history.get("previous")
        and active
        and int(state.streaming.low_watermark_scn or 0) < int(active["valid_from_scn"])
    ):
        raise SchemaHistoryUnavailableError(
            "Schema activation would discard metadata required for replay"
        )
    history["previous"] = active
    history["active"] = {
        "version_id": version_id,
        "valid_from_scn": str(valid_from_scn),
        "schema": schema.to_dict(),
        "fingerprint": schema.fingerprint,
    }
    history["pending"] = None
    state.snapshot.table_schema = schema.to_dict()
    return version_id
