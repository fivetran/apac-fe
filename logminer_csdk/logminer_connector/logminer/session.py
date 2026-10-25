"""Lifecycle for one bounded DBMS_LOGMNR session."""

from typing import Self

import oracledb

from errors import LogMinerSessionError
from logminer.models import RedoRecord
from logminer.redo_log_selector import RedoLog


class LogMinerSession:
    def __init__(self, client):
        self.client = client
        self.started = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.end()

    def start(self, logs: list[RedoLog], start_scn: int, end_scn: int) -> None:
        if not logs:
            raise LogMinerSessionError("Cannot start LogMiner without redo logs")
        try:
            with self.client.cursor() as cursor:
                # SQL_REDO temporal literals depend on this mining session's
                # NLS settings. Preserve all nine Oracle fractional digits;
                # the parser rejects precision the SDK cannot represent.
                for statement in (
                    "ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS'",
                    "ALTER SESSION SET NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD HH24:MI:SS.FF9'",
                    "ALTER SESSION SET NLS_TIMESTAMP_TZ_FORMAT = 'YYYY-MM-DD HH24:MI:SS.FF9 TZH:TZM'",
                    "ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'",
                ):
                    cursor.execute(statement)
                for index, redo_log in enumerate(logs):
                    option = "DBMS_LOGMNR.NEW" if index == 0 else "DBMS_LOGMNR.ADDFILE"
                    cursor.execute(
                        f"""
                        BEGIN
                            DBMS_LOGMNR.ADD_LOGFILE(
                                LOGFILENAME => :filename,
                                OPTIONS => {option}
                            );
                        END;
                        """,
                        filename=redo_log.name,
                    )
                cursor.execute(
                    """
                    BEGIN
                        DBMS_LOGMNR.START_LOGMNR(
                            STARTSCN => :start_scn,
                            ENDSCN => :end_scn,
                            OPTIONS => DBMS_LOGMNR.DICT_FROM_ONLINE_CATALOG
                        );
                    END;
                    """,
                    start_scn=start_scn,
                    end_scn=end_scn,
                )
            self.started = True
        except oracledb.Error as exc:
            raise LogMinerSessionError(
                f"Failed to start bounded LogMiner window {start_scn}..{end_scn}"
            ) from exc

    def records(
        self,
        owner: str | list[tuple[str, str]],
        table: str | None = None,
        fetch_size: int = 1_000,
    ):
        if not self.started:
            raise LogMinerSessionError("LogMiner session is not started")
        try:
            with self.client.cursor() as cursor:
                cursor.arraysize = fetch_size
                pairs = owner if isinstance(owner, list) else [(owner, table)]
                binds: dict[str, str | None] = {}
                clauses = []
                for index, (table_owner, table_name) in enumerate(pairs):
                    clauses.append(
                        f"(SEG_OWNER = :owner_{index} AND SEG_NAME = :table_{index})"
                    )
                    binds[f"owner_{index}"] = table_owner
                    binds[f"table_{index}"] = table_name
                scope = " OR ".join(clauses)
                cursor.execute(
                    f"""
                    SELECT SCN, COMMIT_SCN, OPERATION, OPERATION_CODE,
                           XIDUSN || '.' || XIDSLT || '.' || XIDSQN AS XID,
                           SEG_OWNER, SEG_NAME,
                           CASE WHEN OPERATION_CODE IN (9,10,11,29,68,70,71) THEN NULL ELSE SQL_REDO END,
                           CSF, RS_ID, SSN,
                           THREAD#, SEQUENCE#, ROW_ID, ROLLBACK, STATUS
                    FROM V$LOGMNR_CONTENTS
                    WHERE (
                        ({scope})
                        AND OPERATION_CODE IN (
                            1, 2, 3, 5,
                            9, 10, 11, 29,
                            68, 70, 71,
                            255
                        )
                    )
                    OR OPERATION_CODE IN (7, 34, 36)
                    ORDER BY SCN, RS_ID, SSN
                    """,
                    **binds,
                )
                while True:
                    rows = cursor.fetchmany(fetch_size)
                    if not rows:
                        return
                    for row in rows:
                        yield RedoRecord(
                            scn=int(row[0]),
                            commit_scn=int(row[1]) if row[1] is not None else None,
                            operation=str(row[2]),
                            operation_code=int(row[3]),
                            xid=str(row[4]) if row[4] is not None else None,
                            owner=str(row[5]) if row[5] is not None else None,
                            table=str(row[6]) if row[6] is not None else None,
                            sql_redo=str(row[7]) if row[7] is not None else None,
                            csf=int(row[8] or 0),
                            rs_id=str(row[9]) if row[9] is not None else None,
                            ssn=int(row[10]) if row[10] is not None else None,
                            thread=int(row[11]) if row[11] is not None else None,
                            sequence=int(row[12]) if row[12] is not None else None,
                            row_id=str(row[13]) if row[13] is not None else None,
                            rollback=bool(row[14]),
                            status=int(row[15] or 0),
                        )
        except oracledb.Error as exc:
            raise LogMinerSessionError("Failed to read V$LOGMNR_CONTENTS") from exc

    def end(self) -> None:
        if not self.started:
            return
        try:
            with self.client.cursor() as cursor:
                cursor.execute("BEGIN DBMS_LOGMNR.END_LOGMNR; END;")
        except oracledb.Error as exc:
            raise LogMinerSessionError("Failed to end LogMiner session") from exc
        finally:
            self.started = False
