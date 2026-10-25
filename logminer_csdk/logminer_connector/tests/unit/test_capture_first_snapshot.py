import time
from typing import ClassVar

from configuration import ConnectorConfig
from runtime_budget import RuntimeBudget
from schema_models import ColumnSchema, TableSchema
from snapshot import run_snapshot
from state import ConnectorState


class Operations:
    checkpoints: ClassVar[list] = []

    @classmethod
    def reset(cls):
        cls.checkpoints = []

    @classmethod
    def checkpoint(cls, state):
        cls.checkpoints.append(state)

    @classmethod
    def upsert(cls, **kwargs):
        raise AssertionError("empty historical table should not upsert")


class Client:
    def __init__(self, oldest_transaction_scn):
        self.oldest_transaction_scn = oldest_transaction_scn
        self.fetch_calls = []
        column = ColumnSchema("ID", 1, "NUMBER", 22, 10, 0, None, False, None)
        self.table = TableSchema("A", "T", 1, 1, (column,), ("ID",))

    def discover_table(self):
        return self.table

    def capture_boundary(self):
        return 200, self.oldest_transaction_scn

    def fetch_historical_page(self, table_schema, last_key, fetch_size, snapshot_scn):
        self.fetch_calls.append((table_schema, last_key, fetch_size, snapshot_scn))
        return []


def config():
    return ConnectorConfig.from_mapping(
        {
            "host": "db.example",
            "port": "1521",
            "service_name": "SERVICE",
            "username": "user",
            "password": "secret",
            "include_schema": "A",
            "include_table": "T",
        }
    )


def run(monkeypatch, oldest_transaction_scn):
    Operations.reset()
    monkeypatch.setattr("snapshot.op", Operations)
    client = Client(oldest_transaction_scn)
    state = ConnectorState()
    runtime = RuntimeBudget(time.monotonic(), 600)
    run_snapshot(client, config(), state, runtime)
    return client, state


def test_oldest_open_transaction_pins_capture_start(monkeypatch):
    client, state = run(monkeypatch, 150)
    assert state.snapshot.capture_boundary_scn == "200"
    assert state.snapshot.capture_start_scn == "150"
    assert state.streaming.low_watermark_scn == "150"
    assert state.phase == "streaming"
    assert len(client.fetch_calls) == 1
    assert client.fetch_calls[0][3] == 200
    assert Operations.checkpoints[0]["phase"] == "snapshot"
    assert Operations.checkpoints[-1]["phase"] == "streaming"


def test_no_open_transaction_starts_replay_at_boundary(monkeypatch):
    _, state = run(monkeypatch, None)
    assert state.snapshot.capture_start_scn == "200"
    assert state.streaming.low_watermark_scn == "200"
