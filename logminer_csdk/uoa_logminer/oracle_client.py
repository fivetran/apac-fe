"""Oracle access isolated behind a thin-mode client."""

import contextlib
from dataclasses import replace
from typing import TYPE_CHECKING, Self

import oracledb

from configuration import ConnectorConfig
from errors import (
    MissingPrivilegeError,
    OracleConnectivityError,
    ResnapshotRequiredError,
    SchemaMismatchError,
    SnapshotTooOldError,
    SSHConnectionError,
    UnsupportedThinModeFeatureError,
)
from identifiers import quote_oracle_identifier
from schema_models import ColumnSchema, TableSchema
from selection import TableSelection
from type_mapping import exact_sdk_type_for_unconstrained_number_key

if TYPE_CHECKING:
    from ssh_tunnel import SSHTunnel


class OracleClient:
    def __init__(self, config: ConnectorConfig):
        self.config = config
        self.connection: oracledb.Connection | None = None
        self.tunnel: SSHTunnel | None = None

    def __enter__(self) -> Self:
        if not oracledb.is_thin_mode():
            raise UnsupportedThinModeFeatureError(
                "python-oracledb thick mode is not supported"
            )
        try:
            host, port = self.config.host, self.config.port
            if self.config.ssh is not None:
                from ssh_tunnel import SSHTunnel

                self.tunnel = SSHTunnel(
                    self.config.ssh, host, port, self.config.max_invocation_seconds
                )
                self.tunnel.__enter__()
                host, port = "127.0.0.1", self.tunnel.local_port
            self.connection = oracledb.connect(
                user=self.config.username,
                password=self.config.password,
                host=host,
                port=port,
                service_name=self.config.service_name,
                sid=self.config.sid,
                tcp_connect_timeout=10,
                retry_count=0,
                disable_oob=self.config.ssh is not None,
            )
            self.connection.call_timeout = (
                self.config.oracle_call_timeout_seconds * 1000
            )
        except SSHConnectionError:
            self.__exit__(None, None, None)
            raise
        except Exception:  # noqa: BLE001 -- release tunnel and redact driver errors on failed entry
            failed = self.tunnel is not None and self.tunnel.failed.is_set()
            self.__exit__(None, None, None)
            if self.config.ssh is not None and failed:
                raise SSHConnectionError(
                    "SSH forwarding failed during Oracle connection"
                ) from None
            raise OracleConnectivityError(
                "Unable to connect to the configured Oracle endpoint"
            ) from None
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            if self.connection is not None:
                self.connection.close()
        finally:
            self.connection = None
            if self.tunnel is not None:
                self.tunnel.close()
                self.tunnel = None

    @contextlib.contextmanager
    def cursor(self):
        if self.connection is None:
            raise OracleConnectivityError("Oracle connection is not open")
        cursor = self.connection.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    def current_scn(self) -> int:
        with self.cursor() as cursor:
            cursor.execute("SELECT CURRENT_SCN FROM V$DATABASE")
            return int(cursor.fetchone()[0])

    def source_identity(self) -> str:
        with self.cursor() as cursor:
            cursor.execute("SELECT DBID, RESETLOGS_CHANGE# FROM V$DATABASE")
            dbid, incarnation = cursor.fetchone()
            return f"{dbid}:{incarnation}"

    def capture_boundary(self) -> tuple[int, int | None]:
        """Atomically observe the current SCN and oldest open transaction."""
        try:
            with self.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT database.CURRENT_SCN, MIN(transactions.START_SCN)
                    FROM V$DATABASE database
                    LEFT JOIN V$TRANSACTION transactions ON 1 = 1
                    GROUP BY database.CURRENT_SCN
                    """
                )
                current_scn, oldest_transaction_scn = cursor.fetchone()
        except oracledb.Error as exc:
            raise MissingPrivilegeError(
                "Required read access to V$DATABASE and V$TRANSACTION is missing"
            ) from exc
        return (
            int(current_scn),
            (
                int(oldest_transaction_scn)
                if oldest_transaction_scn is not None
                else None
            ),
        )

    def basic_validation(self) -> dict:
        queries = {
            "version": "SELECT BANNER_FULL FROM V$VERSION WHERE ROWNUM = 1",
            "database": (
                "SELECT LOG_MODE, SUPPLEMENTAL_LOG_DATA_MIN, CURRENT_SCN "
                "FROM V$DATABASE"
            ),
        }
        result = {}
        try:
            with self.cursor() as cursor:
                cursor.execute(queries["version"])
                result["version"] = str(cursor.fetchone()[0])
                cursor.execute(queries["database"])
                database = cursor.fetchone()
                result["log_mode"] = str(database[0])
                result["supplemental_log_data_min"] = str(database[1])
                result["current_scn"] = str(database[2])
        except oracledb.Error as exc:
            raise MissingPrivilegeError(
                "Required read access to V$VERSION or V$DATABASE is missing"
            ) from exc
        return result

    def discover_tables(self) -> list[TableSchema]:
        tables = [
            self.discover_table(selection) for selection in self.config.selected_tables
        ]
        names = [table.destination_name for table in tables]
        if len(set(names)) != len(names):
            raise SchemaMismatchError(
                "Selected source tables collide in destination naming"
            )
        return tables

    def discover_table(self, selection: TableSelection | None = None) -> TableSchema:
        selection = selection or self.config.selected_tables[0]
        owner = selection.owner
        table = selection.name
        try:
            with self.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT OBJECT_ID, DATA_OBJECT_ID
                    FROM ALL_OBJECTS
                    WHERE OWNER = :owner
                      AND OBJECT_NAME = :table_name
                      AND OBJECT_TYPE = 'TABLE'
                    """,
                    owner=owner,
                    table_name=table,
                )
                identity = cursor.fetchone()
                if identity is None:
                    raise MissingPrivilegeError(
                        f"Included table {owner}.{table} is not accessible"
                    )
                cursor.execute(
                    """
                    SELECT COLUMN_NAME, COLUMN_ID, DATA_TYPE, DATA_LENGTH,
                           DATA_PRECISION, DATA_SCALE, CHAR_USED, NULLABLE,
                           DATA_DEFAULT
                    FROM ALL_TAB_COLUMNS
                    WHERE OWNER = :owner AND TABLE_NAME = :table_name
                    ORDER BY COLUMN_ID
                    """,
                    owner=owner,
                    table_name=table,
                )
                columns = tuple(
                    ColumnSchema(
                        name=str(row[0]),
                        column_id=int(row[1]),
                        data_type=str(row[2]),
                        length=int(row[3]) if row[3] is not None else None,
                        precision=int(row[4]) if row[4] is not None else None,
                        scale=int(row[5]) if row[5] is not None else None,
                        char_used=str(row[6]) if row[6] is not None else None,
                        nullable=str(row[7]) == "Y",
                        default=str(row[8]).strip() if row[8] is not None else None,
                    )
                    for row in cursor
                )
                cursor.execute(
                    """
                    SELECT columns.COLUMN_NAME
                    FROM ALL_CONSTRAINTS constraints
                    JOIN ALL_CONS_COLUMNS columns
                      ON columns.OWNER = constraints.OWNER
                     AND columns.CONSTRAINT_NAME = constraints.CONSTRAINT_NAME
                    WHERE constraints.OWNER = :owner
                      AND constraints.TABLE_NAME = :table_name
                      AND constraints.CONSTRAINT_TYPE = 'P'
                    ORDER BY columns.POSITION
                    """,
                    owner=owner,
                    table_name=table,
                )
                primary_key = tuple(str(row[0]) for row in cursor)
                primary_key_names = set(primary_key)
                profiled_columns = []
                for column in columns:
                    if (
                        column.name in primary_key_names
                        and column.data_type.upper() == "NUMBER"
                        and (column.precision is None or column.scale is None)
                    ):
                        quoted_column = quote_oracle_identifier(column.name)
                        quoted_owner = quote_oracle_identifier(owner)
                        quoted_table = quote_oracle_identifier(table)
                        cursor.execute(
                            f"""
                            SELECT MIN({quoted_column}), MAX({quoted_column}),
                                   MAX(
                                       CASE
                                           WHEN {quoted_column} !=
                                                TRUNC({quoted_column})
                                           THEN 1 ELSE 0
                                       END
                                   )
                            FROM {quoted_owner}.{quoted_table}
                            """
                        )
                        minimum, maximum, has_fractional_value = cursor.fetchone()
                        sdk_type_override = exact_sdk_type_for_unconstrained_number_key(
                            minimum,
                            maximum,
                            bool(has_fractional_value),
                        )
                        column = replace(
                            column,
                            sdk_type_override=sdk_type_override,
                        )
                    profiled_columns.append(column)
                columns = tuple(profiled_columns)
        except oracledb.Error as exc:
            raise MissingPrivilegeError(
                f"Unable to discover metadata for {owner}.{table}"
            ) from exc
        if not columns:
            raise MissingPrivilegeError(f"No visible columns found for {owner}.{table}")
        if not primary_key:
            raise MissingPrivilegeError(
                f"Included table {owner}.{table} has no primary key"
            )
        result = TableSchema(
            owner=owner,
            name=table,
            object_id=int(identity[0]),
            data_object_id=int(identity[1]) if identity[1] is not None else None,
            columns=columns,
            primary_key=primary_key,
        )
        result = result.select(selection.columns)
        result.sdk_definition()
        return result

    def fetch_historical_page(
        self,
        table_schema: TableSchema,
        last_key: list,
        fetch_size: int,
        snapshot_scn: int,
    ) -> list[tuple]:
        column_names = [column.name for column in table_schema.replicated_columns]
        projection = ", ".join(quote_oracle_identifier(name) for name in column_names)
        owner = quote_oracle_identifier(table_schema.owner)
        table = quote_oracle_identifier(table_schema.name)
        key_columns = list(table_schema.primary_key)
        binds = {"fetch_size": fetch_size, "snapshot_scn": snapshot_scn}
        predicate = ""
        if last_key:
            parts = []
            for index, key_name in enumerate(key_columns):
                equal_prefix = [
                    f"{quote_oracle_identifier(key_columns[prefix])} = :key_{prefix}"
                    for prefix in range(index)
                ]
                greater = f"{quote_oracle_identifier(key_name)} > :key_{index}"
                parts.append("(" + " AND ".join(equal_prefix + [greater]) + ")")
                binds[f"key_{index}"] = last_key[index]
            predicate = "WHERE " + " OR ".join(parts)
        order_by = ", ".join(quote_oracle_identifier(name) for name in key_columns)
        sql = (
            f"SELECT {projection} FROM {owner}.{table} AS OF SCN :snapshot_scn "
            f"{predicate} ORDER BY {order_by} "
            f"FETCH FIRST :fetch_size ROWS ONLY"
        )
        try:
            with self.cursor() as cursor:
                cursor.arraysize = fetch_size
                cursor.execute(sql, binds, fetch_decimals=True)
                return cursor.fetchall()
        except oracledb.Error as exc:
            code = getattr(exc.args[0], "code", None) if exc.args else None
            if code in {1555, 8180, 8181}:
                raise SnapshotTooOldError(
                    f"Original snapshot SCN {snapshot_scn} is unavailable; controlled resnapshot required"
                ) from None
            if code == 1466:
                raise ResnapshotRequiredError(
                    f"DDL invalidated snapshot SCN {snapshot_scn} for {table_schema.source_key}"
                ) from None
            raise

    def fetch_committed_row(
        self, table_schema: TableSchema, keys: dict, commit_scn: int
    ) -> tuple | None:
        """Fetch the complete selected after-image at the exact commit boundary."""
        projection = ", ".join(
            quote_oracle_identifier(column.name)
            for column in table_schema.replicated_columns
        )
        predicates = " AND ".join(
            f"{quote_oracle_identifier(name)} = :key_{index}"
            for index, name in enumerate(table_schema.primary_key)
        )
        binds = {
            f"key_{index}": keys[name.lower()]
            for index, name in enumerate(table_schema.primary_key)
        }
        binds["commit_scn"] = commit_scn
        sql = f"SELECT {projection} FROM {quote_oracle_identifier(table_schema.owner)}.{quote_oracle_identifier(table_schema.name)} AS OF SCN :commit_scn WHERE {predicates}"
        try:
            with self.cursor() as cursor:
                cursor.execute(sql, binds, fetch_decimals=True)
                return cursor.fetchone()
        except oracledb.Error:
            raise ResnapshotRequiredError(
                f"Commit after-image unavailable for {table_schema.source_key} at SCN {commit_scn}"
            ) from None
