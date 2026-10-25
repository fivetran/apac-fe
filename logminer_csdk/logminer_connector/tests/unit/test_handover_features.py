"""Behavior regressions for the approved client scope."""

import copy
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from configuration import ConnectorConfig
from errors import (
    ConfigurationError,
    RedoParseError,
    SchemaMismatchError,
    UnsupportedThinModeFeatureError,
)
from logminer.commit_emitter import emit_committed
from logminer.continuation import ContinuationAssembler
from logminer.models import DmlEvent, RedoRecord
from logminer.parser import parse_sql_redo
from runtime_budget import RuntimeBudget
from schema_models import ColumnSchema, TableSchema
from snapshot import run_snapshot
from state import ConnectorState
from type_mapping import convert_snapshot_value


def config(**extra):
    return ConnectorConfig.from_mapping(
        {
            "host": "example.invalid",
            "service_name": "service",
            "username": "test",
            "password": "synthetic",
            "tables": json.dumps({"A.T": ["ID", "VALUE"], "A.U": ["ID", "VALUE"]}),
            **extra,
        }
    )


def table(name="T"):
    return TableSchema(
        "A",
        name,
        1 if name == "T" else 2,
        1,
        (
            ColumnSchema("ID", 1, "NUMBER", 22, 10, 0, None, False, None),
            ColumnSchema("VALUE", 2, "VARCHAR2", 20, None, None, "B", True, None),
            ColumnSchema("PAYLOAD", 3, "CLOB", 4000, None, None, None, True, None),
        ),
        ("ID",),
    ).select(("VALUE",))


class Sink:
    def __init__(self):
        self.rows = {}
        self.calls = []
        self.saved = None

    def checkpoint(self, state):
        self.saved = copy.deepcopy(state)
        self.calls.append(("checkpoint", None))

    def upsert(self, table, data):
        self.rows[(table, data["id"])] = data
        self.calls.append(("upsert", table))

    def delete(self, table, keys):
        self.rows.pop((table, keys["id"]), None)
        self.calls.append(("delete", keys["id"]))

    def truncate(self, table):
        self.rows = {key: value for key, value in self.rows.items() if key[0] != table}
        self.calls.append(("truncate", table))


class Client:
    def __init__(self):
        self.tables = [table(), table("U")]
        self.boundaries = 0
        self.reads = []

    def discover_tables(self):
        return self.tables

    def capture_boundary(self):
        self.boundaries += 1
        return 200, 150

    def fetch_historical_page(self, table_schema, last_key, fetch_size, snapshot_scn):
        self.reads.append((table_schema.source_key, snapshot_scn))
        return [(1, "value")] if not last_key else []


def test_config_multiple_tables_and_automatic_keys():
    assert [item.source_key for item in config().selected_tables] == ["A.T", "A.U"]
    assert [column.name for column in table().replicated_columns] == ["ID", "VALUE"]
    assert "payload" not in table().sdk_definition()["columns"]


@pytest.mark.parametrize(
    "extra", [{"logminer_batch_initial_scn_span": "100"}, {"mispelled": "true"}]
)
def test_unknown_configuration_cannot_silently_use_defaults(extra):
    with pytest.raises(ConfigurationError):
        config(**extra)


def test_selected_lob_is_excluded_without_reading():
    class LOB:
        def read(self):
            raise AssertionError("LOB must never be fetched")

    with pytest.raises(UnsupportedThinModeFeatureError):
        convert_snapshot_value(LOB(), {"data_type": "CLOB"}, 1)
    assert "PAYLOAD" not in table().select(("PAYLOAD",)).selected_columns


def test_parser_ignores_excluded_lob_and_new_column_expressions():
    values, keys = parse_sql_redo(
        'insert into "A"."T" ("ID","VALUE","PAYLOAD") values (1,\'x\',EMPTY_CLOB());',
        "INSERT",
        table(),
    )
    assert values == {"id": 1, "value": "x"} and keys == {"id": 1}
    values, keys = parse_sql_redo(
        'update "A"."T" set "PAYLOAD" = EMPTY_CLOB(), "VALUE" = NULL where "ID" = 1;',
        "UPDATE",
        table(),
    )
    assert values == {"value": None} and keys == {"id": 1}


def test_multi_table_snapshot_resumes_at_one_scn(monkeypatch):
    sink = Sink()
    monkeypatch.setattr("snapshot.op", sink)
    client = Client()
    state = ConnectorState()
    cfg = config(snapshot_rows_per_invocation="1")
    for _ in range(4):
        run_snapshot(client, cfg, state, RuntimeBudget.start(600))
        state = ConnectorState.load(sink.saved)
        if state.phase == "streaming":
            break
    assert state.phase == "streaming" and client.boundaries == 1
    assert {scn for _, scn in client.reads} == {200}
    assert set(sink.rows) == {("a_t", 1), ("a_u", 1)}
    assert state.streaming.low_watermark_scn == "150"


def test_ddl_resnapshot_truncates_once_and_freezes_columns(monkeypatch):
    sink = Sink()
    monkeypatch.setattr("snapshot.op", sink)
    client = Client()
    state = ConnectorState()
    run_snapshot(client, config(), state, RuntimeBudget.start(600))
    state.request_resnapshot("DDL")
    extra = ColumnSchema("ADDED", 4, "VARCHAR2", 40, None, None, "B", True, None)
    client.tables = [
        replace(source, columns=(*source.columns, extra)) for source in client.tables
    ]
    run_snapshot(
        client,
        config(snapshot_rows_per_invocation="1"),
        state,
        RuntimeBudget.start(600),
    )
    restored = ConnectorState.load(sink.saved)
    run_snapshot(client, config(), restored, RuntimeBudget.start(600))
    assert restored.phase == "streaming"
    assert len([call for call in sink.calls if call[0] == "truncate"]) == 2
    for raw in restored.table_schemas().values():
        assert "added" not in TableSchema.from_dict(raw).sdk_definition()["columns"]


def test_selected_column_drop_and_pk_definition_change_fail():
    original = table()
    with pytest.raises(SchemaMismatchError):
        replace(original, columns=original.columns[:1]).retain_contract(original)
    with pytest.raises(SchemaMismatchError):
        replace(original, primary_key=("VALUE",)).retain_contract(original)


def test_continuation_limit_preserves_replay_position():
    record = RedoRecord(
        100, None, "INSERT", 1, "1", "A", "T", "abcd", 1, "r", 1, 1, 1, "row"
    )
    assembler = ContinuationAssembler(max_bytes=6, max_fragments=2)
    assert assembler.add(record) is None
    with pytest.raises(RedoParseError):
        assembler.add(record)
    assert assembler.incomplete_scn == 100 and len(assembler._parts) == 1


def event(old, new, table_key="A.T"):
    return DmlEvent(
        "1",
        1,
        100,
        table_key,
        table_key.lower().replace(".", "_"),
        "UPDATE",
        {"id": new},
        {"id": old},
        "v1",
        100,
    )


def test_key_swap_deletes_all_old_keys_before_complete_upserts(monkeypatch):
    sink = Sink()
    monkeypatch.setattr("logminer.commit_emitter.op", sink)
    source = table()
    reads = []

    def fetch(schema, keys, scn):
        reads.append((keys["id"], scn))
        return (keys["id"], "final")

    emit_committed(
        [event(1, 2), event(2, 1)],
        120,
        {"A.T": source},
        SimpleNamespace(fetch_committed_row=fetch),
        config(),
        RuntimeBudget.start(600),
        lambda _: pytest.fail("partial emitter must not run"),
    )
    assert reads == [(1, 120), (2, 120)]
    assert [call[0] for call in sink.calls] == ["delete", "delete", "upsert", "upsert"]
    assert set(sink.rows) == {("a_t", 1), ("a_t", 2)}
    assert all(row["value"] == "final" for row in sink.rows.values())


def test_key_move_then_delete_does_not_invent_after_image(monkeypatch):
    sink = Sink()
    monkeypatch.setattr("logminer.commit_emitter.op", sink)
    emit_committed(
        [event(1, 2)],
        120,
        {"A.T": table()},
        SimpleNamespace(fetch_committed_row=lambda *args: None),
        config(),
        RuntimeBudget.start(600),
        lambda _: None,
    )
    assert [call[0] for call in sink.calls] == ["delete", "delete"]


def test_schema_callback_and_scope_change(monkeypatch):
    import connector

    client = Client()
    client.__class__.__enter__ = lambda self: self
    client.__class__.__exit__ = lambda *args: None
    client.source_identity = lambda: "db:1"
    monkeypatch.setattr(connector, "OracleClient", lambda _: client)
    raw = {
        "host": "example.invalid",
        "service_name": "service",
        "username": "test",
        "password": "synthetic",
        "tables": json.dumps({"A.T": ["ID", "VALUE"], "A.U": ["ID", "VALUE"]}),
    }
    assert len(connector.schema(raw)) == 2
    state = ConnectorState(scope_fingerprint="different")
    with pytest.raises(SchemaMismatchError):
        connector.update(raw, state.to_dict())


def test_frozen_selection_replays_unselected_columns_removed_by_ddl():
    values, keys = parse_sql_redo(
        'update "A"."T" set "REMOVED" = 42, "VALUE" = \'final\' where "ID" = 1;',
        "UPDATE",
        table(),
    )
    assert values == {"value": "final"} and keys == {"id": 1}


def test_selected_type_narrowing_and_destination_widening_fail():
    original = table()
    value = original.columns[1]
    with pytest.raises(SchemaMismatchError):
        replace(
            original,
            columns=(
                original.columns[0],
                replace(value, length=10),
                original.columns[2],
            ),
        ).retain_contract(original)
    wider = replace(
        original,
        columns=(original.columns[0], replace(value, length=100), original.columns[2]),
    )
    assert wider.retain_contract(original).sdk_definition() == original.sdk_definition()
    key = original.columns[0]
    with pytest.raises(SchemaMismatchError):
        replace(
            original, columns=(replace(key, precision=38), *original.columns[1:])
        ).retain_contract(original)


def test_continuation_retains_intermediate_failure_status():
    first = RedoRecord(
        100, None, "INSERT", 1, "1", "A", "T", "a", 1, "r", 1, 1, 1, "row"
    )
    assembler = ContinuationAssembler()
    assert assembler.add(first) is None
    assert assembler.add(replace(first, sql_redo="b", status=2)) is None
    assembled = assembler.add(replace(first, sql_redo="c", csf=0))
    assert assembled.status == 2 and assembled.sql_redo == "abc"


@pytest.mark.parametrize("damage", ["index", "order", "completed", "identity"])
def test_corrupt_snapshot_progress_cannot_skip_tables(monkeypatch, damage):
    from errors import IncompatibleStateError

    sink = Sink()
    monkeypatch.setattr("snapshot.op", sink)
    state = ConnectorState()
    run_snapshot(
        Client(),
        config(snapshot_rows_per_invocation="1"),
        state,
        RuntimeBudget.start(600),
    )
    raw = copy.deepcopy(sink.saved)
    snap = raw["snapshot"]
    if damage == "index":
        snap["table_index"] = 99
    elif damage == "order":
        snap["table_order"] = ["A.T", "A.T"]
    elif damage == "completed":
        snap["table_index"] = 1
    else:
        snap["tables"]["A.T"]["table_schema"]["name"] = "WRONG"
    with pytest.raises(IncompatibleStateError):
        ConnectorState.load(raw)


def test_decimal_precision_or_scale_change_cannot_silently_change_contract():
    original = table()
    value = replace(
        original.columns[1], data_type="NUMBER", precision=12, scale=2, char_used=None
    )
    original = replace(
        original, columns=(original.columns[0], value, original.columns[2])
    )
    changed = replace(
        original,
        columns=(
            original.columns[0],
            replace(value, precision=14, scale=3),
            original.columns[2],
        ),
    )
    with pytest.raises(SchemaMismatchError):
        changed.retain_contract(original)


def test_oracle_password_preserves_significant_whitespace():
    assert config(password=" synthetic ").password == " synthetic "


@pytest.mark.parametrize(
    "oracle_type",
    [
        "TIMESTAMP WITH TIME ZONE",
        "TIMESTAMP(6) WITH TIME ZONE",
        "TIMESTAMP WITH LOCAL TIME ZONE",
        "TIMESTAMP(6) WITH LOCAL TIME ZONE",
    ],
)
def test_timezone_types_stop_instead_of_losing_offsets(oracle_type):
    from type_mapping import sdk_type_for

    with pytest.raises(UnsupportedThinModeFeatureError):
        sdk_type_for({"data_type": oracle_type})


def test_selected_unsupported_type_fails_before_snapshot_operations():
    original = table()
    changed = replace(
        original,
        columns=(
            original.columns[0],
            replace(original.columns[1], data_type="TIMESTAMP(6) WITH TIME ZONE"),
            original.columns[2],
        ),
    )
    with pytest.raises(UnsupportedThinModeFeatureError):
        changed.select(("VALUE",))
    assert changed.select(("ID",)).sdk_definition()["columns"] == {"id": "LONG"}


@pytest.mark.parametrize(
    "metadata",
    [{"data_type": "TIMESTAMP(7)", "scale": 7}, {"data_type": "TIMESTAMP(9)"}],
)
def test_submicrosecond_timestamp_metadata_is_rejected_before_fetch(metadata):
    from type_mapping import sdk_type_for

    with pytest.raises(UnsupportedThinModeFeatureError):
        sdk_type_for(metadata)
