"""Finite LogMiner catch-up orchestration with replay-safe checkpoints."""

from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op

from errors import (
    MissingRedoLogError,
    RedoParseError,
)
from logminer.commit_emitter import emit_committed
from logminer.continuation import ContinuationAssembler
from logminer.models import DmlEvent
from logminer.parser import parse_sql_redo
from logminer.redo_log_selector import select_redo_logs
from logminer.session import LogMinerSession
from logminer.transaction_buffer import TransactionBuffer
from logminer.watermarks import (
    adapt_span,
    calculate_low_watermark,
    choose_window_end,
)
from schema_evolution.schema_history import resolve_schema_version
from schema_models import TableSchema
from type_mapping import enforce_operation_limit, estimate_operation_bytes


def _emit_event(event: DmlEvent) -> None:
    if event.operation == "INSERT":
        op.upsert(table=event.destination_table, data=event.values)
    elif event.operation == "UPDATE":
        modified = dict(event.keys)
        modified.update(event.values)
        op.update(table=event.destination_table, modified=modified)
    elif event.operation == "DELETE":
        op.delete(table=event.destination_table, keys=event.keys)
    else:
        raise RedoParseError(f"Unsupported buffered operation: {event.operation}")


def run_logminer_sync(client, config, state, runtime) -> None:
    schemas = {
        key: TableSchema.from_dict(value)
        for key, value in state.table_schemas().items()
    }
    if not schemas:
        raise RedoParseError("Streaming state has no table schemas")
    boundary = int(state.snapshot.capture_boundary_scn or 0)
    start_scn = int(state.streaming.low_watermark_scn)
    target_scn = client.current_scn()
    span = config.logminer_initial_scn_span
    windows = 0
    transactions = TransactionBuffer(
        max_open_transactions=config.max_open_transactions,
        max_transaction_events=config.max_transaction_events,
        max_total_bytes=config.max_transaction_buffer_bytes,
        max_single_transaction_bytes=config.max_single_transaction_bytes,
        deployment_profile=config.deployment_profile,
    )
    assembler = ContinuationAssembler(
        config.max_continuation_bytes, config.max_continuation_fragments
    )
    high_commit = (
        int(state.streaming.high_watermark_commit_scn)
        if state.streaming.high_watermark_commit_scn is not None
        else None
    )

    while (
        start_scn <= target_scn
        and windows < config.max_mining_windows_per_invocation
        and not runtime.nearly_exhausted()
    ):
        requested_end = choose_window_end(start_scn, target_scn, span)
        with client.cursor() as cursor:
            logs, covered_end = select_redo_logs(
                cursor,
                start_scn,
                requested_end,
                config.archive_log_only,
            )
        if not logs:
            log.info(
                f"Redo at SCN {start_scn} is not archived yet; "
                "returning without advancing the low watermark"
            )
            return
        record_count = 0
        with LogMinerSession(client) as session:
            session.start(logs, start_scn, covered_end)
            pairs = [(schema.owner, schema.name) for schema in schemas.values()]
            records = (
                session.records(*pairs[0])
                if len(pairs) == 1
                else session.records(pairs)
            )
            for raw_record in records:
                if runtime.nearly_exhausted():
                    # No checkpoint for a partially read window. Previously
                    # checkpointed windows replay the unresolved transaction.
                    return
                if raw_record.operation_code in {9, 10, 11, 29, 68, 70, 71}:
                    continue
                table_key = f"{raw_record.owner}.{raw_record.table}"
                schema = schemas.get(table_key)

                record_count += 1
                record = assembler.add(raw_record)
                if record is None:
                    continue
                if record.operation_code in {1, 2, 3}:
                    if schema is None:
                        raise RedoParseError(
                            "DML table identity is outside saved selection"
                        )
                    if not record.xid:
                        raise RedoParseError(
                            f"DML at SCN {record.scn} has no transaction ID"
                        )
                    if record.rollback:
                        transactions.compensate(
                            record.xid,
                            schema.source_key,
                            record.row_id,
                            record.operation,
                        )
                        continue
                    if record.status != 0:
                        raise RedoParseError(
                            f"LogMiner DML status {record.status} at SCN {record.scn} is not decodable"
                        )
                    event_schema, event_version = resolve_schema_version(
                        state, schema.source_key, record.scn
                    )
                    values, keys = parse_sql_redo(
                        record.sql_redo or "", record.operation, event_schema
                    )
                    operation_data = (
                        values if record.operation == "INSERT" else {**keys, **values}
                    )
                    enforce_operation_limit(operation_data, config.max_operation_bytes)
                    event = DmlEvent(
                        transaction_id=record.xid,
                        transaction_sequence=record.ssn or record_count,
                        event_scn=record.scn,
                        table_key=schema.source_key,
                        destination_table=schema.destination_name,
                        operation=record.operation,
                        values=values,
                        keys=keys,
                        schema_version_id=event_version,
                        estimated_bytes=estimate_operation_bytes(operation_data),
                        row_id=record.row_id,
                    )
                    transactions.append(event)
                elif record.operation_code == 7 and record.xid:
                    committed = transactions.commit(record.xid)
                    commit_scn = record.commit_scn or record.scn
                    if commit_scn <= boundary:
                        continue
                    emit_committed(
                        committed,
                        commit_scn,
                        schemas,
                        client,
                        config,
                        runtime,
                        _emit_event,
                    )
                    if committed:
                        # COMMIT_SCN is NULL without COMMITTED_DATA_ONLY. The
                        # COMMIT record's own SCN is the transaction boundary.
                        high_commit = max(
                            high_commit or 0, record.commit_scn or record.scn
                        )
                elif record.operation_code == 36 and record.xid:
                    transactions.rollback(record.xid)
                elif record.operation_code == 5:
                    if record.scn <= boundary:
                        continue
                    if schema is None:
                        raise RedoParseError(
                            "DDL table identity is outside saved selection"
                        )
                    state.request_resnapshot(
                        f"DDL at SCN {record.scn} for {schema.source_key}"
                    )
                    op.checkpoint(state=state.to_dict())
                    log.info(
                        f"DDL detected for {schema.source_key}; historical reconciliation scheduled"
                    )
                    return
                elif record.operation_code == 34:
                    raise MissingRedoLogError(
                        f"LogMiner reported MISSING_SCN at SCN {record.scn}; "
                        "a controlled resnapshot is required"
                    )
                elif record.operation_code == 255:
                    raise RedoParseError(
                        f"Oracle LogMiner reported an unsupported operation at "
                        f"SCN {record.scn}"
                    )

        next_unread = covered_end + 1
        low_watermark = calculate_low_watermark(
            next_unread,
            transactions.oldest_start_scn,
            assembler.incomplete_scn,
            (
                int(state.pending_schema_change["safe_replay_scn"])
                if state.pending_schema_change
                else None
            ),
        )
        previous_processed = int(state.streaming.processed_through_scn or 0)
        state.streaming.processed_through_scn = str(
            max(previous_processed, covered_end)
        )
        state.streaming.low_watermark_scn = str(low_watermark)
        state.streaming.high_watermark_commit_scn = (
            str(high_commit) if high_commit is not None else None
        )
        op.checkpoint(state=state.to_dict())
        log.info(
            f"Processed bounded LogMiner window {start_scn}..{covered_end}; "
            f"records={record_count}, open_transactions={transactions.open_count}"
        )
        windows += 1
        span = adapt_span(
            span,
            record_count,
            config.logminer_min_scn_span,
            config.logminer_max_scn_span,
        )
        start_scn = next_unread
        if covered_end < requested_end:
            break
