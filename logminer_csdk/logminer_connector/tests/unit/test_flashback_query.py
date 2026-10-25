from contextlib import nullcontext
from types import SimpleNamespace

import oracledb
import pytest
from test_logminer_restart import config, table

from errors import ResnapshotRequiredError, SnapshotTooOldError
from oracle_client import OracleClient


def test_explicit_projection_keyset_and_original_snapshot_scn():
    calls = []
    cursor = SimpleNamespace(
        execute=lambda sql, binds, **options: calls.append((sql, binds, options)),
        fetchall=list,
    )
    client = OracleClient(config())
    client.cursor = lambda: nullcontext(cursor)
    client.fetch_historical_page(table(), [8], 5, snapshot_scn=123)
    sql, binds, options = calls[0]
    assert options == {"fetch_decimals": True}
    assert 'SELECT "ID", "VALUE"' in sql
    assert "AS OF SCN :snapshot_scn" in sql
    assert '"ID" > :key_0' in sql
    assert "OFFSET" not in sql
    assert binds == {"snapshot_scn": 123, "fetch_size": 5, "key_0": 8}


@pytest.mark.parametrize(
    "code,error",
    [
        (1555, SnapshotTooOldError),
        (8180, SnapshotTooOldError),
        (8181, SnapshotTooOldError),
        (1466, ResnapshotRequiredError),
    ],
)
def test_flashback_unavailable_fails_without_capturing_new_scn(code, error):
    def execute(sql, binds, **options):
        raise oracledb.DatabaseError(SimpleNamespace(code=code))

    client = OracleClient(config())
    client.cursor = lambda: nullcontext(SimpleNamespace(execute=execute))
    with pytest.raises(error):
        client.fetch_historical_page(table(), [], 1, snapshot_scn=123)


def test_sid_is_passed_to_thin_driver(monkeypatch):
    from dataclasses import replace

    calls = []
    connection = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(
        oracledb, "connect", lambda **kwargs: calls.append(kwargs) or connection
    )
    monkeypatch.setattr(oracledb, "is_thin_mode", lambda: True)
    with OracleClient(replace(config(), service_name=None, sid="DATABASE")):
        pass
    assert calls[0]["sid"] == "DATABASE"
    assert calls[0]["service_name"] is None
