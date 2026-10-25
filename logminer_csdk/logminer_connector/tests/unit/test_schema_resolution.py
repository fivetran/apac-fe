from dataclasses import replace

import pytest
from test_logminer_restart import initial_state, table

from errors import SchemaHistoryUnavailableError
from schema_evolution.schema_history import (
    activate_schema_version,
    resolve_schema_version,
)
from state import ConnectorState


def test_pre_and_post_ddl_versions_use_event_boundary():
    state = ConnectorState.load(initial_state())
    old = table()
    new = replace(old, columns=(old.columns[0], replace(old.columns[1], length=100)))
    activate_schema_version(state, new, 110, "test")
    assert resolve_schema_version(state, old.source_key, 109)[0] == old
    assert resolve_schema_version(state, old.source_key, 110)[0] == new
    with pytest.raises(SchemaHistoryUnavailableError):
        resolve_schema_version(state, old.source_key, 99)


def test_schema_history_required_by_replay_cannot_be_evicted():
    state = ConnectorState.load(initial_state())
    old = table()
    new = replace(old, columns=(old.columns[0], replace(old.columns[1], length=100)))
    activate_schema_version(state, new, 110, "test")
    newest = replace(new, columns=(new.columns[0], replace(new.columns[1], length=200)))
    with pytest.raises(SchemaHistoryUnavailableError):
        activate_schema_version(state, newest, 120, "test")
    assert resolve_schema_version(state, old.source_key, 100)[0] == old
