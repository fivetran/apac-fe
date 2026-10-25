"""Select redo logs covering a bounded SCN interval."""

from dataclasses import dataclass

from errors import MissingRedoLogError


@dataclass(frozen=True)
class RedoLog:
    name: str
    first_scn: int
    next_scn: int
    thread: int
    sequence: int
    archived: bool


def select_redo_logs(
    cursor, start_scn: int, end_scn: int, archive_only: bool
) -> tuple[list[RedoLog], int]:
    cursor.execute(
        """
        SELECT NAME, FIRST_CHANGE#, NEXT_CHANGE#, THREAD#, SEQUENCE#, 1
        FROM V$ARCHIVED_LOG
        WHERE NAME IS NOT NULL
          AND STATUS = 'A'
          AND RESETLOGS_CHANGE# = (SELECT RESETLOGS_CHANGE# FROM V$DATABASE)
          AND FIRST_CHANGE# <= :end_scn
          AND NEXT_CHANGE# > :start_scn
        """,
        start_scn=start_scn,
        end_scn=end_scn,
    )
    rows = list(cursor)
    if not archive_only:
        cursor.execute(
            """
            SELECT files.MEMBER, logs.FIRST_CHANGE#,
                   CASE
                     WHEN logs.NEXT_CHANGE# = 0 THEN :end_scn + 1
                     ELSE logs.NEXT_CHANGE#
                   END,
                   logs.THREAD#, logs.SEQUENCE#, 0
            FROM V$LOG logs
            JOIN V$LOGFILE files ON files.GROUP# = logs.GROUP#
            WHERE logs.FIRST_CHANGE# <= :end_scn
              AND (logs.NEXT_CHANGE# = 0 OR logs.NEXT_CHANGE# > :start_scn)
            """,
            start_scn=start_scn,
            end_scn=end_scn,
        )
        rows.extend(cursor)
    unique: dict[tuple[int, int], RedoLog] = {}
    for row in rows:
        name = str(row[0])
        candidate = RedoLog(
            name=name,
            first_scn=int(row[1]),
            next_scn=int(row[2]),
            thread=int(row[3]),
            sequence=int(row[4]),
            archived=bool(row[5]),
        )
        identity = (candidate.thread, candidate.sequence)
        existing = unique.get(identity)
        if existing is not None:
            if (existing.first_scn, existing.next_scn) != (
                candidate.first_scn,
                candidate.next_scn,
            ):
                raise MissingRedoLogError(
                    f"Conflicting redo coverage for thread {candidate.thread} "
                    f"sequence {candidate.sequence}"
                )
            # An archive filename may outlive its physical file in Oracle
            # metadata. Prefer the matching online copy when explicitly
            # enabled, and register only one copy of a redo sequence.
            if existing.archived and not candidate.archived:
                unique[identity] = candidate
        else:
            unique[identity] = candidate
    logs = sorted(
        unique.values(),
        key=lambda item: (item.thread, item.first_scn, item.sequence, item.name),
    )
    threads = {item.thread for item in logs}
    if len(threads) > 1:
        raise MissingRedoLogError(
            "Multiple Oracle redo threads detected; RAC ordering is not supported"
        )
    if not logs:
        if archive_only:
            cursor.execute(
                """
                SELECT MIN(FIRST_CHANGE#), MAX(NEXT_CHANGE#)
                FROM V$ARCHIVED_LOG
                WHERE NAME IS NOT NULL AND STATUS = 'A'
                  AND RESETLOGS_CHANGE# = (SELECT RESETLOGS_CHANGE# FROM V$DATABASE)
                """
            )
            oldest_scn, newest_next_scn = cursor.fetchone()
            if newest_next_scn is not None and start_scn >= int(newest_next_scn):
                return [], start_scn - 1
            if oldest_scn is not None and start_scn < int(oldest_scn):
                raise MissingRedoLogError(
                    f"Required redo start SCN {start_scn} is unavailable; "
                    f"oldest archived SCN is {int(oldest_scn)}"
                )
        raise MissingRedoLogError(f"No redo log covers required start SCN {start_scn}")
    position = start_scn
    selected = []
    for item in logs:
        if item.next_scn <= position:
            continue
        if item.first_scn > position:
            break
        selected.append(item)
        position = max(position, item.next_scn)
        if position > end_scn:
            break
    if not selected or selected[0].first_scn > start_scn:
        oldest = min(item.first_scn for item in logs)
        raise MissingRedoLogError(
            f"Required redo start SCN {start_scn} is unavailable; "
            f"oldest selected SCN is {oldest}"
        )
    covered_end = min(end_scn, position - 1)
    if covered_end < start_scn:
        raise MissingRedoLogError(
            f"Redo coverage gap begins at required SCN {start_scn}"
        )
    return selected, covered_end
