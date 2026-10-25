from dataclasses import replace

import pytest

from errors import RedoParseError, TransactionBufferLimitError
from logminer.models import DmlEvent
from logminer.transaction_buffer import TransactionBuffer


def event(transaction_id="1", sequence=1, scn=100, size=100):
    return DmlEvent(
        transaction_id=transaction_id,
        transaction_sequence=sequence,
        event_scn=scn,
        table_key="A.T",
        destination_table="a_t",
        operation="UPDATE",
        values={"value": sequence},
        keys={"id": 1},
        schema_version_id="v1",
        estimated_bytes=size,
    )


def buffer(**overrides):
    values = {
        "max_open_transactions": 2,
        "max_transaction_events": 10,
        "max_total_bytes": 1_000,
        "max_single_transaction_bytes": 500,
        "deployment_profile": "saas",
    }
    values.update(overrides)
    return TransactionBuffer(**values)


def test_commit_orders_and_removes_complete_transaction():
    transactions = buffer()
    transactions.append(event(sequence=2, scn=101))
    transactions.append(event(sequence=1, scn=100))
    committed = transactions.commit("1")
    assert [item.transaction_sequence for item in committed] == [1, 2]
    assert transactions.open_count == 0
    assert transactions.total_bytes == 0


def test_rollback_discards_transaction():
    transactions = buffer()
    transactions.append(event())
    transactions.rollback("1")
    assert transactions.commit("1") == []


def test_oldest_transaction_pins_watermark_input():
    transactions = buffer()
    transactions.append(event(transaction_id="late", scn=200))
    transactions.append(event(transaction_id="early", scn=100))
    assert transactions.oldest_start_scn == 100


def test_single_transaction_limit_fails_before_mutation():
    transactions = buffer(max_single_transaction_bytes=150)
    transactions.append(event(size=100))
    with pytest.raises(TransactionBufferLimitError, match="Hybrid"):
        transactions.append(event(sequence=2, size=100))
    assert transactions.total_events == 1


def test_savepoint_compensation_removes_only_latest_matching_row_change():
    transactions = buffer()
    transactions.append(
        replace(event(sequence=1), row_id="row1", values={"value": "kept"})
    )
    transactions.append(replace(event(sequence=2, scn=101), row_id="row2"))
    transactions.append(
        replace(event(sequence=3, scn=102), row_id="row1", values={"value": "undone"})
    )
    transactions.compensate("1", "A.T", "row1", "UPDATE")
    assert transactions.total_events == 2
    assert transactions.total_bytes == 200
    assert transactions.oldest_start_scn == 100
    result = transactions.commit("1")
    assert [item.row_id for item in result] == ["row1", "row2"]
    assert result[0].values == {"value": "kept"}


def test_compensated_empty_transaction_keeps_replay_pin_until_rollback():
    transactions = buffer()
    transactions.append(replace(event(), operation="INSERT", row_id="row1"))
    transactions.compensate("1", "A.T", "row1", "DELETE")
    assert transactions.total_events == transactions.total_bytes == 0
    assert transactions.oldest_start_scn == 100
    transactions.rollback("1")
    assert transactions.open_count == 0


@pytest.mark.parametrize(
    "row_id,operation", [(None, "UPDATE"), ("missing", "UPDATE"), ("row1", "INSERT")]
)
def test_ambiguous_compensation_fails_without_discarding_changes(row_id, operation):
    transactions = buffer()
    transactions.append(replace(event(), row_id="row1"))
    with pytest.raises(RedoParseError):
        transactions.compensate("1", "A.T", row_id, operation)
    assert transactions.total_events == 1
