"""Contracts against the installed SDK serializer and operation stream."""

import json
import threading

import pytest
from fivetran_connector_sdk import Connector, Operations
from fivetran_connector_sdk.operation_stream import _OperationStream


def test_connector_accepts_schema_and_plain_update_callbacks():
    def schema(configuration):
        return [{"table": "test", "primary_key": ["id"]}]

    def update(configuration, state):
        return None

    assert isinstance(Connector(update=update, schema=schema), Connector)


def test_sdk_orders_records_before_acknowledged_checkpoint(monkeypatch):
    stream = _OperationStream()
    monkeypatch.setattr(Operations, "operation_stream", stream)
    monkeypatch.setattr("fivetran_connector_sdk.operations._get_columns", lambda _: {})
    complete = threading.Event()
    failures = []

    def produce():
        try:
            assert Operations.upsert("test", {"id": 920726000001, "value": "x"}) is None
            assert (
                Operations.update("test", {"id": 920726000001, "value": None}) is None
            )
            assert Operations.delete("test", {"id": 920726000001}) is None
            assert Operations.checkpoint({"low_watermark_scn": "123"}) is None
        except (AssertionError, RuntimeError, ValueError, TypeError) as exc:
            failures.append(exc)
        finally:
            stream.mark_done()
            complete.set()

    producer = threading.Thread(target=produce)
    producer.start()
    try:
        responses = next(stream)
        assert isinstance(responses, list)
        assert len(responses) == 2
        records = responses[0].structured_records.structured_records
        assert len(records) == 3
        assert records[0].data["id"].long == 920726000001
        assert records[1].data["value"].WhichOneof("inner") == "null"
        assert set(records[2].data) == {"id"}
        assert len({record.type for record in records}) == 3
        assert json.loads(responses[1].checkpoint.state_json) == {
            "low_watermark_scn": "123"
        }
        assert not complete.is_set()
    finally:
        stream.unblock()
        producer.join(timeout=5)
    assert not producer.is_alive()
    assert not failures
    with pytest.raises(StopIteration):
        next(stream)
