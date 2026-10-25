"""Internal LogMiner records and typed DML events."""

from dataclasses import dataclass, field


class _Unset:
    def __repr__(self) -> str:
        return "UNSET"


UNSET = _Unset()


@dataclass(frozen=True)
class RedoRecord:
    scn: int
    commit_scn: int | None
    operation: str
    operation_code: int
    xid: str | None
    owner: str | None
    table: str | None
    sql_redo: str | None
    csf: int
    rs_id: str | None
    ssn: int | None
    thread: int | None
    sequence: int | None
    row_id: str | None
    rollback: bool = False
    status: int = 0


@dataclass(frozen=True)
class DmlEvent:
    transaction_id: str
    transaction_sequence: int
    event_scn: int
    table_key: str
    destination_table: str
    operation: str
    values: dict
    keys: dict
    schema_version_id: str
    estimated_bytes: int
    row_id: str | None = None


@dataclass
class Transaction:
    transaction_id: str
    start_scn: int
    events: list[DmlEvent] = field(default_factory=list)
    estimated_bytes: int = 0
    last_seen_scn: int = 0
