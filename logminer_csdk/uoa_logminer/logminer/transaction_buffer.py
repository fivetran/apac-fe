"""Bounded, commit-aware in-memory transaction reconstruction."""

from errors import RedoParseError, TransactionBufferLimitError
from logminer.models import DmlEvent, Transaction


class TransactionBuffer:
    def __init__(
        self,
        max_open_transactions: int,
        max_transaction_events: int,
        max_total_bytes: int,
        max_single_transaction_bytes: int,
        deployment_profile: str,
    ):
        self.max_open_transactions = max_open_transactions
        self.max_transaction_events = max_transaction_events
        self.max_total_bytes = max_total_bytes
        self.max_single_transaction_bytes = max_single_transaction_bytes
        self.deployment_profile = deployment_profile
        self._transactions: dict[str, Transaction] = {}
        self.total_events = 0
        self.total_bytes = 0

    @property
    def open_count(self) -> int:
        return len(self._transactions)

    @property
    def oldest_start_scn(self) -> int | None:
        if not self._transactions:
            return None
        return min(tx.start_scn for tx in self._transactions.values())

    def append(self, event: DmlEvent) -> None:
        transaction = self._transactions.get(event.transaction_id)
        creating = transaction is None
        if creating:
            if self.open_count + 1 > self.max_open_transactions:
                self._raise_limit(
                    event.transaction_id,
                    event.event_scn,
                    1,
                    event.estimated_bytes,
                    "max_open_transactions",
                    self.max_open_transactions,
                )
            transaction = Transaction(
                transaction_id=event.transaction_id,
                start_scn=event.event_scn,
                last_seen_scn=event.event_scn,
            )
        assert transaction is not None
        new_transaction_bytes = transaction.estimated_bytes + event.estimated_bytes
        new_total_events = self.total_events + 1
        new_total_bytes = self.total_bytes + event.estimated_bytes
        if new_total_events > self.max_transaction_events:
            self._raise_limit(
                event.transaction_id,
                transaction.start_scn,
                len(transaction.events) + 1,
                new_transaction_bytes,
                "max_transaction_events",
                self.max_transaction_events,
            )
        if new_transaction_bytes > self.max_single_transaction_bytes:
            self._raise_limit(
                event.transaction_id,
                transaction.start_scn,
                len(transaction.events) + 1,
                new_transaction_bytes,
                "max_single_transaction_bytes",
                self.max_single_transaction_bytes,
            )
        if new_total_bytes > self.max_total_bytes:
            self._raise_limit(
                event.transaction_id,
                transaction.start_scn,
                len(transaction.events) + 1,
                new_transaction_bytes,
                "max_transaction_buffer_bytes",
                self.max_total_bytes,
            )
        if creating:
            self._transactions[event.transaction_id] = transaction
        transaction.events.append(event)
        transaction.estimated_bytes = new_transaction_bytes
        transaction.last_seen_scn = event.event_scn
        self.total_events = new_total_events
        self.total_bytes = new_total_bytes

    def commit(self, transaction_id: str) -> list[DmlEvent]:
        transaction = self._transactions.pop(transaction_id, None)
        if transaction is None:
            return []
        self.total_events -= len(transaction.events)
        self.total_bytes -= transaction.estimated_bytes
        return sorted(
            transaction.events,
            key=lambda event: (event.event_scn, event.transaction_sequence),
        )

    def rollback(self, transaction_id: str) -> None:
        transaction = self._transactions.pop(transaction_id, None)
        if transaction is None:
            return
        self.total_events -= len(transaction.events)
        self.total_bytes -= transaction.estimated_bytes

    def compensate(
        self,
        transaction_id: str,
        table_key: str,
        row_id: str | None,
        inverse_operation: str,
    ) -> None:
        """Undo the latest buffered row change, including savepoint rollbacks.

        Compensation SQL is not an ordinary source change and may omit keys.
        Keep the transaction's original start SCN pinned even when empty.
        """
        transaction = self._transactions.get(transaction_id)
        if transaction is None or not row_id:
            raise RedoParseError(
                "Rollback compensation has no reconstructable transaction/row identity"
            )
        expected = {"INSERT": "DELETE", "DELETE": "INSERT", "UPDATE": "UPDATE"}
        for index in range(len(transaction.events) - 1, -1, -1):
            event = transaction.events[index]
            if event.table_key != table_key or event.row_id != row_id:
                continue
            if expected.get(event.operation) != inverse_operation:
                raise RedoParseError(
                    "Rollback compensation operation does not match buffered change"
                )
            transaction.events.pop(index)
            transaction.estimated_bytes -= event.estimated_bytes
            self.total_bytes -= event.estimated_bytes
            self.total_events -= 1
            return
        raise RedoParseError(
            "Rollback compensation has no matching buffered row change"
        )

    def _raise_limit(
        self,
        transaction_id: str,
        start_scn: int,
        event_count: int,
        estimated_bytes: int,
        limit_name: str,
        limit: int,
    ) -> None:
        raise TransactionBufferLimitError(
            f"Transaction buffer limit exceeded: transaction_id={transaction_id}, "
            f"start_scn={start_scn}, observed_event_count={event_count}, "
            f"estimated_bytes={estimated_bytes}, {limit_name}={limit}, "
            f"deployment_profile={self.deployment_profile}. Use Hybrid Deployment "
            "or reduce source transaction size."
        )
