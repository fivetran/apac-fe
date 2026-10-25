import json

import pytest

from errors import IncompatibleStateError, ResnapshotRequiredError
from state import STATE_VERSION, ConnectorState


def test_empty_state_starts_snapshot():
    state = ConnectorState.load({})
    assert state.phase == "snapshot"
    assert state.to_dict()["state_version"] == STATE_VERSION


def test_state_round_trip():
    state = ConnectorState.load({})
    state.snapshot.capture_boundary_scn = "123"
    state.snapshot.capture_start_scn = "100"
    state.snapshot.last_key = [
        {"type": "scalar", "value": 10},
        {"type": "scalar", "value": "A"},
    ]
    encoded = json.loads(json.dumps(state.to_dict()))
    decoded = ConnectorState.load(encoded)
    assert decoded.to_dict() == encoded


def test_unknown_state_version_is_rejected():
    with pytest.raises(IncompatibleStateError, match="state_version"):
        ConnectorState.load({"state_version": 999, "phase": "snapshot"})


def test_version_one_state_migrates_capture_positions():
    state = ConnectorState.load(
        {
            "state_version": 1,
            "phase": "snapshot",
            "snapshot": {
                "snapshot_scn": "123",
                "stream_start_scn": "100",
                "last_key": [],
                "completed": False,
                "table_schema": None,
            },
            "streaming": {},
            "schema_history": {},
            "pending_schema_change": None,
        }
    )
    assert state.snapshot.capture_boundary_scn == "123"
    assert state.snapshot.capture_start_scn == "100"
    assert state.to_dict()["state_version"] == STATE_VERSION


def test_invalid_phase_is_rejected():
    with pytest.raises(IncompatibleStateError, match="phase"):
        ConnectorState.load({"state_version": STATE_VERSION, "phase": "unknown"})


def test_unfinished_version_two_snapshot_requires_resnapshot():
    with pytest.raises(ResnapshotRequiredError):
        ConnectorState.load(
            {
                "state_version": 2,
                "phase": "snapshot",
                "snapshot": {"capture_boundary_scn": "123"},
            }
        )


def test_completed_version_two_state_keeps_streaming_position():
    state = ConnectorState.load(
        {
            "state_version": 2,
            "phase": "streaming",
            "snapshot": {"completed": True, "capture_boundary_scn": "123"},
            "streaming": {"low_watermark_scn": "100"},
        }
    )
    assert state.streaming.low_watermark_scn == "100"
    assert state.snapshot.read_mode == "legacy_completed"
