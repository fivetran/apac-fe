"""Exercise complete bounded invocations with discarded in-memory buffers."""

import copy
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace

import pytest

from configuration import ConnectorConfig
from errors import MissingRedoLogError, TransactionBufferLimitError
from logminer.models import RedoRecord
from logminer.sync import run_logminer_sync
from runtime_budget import RuntimeBudget
from schema_models import ColumnSchema, TableSchema
from state import ConnectorState


class InjectedFailure(RuntimeError):
    pass


def table():
    return TableSchema(
        "A",
        "T",
        1,
        1,
        (
            ColumnSchema("ID", 1, "NUMBER", 22, 10, 0, None, False, None),
            ColumnSchema("VALUE", 2, "VARCHAR2", 50, None, None, "B", True, None),
        ),
        ("ID",),
    )


def initial_state():
    schema = table()
    state = ConnectorState()
    state.phase = "streaming"
    state.snapshot.table_schema = schema.to_dict()
    state.streaming.low_watermark_scn = "100"
    state.streaming.processed_through_scn = "99"
    state.schema_history[schema.source_key] = {
        "previous": None,
        "active": {
            "version_id": "v1",
            "valid_from_scn": "100",
            "schema": schema.to_dict(),
            "fingerprint": schema.fingerprint,
        },
        "pending": None,
    }
    return state.to_dict()


def config(**overrides):
    result = ConnectorConfig.from_mapping(
        {
            "host": "example.invalid",
            "service_name": "test",
            "username": "test",
            "password": "fake",
            "include_schema": "A",
            "include_table": "T",
            "logminer_initial_scn_span": "10",
            "logminer_min_scn_span": "10",
            "logminer_max_scn_span": "10",
            "max_mining_windows_per_invocation": "10",
        }
    )
    return replace(result, **overrides)


def record(scn, operation, xid="1", sql=None, **overrides):
    codes = {
        "INSERT": 1,
        "DELETE": 2,
        "UPDATE": 3,
        "COMMIT": 7,
        "ROLLBACK": 36,
        "MISSING_SCN": 34,
    }
    return replace(
        RedoRecord(
            scn,
            scn if operation == "COMMIT" else None,
            operation,
            codes[operation],
            xid,
            "A",
            "T",
            sql,
            0,
            f"{scn:010}",
            1,
            1,
            1,
            None,
        ),
        **overrides,
    )


def insert(scn, key, xid="1"):
    return record(
        scn,
        "INSERT",
        xid,
        f'insert into "A"."T"("ID","VALUE") values ({key},\'initial\');',
    )


class Sink:
    """Model acknowledged checkpoints and idempotent destination operations."""

    def __init__(self, failure=None):
        self.saved = initial_state()
        self.rows = {}
        self.calls = []
        self.failure = failure
        self.operations = 0

    def _operation(self, kind, values):
        self.operations += 1
        self.calls.append(kind)
        key = values["id"]
        if kind == "upsert":
            self.rows[key] = {**values, "_fivetran_deleted": False}
        elif kind == "update":
            self.rows[key].update(values)
        elif kind == "delete":
            self.rows[key]["_fivetran_deleted"] = True
        if self.failure == ("operation", self.operations):
            self.failure = None
            raise InjectedFailure("operation boundary")

    def upsert(self, table, data):
        self._operation("upsert", data)

    def update(self, table, modified):
        self._operation("update", modified)

    def delete(self, table, keys):
        self._operation("delete", keys)

    def checkpoint(self, state):
        if self.failure == "before_checkpoint":
            self.failure = None
            raise InjectedFailure("before checkpoint")
        self.saved = copy.deepcopy(state)
        self.calls.append("checkpoint")
        if self.failure == "after_checkpoint":
            self.failure = None
            raise InjectedFailure("after checkpoint")


class Client:
    def __init__(self, target):
        self.target = target
        self.target_reads = 0

    def current_scn(self):
        self.target_reads += 1
        return self.target

    def cursor(self):
        return nullcontext(SimpleNamespace())


def install(monkeypatch, records, sink, failure_after_read=None):
    windows = []

    class Session:
        def __init__(self, client):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def start(self, logs, start, end):
            self.start_scn, self.end_scn = start, end
            windows.append((start, end))

        def records(self, owner, table):
            for item in records:
                if self.start_scn <= item.scn <= self.end_scn:
                    if failure_after_read == item.scn:
                        raise InjectedFailure("after redo read")
                    yield item

    monkeypatch.setattr("logminer.sync.LogMinerSession", Session)
    monkeypatch.setattr(
        "logminer.sync.select_redo_logs",
        lambda cursor, start, end, archive: ([object()], end),
    )
    monkeypatch.setattr("logminer.sync.op", sink)
    monkeypatch.setattr("logminer.sync.log", SimpleNamespace(info=lambda _: None))
    return windows


def invoke(client, sink, cfg=None):
    state = ConnectorState.load(copy.deepcopy(sink.saved))
    run_logminer_sync(client, cfg or config(), state, RuntimeBudget.start(600))


@pytest.mark.parametrize(
    "failure",
    [
        ("operation", 1),
        ("operation", 2),
        "before_checkpoint",
        "after_checkpoint",
    ],
)
def test_failure_replay_preserves_complete_committed_transaction(monkeypatch, failure):
    sink = Sink(failure)
    records = [insert(100, 1), insert(101, 2), record(102, "COMMIT")]
    install(monkeypatch, records, sink)
    with pytest.raises(InjectedFailure):
        invoke(Client(109), sink)
    if failure == "after_checkpoint":
        assert sink.saved["streaming"]["low_watermark_scn"] == "110"
    else:
        assert sink.saved["streaming"]["low_watermark_scn"] == "100"
    invoke(Client(109), sink)
    assert sink.rows == {
        1: {"id": 1, "value": "initial", "_fivetran_deleted": False},
        2: {"id": 2, "value": "initial", "_fivetran_deleted": False},
    }
    assert sink.saved["streaming"]["high_watermark_commit_scn"] == "102"


def test_transaction_across_invocations_reconstructs_from_pinned_watermark(monkeypatch):
    sink = Sink()
    records = [
        insert(100, 1, "long"),
        insert(103, 2, "short"),
        record(104, "COMMIT", "short"),
        record(115, "COMMIT", "long"),
    ]
    windows = install(monkeypatch, records, sink)
    first = Client(109)
    invoke(first, sink)
    assert set(sink.rows) == {2}
    assert sink.saved["streaming"] == {
        "low_watermark_scn": "100",
        "processed_through_scn": "109",
        "high_watermark_commit_scn": "104",
    }
    second = Client(119)
    invoke(second, sink)
    assert set(sink.rows) == {1, 2}
    assert sink.calls.count("upsert") == 3  # short transaction replays
    assert sink.saved["streaming"]["low_watermark_scn"] == "120"
    assert first.target_reads == second.target_reads == 1
    assert windows == [(100, 109), (100, 109), (110, 119)]


def test_rollback_across_invocations_never_emits_uncommitted_changes(monkeypatch):
    sink = Sink()
    install(monkeypatch, [insert(100, 1), record(115, "ROLLBACK")], sink)
    invoke(Client(109), sink)
    assert sink.rows == {}
    assert sink.saved["streaming"]["low_watermark_scn"] == "100"
    invoke(Client(119), sink)
    assert sink.rows == {}
    assert sink.saved["streaming"]["low_watermark_scn"] == "120"


def test_window_limit_returns_and_resume_reaches_fixed_target(monkeypatch):
    sink = Sink()
    windows = install(monkeypatch, [], sink)
    client = Client(129)
    cfg = config(max_mining_windows_per_invocation=1)
    for expected_low in ("110", "120", "130"):
        invoke(client, sink, cfg)
        assert sink.saved["streaming"]["low_watermark_scn"] == expected_low
    assert windows == [(100, 109), (110, 119), (120, 129)]
    assert client.target_reads == 3


@pytest.mark.parametrize(
    "cfg",
    [
        config(max_transaction_events=1),
        config(max_open_transactions=1),
        config(max_single_transaction_bytes=1),
        config(max_transaction_buffer_bytes=1),
    ],
)
def test_buffer_failure_cannot_checkpoint_or_emit_partial_transaction(monkeypatch, cfg):
    sink = Sink()
    install(monkeypatch, [insert(100, 1), insert(101, 2, "2")], sink)
    with pytest.raises(TransactionBufferLimitError):
        invoke(Client(109), sink, cfg)
    assert sink.calls == []
    assert sink.saved == initial_state()


def test_missing_redo_does_not_checkpoint(monkeypatch):
    sink = Sink()
    install(monkeypatch, [record(100, "MISSING_SCN")], sink)
    with pytest.raises(MissingRedoLogError):
        invoke(Client(109), sink)
    assert sink.calls == []
    assert sink.saved == initial_state()


def test_read_failure_replays_without_advancing_watermark(monkeypatch):
    sink = Sink()
    records = [insert(100, 1), record(105, "COMMIT")]
    install(monkeypatch, records, sink, failure_after_read=105)
    with pytest.raises(InjectedFailure):
        invoke(Client(109), sink)
    assert sink.rows == {}
    assert sink.saved == initial_state()
    install(monkeypatch, records, sink)
    invoke(Client(109), sink)
    assert set(sink.rows) == {1}


def test_explicit_null_partial_update_and_delete_survive_replay(monkeypatch):
    sink = Sink("before_checkpoint")
    records = [
        insert(100, 1),
        record(101, "COMMIT"),
        record(102, "UPDATE", "2", 'update "A"."T" set "VALUE" = NULL where "ID" = 1;'),
        record(103, "COMMIT", "2"),
        record(104, "DELETE", "3", 'delete from "A"."T" where "ID" = 1;'),
        record(105, "COMMIT", "3"),
    ]
    install(monkeypatch, records, sink)
    with pytest.raises(InjectedFailure):
        invoke(Client(109), sink)
    invoke(Client(109), sink)
    assert sink.rows[1] == {"id": 1, "value": None, "_fivetran_deleted": True}
    assert sink.calls.count("delete") == 2
    assert sink.saved["streaming"]["low_watermark_scn"] == "110"


def test_incomplete_continuation_pins_restart_until_reassembled(monkeypatch):
    sink = Sink()
    first = insert(100, 1)
    sql = first.sql_redo
    assert sql is not None
    fragments = [
        replace(first, csf=1, sql_redo=sql[:20]),
        replace(first, scn=110, csf=0, sql_redo=sql[20:]),
        record(115, "COMMIT"),
    ]
    install(monkeypatch, fragments, sink)
    invoke(Client(109), sink)
    assert sink.rows == {}
    assert sink.saved["streaming"]["low_watermark_scn"] == "100"
    invoke(Client(119), sink)
    assert set(sink.rows) == {1}
    assert sink.saved["streaming"]["low_watermark_scn"] == "120"


def test_runtime_budget_returns_without_advancing_unread_redo(monkeypatch):
    sink = Sink()
    windows = install(monkeypatch, [insert(100, 1)], sink)
    run_logminer_sync(
        Client(109),
        config(),
        ConnectorState.load(sink.saved),
        SimpleNamespace(nearly_exhausted=lambda: True),
    )
    assert windows == []
    assert sink.calls == []
    assert sink.saved == initial_state()


def test_ddl_schedules_reconciliation_without_advancing_watermark(monkeypatch):
    sink = Sink()
    ddl = replace(
        record(105, "UPDATE"),
        operation="DDL",
        operation_code=5,
        sql_redo='alter table "A"."T" add "UNSELECTED" number;',
    )
    install(monkeypatch, [ddl, insert(106, 2), record(107, "COMMIT")], sink)
    invoke(Client(109), sink)
    assert sink.saved["phase"] == "snapshot"
    assert sink.saved["snapshot"]["reconcile"]
    assert sink.saved["snapshot"]["contracts"]["A.T"] == table().to_dict()
    assert sink.saved["streaming"]["low_watermark_scn"] == "100"
    assert sink.calls == ["checkpoint"]


def test_snapshot_boundary_suppresses_already_snapshotted_transactions(monkeypatch):
    sink = Sink()
    sink.saved["snapshot"]["capture_boundary_scn"] = "104"
    install(
        monkeypatch,
        [
            insert(100, 1),
            record(102, "COMMIT"),
            insert(103, 2, "2"),
            record(105, "COMMIT", "2"),
        ],
        sink,
    )
    invoke(Client(109), sink)
    assert set(sink.rows) == {2}
    assert sink.saved["streaming"]["high_watermark_commit_scn"] == "105"


def test_lob_operation_does_not_hide_scalar_dml_in_same_transaction(monkeypatch):
    sink = Sink()
    lob = replace(
        record(101, "UPDATE"), operation="LOB_WRITE", operation_code=10, sql_redo=None
    )
    install(monkeypatch, [insert(100, 1), lob, record(105, "COMMIT")], sink)
    invoke(Client(109), sink)
    assert set(sink.rows) == {1}


def test_mid_window_budget_discards_buffer_without_checkpoint(monkeypatch):
    sink = Sink()
    install(monkeypatch, [insert(100, 1), record(105, "COMMIT")], sink)
    checks = iter([False, False, True])
    run_logminer_sync(
        Client(109),
        config(),
        ConnectorState.load(sink.saved),
        SimpleNamespace(nearly_exhausted=lambda: next(checks)),
    )
    assert sink.calls == [] and sink.saved == initial_state()
