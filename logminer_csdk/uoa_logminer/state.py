"""Versioned, compact, replay-safe Connector SDK state."""

import json
from dataclasses import dataclass, field

from errors import IncompatibleStateError, ResnapshotRequiredError

STATE_VERSION = 4
MAX_STATE_BYTES = 9 * 1024 * 1024


@dataclass
class SnapshotState:
    read_mode: str = "flashback"
    capture_boundary_scn: str | None = None
    capture_start_scn: str | None = None
    last_key: list = field(default_factory=list)
    completed: bool = False
    table_schema: dict | None = None
    tables: dict = field(default_factory=dict)
    table_order: list[str] = field(default_factory=list)
    table_index: int = 0
    reconcile: bool = False
    contracts: dict = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "read_mode": self.read_mode,
            "capture_boundary_scn": self.capture_boundary_scn,
            "capture_start_scn": self.capture_start_scn,
            "last_key": self.last_key,
            "completed": self.completed,
            "table_schema": self.table_schema,
            "tables": self.tables,
            "table_order": self.table_order,
            "table_index": self.table_index,
            "reconcile": self.reconcile,
            "contracts": self.contracts,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "SnapshotState":
        return cls(
            read_mode=value.get("read_mode", "flashback"),
            capture_boundary_scn=value.get("capture_boundary_scn"),
            capture_start_scn=value.get("capture_start_scn"),
            last_key=list(value.get("last_key", [])),
            completed=bool(value.get("completed", False)),
            table_schema=value.get("table_schema"),
            tables=dict(value.get("tables", {})),
            table_order=list(value.get("table_order", [])),
            table_index=int(value.get("table_index", 0)),
            reconcile=bool(value.get("reconcile", False)),
            contracts=dict(value.get("contracts", {})),
            reason=value.get("reason"),
        )


@dataclass
class StreamingState:
    low_watermark_scn: str | None = None
    processed_through_scn: str | None = None
    high_watermark_commit_scn: str | None = None

    def to_dict(self) -> dict:
        return {
            "low_watermark_scn": self.low_watermark_scn,
            "processed_through_scn": self.processed_through_scn,
            "high_watermark_commit_scn": self.high_watermark_commit_scn,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "StreamingState":
        return cls(
            low_watermark_scn=value.get("low_watermark_scn"),
            processed_through_scn=value.get("processed_through_scn"),
            high_watermark_commit_scn=value.get("high_watermark_commit_scn"),
        )


@dataclass
class ConnectorState:
    phase: str = "snapshot"
    snapshot: SnapshotState = field(default_factory=SnapshotState)
    streaming: StreamingState = field(default_factory=StreamingState)
    schema_history: dict = field(default_factory=dict)
    pending_schema_change: dict | None = None
    scope_fingerprint: str | None = None
    source_identity: str | None = None

    def table_schemas(self) -> dict:
        if self.snapshot.tables:
            return {
                key: value["table_schema"]
                for key, value in self.snapshot.tables.items()
            }
        if self.snapshot.table_schema:
            schema = self.snapshot.table_schema
            return {f"{schema['owner']}.{schema['name']}": schema}
        return {}

    def request_resnapshot(self, reason: str) -> None:
        contracts = self.table_schemas() or self.snapshot.contracts
        self.snapshot = SnapshotState(
            reconcile=True, contracts=contracts, reason=reason
        )
        self.phase = "snapshot"
        self.pending_schema_change = None

    def to_dict(self) -> dict:
        value = {
            "state_version": STATE_VERSION,
            "phase": self.phase,
            "snapshot": self.snapshot.to_dict(),
            "streaming": self.streaming.to_dict(),
            "schema_history": self.schema_history,
            "pending_schema_change": self.pending_schema_change,
            "scope_fingerprint": self.scope_fingerprint,
            "source_identity": self.source_identity,
        }
        encoded = json.dumps(value, separators=(",", ":"), default=str).encode("utf-8")
        if len(encoded) > MAX_STATE_BYTES:
            raise IncompatibleStateError(
                f"Connector state size {len(encoded)} exceeds {MAX_STATE_BYTES}"
            )
        return value

    @classmethod
    def load(cls, raw: dict) -> "ConnectorState":
        if not raw:
            return cls()
        version = raw.get("state_version")
        if version == 1:
            raw = _migrate_v1(raw)
            version = STATE_VERSION
        if version == 2:
            snapshot = dict(raw.get("snapshot", {}))
            if raw.get("phase") == "snapshot" and snapshot.get("capture_boundary_scn"):
                raise ResnapshotRequiredError(
                    "Unfinished capture-first snapshot cannot resume as Flashback; controlled resnapshot required"
                )
            raw = {
                **raw,
                "state_version": STATE_VERSION,
                "snapshot": {
                    **snapshot,
                    "read_mode": "flashback"
                    if raw.get("phase") == "snapshot"
                    else "legacy_completed",
                },
            }
            version = STATE_VERSION
        if version == 3:
            raw = {**raw, "state_version": STATE_VERSION}
            version = STATE_VERSION
        if version != STATE_VERSION:
            raise IncompatibleStateError(
                f"Unsupported state_version={version}; expected {STATE_VERSION}"
            )
        phase = raw.get("phase")
        if phase not in {"snapshot", "streaming"}:
            raise IncompatibleStateError(f"Invalid connector phase: {phase}")
        try:
            result = cls(
                phase=phase,
                snapshot=SnapshotState.from_dict(raw.get("snapshot", {})),
                streaming=StreamingState.from_dict(raw.get("streaming", {})),
                schema_history=dict(raw.get("schema_history", {})),
                pending_schema_change=raw.get("pending_schema_change"),
                scope_fingerprint=raw.get("scope_fingerprint"),
                source_identity=raw.get("source_identity"),
            )
            saved_snapshot = result.snapshot
            if saved_snapshot.tables:
                if (
                    len(saved_snapshot.table_order) != len(saved_snapshot.tables)
                    or set(saved_snapshot.table_order) != set(saved_snapshot.tables)
                    or not 0
                    <= saved_snapshot.table_index
                    <= len(saved_snapshot.table_order)
                    or any(
                        not saved_snapshot.tables[key].get("completed")
                        for key in saved_snapshot.table_order[
                            : saved_snapshot.table_index
                        ]
                    )
                ):
                    raise IncompatibleStateError("Snapshot table progress is corrupt")
                for key, progress in saved_snapshot.tables.items():
                    schema = progress["table_schema"]
                    if key != f"{schema['owner']}.{schema['name']}":
                        raise IncompatibleStateError(
                            "Snapshot table identity is corrupt"
                        )
            for value in (
                saved_snapshot.capture_boundary_scn,
                saved_snapshot.capture_start_scn,
                result.streaming.low_watermark_scn,
                result.streaming.processed_through_scn,
                result.streaming.high_watermark_commit_scn,
            ):
                if value is not None and (not str(value).isdigit() or int(value) < 0):
                    raise IncompatibleStateError("State SCN is corrupt")
            return result
        except (KeyError, TypeError, ValueError) as exc:
            raise IncompatibleStateError("Connector state is corrupt") from exc


def _migrate_v1(raw: dict) -> dict:
    snapshot = dict(raw.get("snapshot", {}))
    snapshot["capture_boundary_scn"] = snapshot.pop("snapshot_scn", None)
    snapshot["capture_start_scn"] = snapshot.pop("stream_start_scn", None)
    return {
        "state_version": STATE_VERSION,
        "phase": raw.get("phase"),
        "snapshot": snapshot,
        "streaming": dict(raw.get("streaming", {})),
        "schema_history": dict(raw.get("schema_history", {})),
        "pending_schema_change": raw.get("pending_schema_change"),
    }
