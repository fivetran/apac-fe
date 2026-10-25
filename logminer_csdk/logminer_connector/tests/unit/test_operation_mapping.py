from typing import ClassVar

from logminer.models import DmlEvent
from logminer.sync import _emit_event


class Operations:
    calls: ClassVar[list] = []

    @classmethod
    def reset(cls):
        cls.calls = []

    @classmethod
    def upsert(cls, **kwargs):
        cls.calls.append(("upsert", kwargs))

    @classmethod
    def update(cls, **kwargs):
        cls.calls.append(("update", kwargs))

    @classmethod
    def delete(cls, **kwargs):
        cls.calls.append(("delete", kwargs))

    @classmethod
    def truncate(cls, **kwargs):
        cls.calls.append(("truncate", kwargs))


class Logger:
    @staticmethod
    def info(message):
        return None


def event(operation, values, keys):
    return DmlEvent(
        transaction_id="1",
        transaction_sequence=1,
        event_scn=100,
        table_key="A.T",
        destination_table="a_t",
        operation=operation,
        values=values,
        keys=keys,
        schema_version_id="v1",
        estimated_bytes=100,
    )


def test_insert_uses_complete_upsert(monkeypatch):
    Operations.reset()
    monkeypatch.setattr("logminer.sync.op", Operations)
    _emit_event(event("INSERT", {"id": 1, "value": "x"}, {"id": 1}))
    assert Operations.calls == [
        ("upsert", {"table": "a_t", "data": {"id": 1, "value": "x"}})
    ]


def test_partial_update_includes_key_and_preserves_absent_columns(monkeypatch):
    Operations.reset()
    monkeypatch.setattr("logminer.sync.op", Operations)
    _emit_event(event("UPDATE", {"value": None}, {"id": 1}))
    assert Operations.calls == [
        (
            "update",
            {"table": "a_t", "modified": {"id": 1, "value": None}},
        )
    ]


def test_delete_uses_soft_delete_operation(monkeypatch):
    Operations.reset()
    monkeypatch.setattr("logminer.sync.op", Operations)
    _emit_event(event("DELETE", {}, {"id": 1}))
    assert Operations.calls == [("delete", {"table": "a_t", "keys": {"id": 1}})]
