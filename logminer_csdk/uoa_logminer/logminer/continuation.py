"""Assemble SQL_REDO continuation fragments without partial parsing."""

from errors import RedoParseError
from logminer.models import RedoRecord


class ContinuationAssembler:
    def __init__(
        self, max_bytes: int = 16 * 1024 * 1024, max_fragments: int = 8192
    ) -> None:
        self.max_bytes = max_bytes
        self.max_fragments = max_fragments
        self._bytes = 0
        self._status = 0
        self._parts: list[str] = []
        self._first_scn: int | None = None
        self._template: RedoRecord | None = None

    @property
    def incomplete_scn(self) -> int | None:
        return self._first_scn

    def add(self, record: RedoRecord) -> RedoRecord | None:
        fragment = record.sql_redo or ""
        size = len(fragment.encode("utf-8"))
        if (
            self._bytes + size > self.max_bytes
            or len(self._parts) + 1 > self.max_fragments
        ):
            raise RedoParseError(
                "SQL continuation exceeds configured byte/fragment limit"
            )
        self._bytes += size
        self._status = max(self._status, record.status)
        if self._parts:
            if self._template is None:
                raise RedoParseError("Continuation assembler is corrupt")
            if record.scn < self._template.scn:
                raise RedoParseError("Continuation fragments are out of order")
            if (
                record.xid,
                record.rs_id,
                record.ssn,
                record.rollback,
                record.operation_code,
                record.row_id,
            ) != (
                self._template.xid,
                self._template.rs_id,
                self._template.ssn,
                self._template.rollback,
                self._template.operation_code,
                self._template.row_id,
            ):
                raise RedoParseError(
                    "Continuation fragments have different logical identities"
                )
            self._parts.append(fragment)
        else:
            self._first_scn = record.scn
            self._template = record
            self._parts = [fragment]
        if record.csf == 1:
            return None
        template = self._template
        if template is None:
            raise RedoParseError("Continuation record is missing its first fragment")
        assembled = RedoRecord(
            scn=template.scn,
            commit_scn=record.commit_scn or template.commit_scn,
            operation=template.operation,
            operation_code=template.operation_code,
            xid=template.xid,
            owner=template.owner,
            table=template.table,
            sql_redo="".join(self._parts),
            csf=0,
            rs_id=template.rs_id,
            ssn=template.ssn,
            thread=template.thread,
            sequence=template.sequence,
            row_id=template.row_id,
            rollback=template.rollback,
            status=self._status,
        )
        self._parts = []
        self._bytes = 0
        self._status = 0
        self._first_scn = None
        self._template = None
        return assembled
