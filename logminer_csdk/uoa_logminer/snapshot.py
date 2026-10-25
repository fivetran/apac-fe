"""Bounded single-SCN Flashback historical load followed by redo replay."""

import datetime
import decimal

from fivetran_connector_sdk import Operations as op

from errors import ResnapshotRequiredError, SchemaMismatchError
from runtime_budget import RuntimeBudget
from schema_models import TableSchema
from state import ConnectorState
from type_mapping import convert_snapshot_value, enforce_operation_limit


def _encode_key(value):
    if isinstance(value, decimal.Decimal):
        return {"type": "decimal", "value": str(value)}
    if isinstance(value, datetime.datetime):
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, datetime.date):
        return {"type": "date", "value": value.isoformat()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return {"type": "scalar", "value": value}
    raise SchemaMismatchError(
        f"Unsupported primary-key value type for snapshot state: {type(value).__name__}"
    )


def _decode_key(value):
    kind = value.get("type")
    raw = value.get("value")
    if kind == "decimal":
        return decimal.Decimal(raw)
    if kind == "datetime":
        return datetime.datetime.fromisoformat(raw)
    if kind == "date":
        return datetime.date.fromisoformat(raw)
    if kind == "scalar":
        return raw
    raise SchemaMismatchError("Snapshot state contains an invalid key encoding")


def _row_to_record(row: tuple, table_schema: TableSchema, config) -> dict:
    record = {}
    for index, column in enumerate(table_schema.replicated_columns):
        record[column.name.lower()] = convert_snapshot_value(
            row[index], column.to_dict(), config.max_lob_bytes
        )
    enforce_operation_limit(record, config.max_operation_bytes)
    return record


def _discover(client):
    return (
        client.discover_tables()
        if hasattr(client, "discover_tables")
        else [client.discover_table()]
    )


def run_snapshot(client, config, state: ConnectorState, runtime: RuntimeBudget) -> None:
    """Read all selected tables at one immutable SCN with resumable keysets."""
    if state.snapshot.read_mode != "flashback":
        raise ResnapshotRequiredError("Historical state is not a Flashback snapshot")
    discovered = {table.source_key: table for table in _discover(client)}
    if state.snapshot.capture_boundary_scn is None:
        if state.snapshot.contracts:
            if set(discovered) != set(state.snapshot.contracts):
                raise SchemaMismatchError(
                    "Selected tables changed; explicit connection resync required"
                )
            discovered = {
                key: table.retain_contract(
                    TableSchema.from_dict(state.snapshot.contracts[key])
                )
                for key, table in discovered.items()
            }
        boundary, oldest = client.capture_boundary()
        verified = {table.source_key: table for table in _discover(client)}
        if state.snapshot.contracts:
            verified = {
                key: table.retain_contract(
                    TableSchema.from_dict(state.snapshot.contracts[key])
                )
                for key, table in verified.items()
            }
        if {key: table.fingerprint for key, table in verified.items()} != {
            key: table.fingerprint for key, table in discovered.items()
        }:
            raise SchemaMismatchError(
                "Source schema changed while establishing snapshot"
            )
        state.snapshot.capture_boundary_scn = str(boundary)
        state.snapshot.capture_start_scn = str(
            min(boundary, oldest if oldest is not None else boundary)
        )
        state.snapshot.table_order = sorted(discovered)
        state.snapshot.tables = {
            key: {"table_schema": table.to_dict(), "last_key": [], "completed": False}
            for key, table in discovered.items()
        }
        state.schema_history = {}
        for key, table in discovered.items():
            state.schema_history[key] = {
                "previous": None,
                "active": {
                    "version_id": f"capture-{boundary}",
                    "valid_from_scn": state.snapshot.capture_start_scn,
                    "schema": table.to_dict(),
                    "fingerprint": table.fingerprint,
                },
                "pending": None,
            }
            if state.snapshot.reconcile:
                op.truncate(table=table.destination_name)
        state.snapshot.table_schema = discovered[
            state.snapshot.table_order[0]
        ].to_dict()
        op.checkpoint(state=state.to_dict())
    elif not state.snapshot.tables:
        if state.snapshot.table_schema is None:
            raise SchemaMismatchError("Snapshot is missing immutable table metadata")
        old = TableSchema.from_dict(state.snapshot.table_schema)
        state.snapshot.table_order = [old.source_key]
        state.snapshot.tables = {
            old.source_key: {
                "table_schema": old.to_dict(),
                "last_key": state.snapshot.last_key,
                "completed": False,
            }
        }
    if set(discovered) != set(state.snapshot.tables):
        raise SchemaMismatchError(
            "Selected tables changed; explicit connection resync required"
        )
    for key, value in state.snapshot.tables.items():
        table = TableSchema.from_dict(value["table_schema"])
        current = discovered[key]
        if state.snapshot.contracts:
            current = current.retain_contract(table)
        if current.fingerprint != table.fingerprint:
            raise SchemaMismatchError(
                f"Snapshot schema changed for {key}; explicit resnapshot required"
            )
    assert state.snapshot.capture_boundary_scn is not None
    assert state.snapshot.capture_start_scn is not None
    emitted = 0
    while state.snapshot.table_index < len(state.snapshot.table_order):
        if emitted >= config.snapshot_rows_per_invocation or runtime.nearly_exhausted():
            return
        key = state.snapshot.table_order[state.snapshot.table_index]
        progress = state.snapshot.tables[key]
        table = TableSchema.from_dict(progress["table_schema"])
        indexes = [
            next(
                index
                for index, column in enumerate(table.replicated_columns)
                if column.name == name
            )
            for name in table.primary_key
        ]
        page_size = min(
            config.snapshot_fetch_size, config.snapshot_rows_per_invocation - emitted
        )
        rows = client.fetch_historical_page(
            table_schema=table,
            last_key=[_decode_key(value) for value in progress["last_key"]],
            fetch_size=page_size,
            snapshot_scn=int(state.snapshot.capture_boundary_scn),
        )
        for row in rows:
            runtime.require_time()
            op.upsert(
                table=table.destination_name, data=_row_to_record(row, table, config)
            )
            progress["last_key"] = [_encode_key(row[index]) for index in indexes]
            state.snapshot.last_key = progress["last_key"]
            emitted += 1
        if len(rows) < page_size:
            progress["completed"] = True
            state.snapshot.table_index += 1
        op.checkpoint(state=state.to_dict())
    state.snapshot.completed = True
    state.phase = "streaming"
    state.streaming.low_watermark_scn = state.snapshot.capture_start_scn
    state.streaming.processed_through_scn = str(
        max(0, int(state.snapshot.capture_start_scn) - 1)
    )
    state.streaming.high_watermark_commit_scn = None
    op.checkpoint(state=state.to_dict())
