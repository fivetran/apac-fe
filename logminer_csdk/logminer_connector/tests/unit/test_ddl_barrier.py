import pytest

from errors import SchemaRefreshRequiredError
from schema_evolution.ddl_barrier import open_schema_change_barrier
from schema_models import ColumnSchema, TableSchema
from state import ConnectorState


def schemas():
    base = ColumnSchema("ID", 1, "NUMBER", 22, 10, 0, None, False, None)
    added = ColumnSchema("NEW_COL", 2, "VARCHAR2", 20, None, None, "B", True, None)
    old = TableSchema("A", "T", 1, 1, (base,), ("ID",))
    new = TableSchema("A", "T", 1, 1, (base, added), ("ID",))
    return old, new


def test_barrier_persists_pending_change_and_pins_low_watermark():
    state = ConnectorState()
    state.phase = "streaming"
    state.streaming.low_watermark_scn = "200"
    old, new = schemas()
    with pytest.raises(SchemaRefreshRequiredError):
        open_schema_change_barrier(state, old, new, 250, 240)
    assert state.pending_schema_change["ddl_scn"] == "250"
    assert state.streaming.low_watermark_scn == "200"
    assert state.pending_schema_change["expected_new_fingerprint"] == new.fingerprint


def test_barrier_ignores_a_schema_fingerprint_noop():
    state = ConnectorState()
    state.phase = "streaming"
    state.streaming.low_watermark_scn = "200"
    old, _ = schemas()
    open_schema_change_barrier(state, old, old, 250, 240)
    assert state.pending_schema_change is None
    assert state.streaming.low_watermark_scn == "200"
