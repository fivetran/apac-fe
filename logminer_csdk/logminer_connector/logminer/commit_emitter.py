"""Emit committed changes, reconciling PK moves from exact Flashback images."""

from fivetran_connector_sdk import Operations as op

from errors import TransactionBufferLimitError
from snapshot import _row_to_record
from type_mapping import estimate_operation_bytes


def has_key_move(event) -> bool:
    return event.operation == "UPDATE" and any(
        name in event.values and event.values[name] != value
        for name, value in event.keys.items()
    )


def emit_committed(events, commit_scn, schemas, client, config, runtime, emit_event):
    if not any(has_key_move(event) for event in events):
        for event in events:
            runtime.require_time()
            emit_event(event)
        return
    # Reconcile every touched key together. Delete before any upsert so key
    # swaps and repeated moves cannot delete another row's final image.
    identities = {}
    total_bytes = 0
    for event in events:
        table = schemas[event.table_key]
        keys = dict(event.keys)
        after = {name: event.values.get(name, value) for name, value in keys.items()}
        for key in (keys, after):
            identity = (
                event.table_key,
                tuple(key[name.lower()] for name in table.primary_key),
            )
            if identity not in identities:
                total_bytes += estimate_operation_bytes(key) + 128
                if total_bytes > config.max_single_transaction_bytes:
                    raise TransactionBufferLimitError(
                        "Primary-key reconciliation exceeds transaction memory limit"
                    )
                identities[identity] = key
    for (table_key, _), keys in identities.items():
        runtime.require_time()
        op.delete(table=schemas[table_key].destination_name, keys=keys)
    for (table_key, _), keys in identities.items():
        runtime.require_time()
        table = schemas[table_key]
        row = client.fetch_committed_row(table, keys, commit_scn)
        if row is not None:
            op.upsert(
                table=table.destination_name, data=_row_to_record(row, table, config)
            )
