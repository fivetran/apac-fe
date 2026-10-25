"""Legacy publication barriers migrate to the approved resnapshot workflow."""

from test_handover_features import table

from state import ConnectorState


def test_legacy_pending_barrier_retains_contract_for_reconciliation():
    state = ConnectorState(phase="streaming")
    state.snapshot.table_schema = table().to_dict()
    state.pending_schema_change = {"ddl_scn": "250", "safe_replay_scn": "245"}
    state.streaming.low_watermark_scn = "240"
    state.request_resnapshot("migration")
    restored = ConnectorState.load(state.to_dict())
    assert restored.phase == "snapshot"
    assert restored.pending_schema_change is None
    assert restored.snapshot.contracts["A.T"] == table().to_dict()
    assert restored.snapshot.reconcile
    assert restored.streaming.low_watermark_scn == "240"
