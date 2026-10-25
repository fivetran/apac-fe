import pytest

from errors import MissingRedoLogError
from logminer.redo_log_selector import select_redo_logs


class Cursor:
    def __init__(self, archived, online=(), archive_bounds=(None, None)):
        self.archived = list(archived)
        self.online = list(online)
        self.archive_bounds = archive_bounds
        self.rows = []

    def execute(self, sql, **binds):
        if "MIN(FIRST_CHANGE#)" in sql:
            self.rows = [self.archive_bounds]
        else:
            self.rows = self.archived if "V$ARCHIVED_LOG" in sql else self.online

    def __iter__(self):
        return iter(self.rows)

    def fetchone(self):
        return self.rows[0]


def test_selects_contiguous_archive_coverage():
    cursor = Cursor(
        [
            ("/archive/1", 100, 200, 1, 1, 1),
            ("/archive/2", 200, 300, 1, 2, 1),
        ]
    )
    logs, covered_end = select_redo_logs(cursor, 150, 250, True)
    assert [log.sequence for log in logs] == [1, 2]
    assert covered_end == 250


def test_gap_at_start_fails_without_advancing():
    cursor = Cursor(
        [("/archive/2", 200, 300, 1, 2, 1)],
        archive_bounds=(200, 300),
    )
    with pytest.raises(MissingRedoLogError, match="start SCN"):
        select_redo_logs(cursor, 150, 250, True)


def test_multiple_threads_are_rejected_until_rac_is_proven():
    cursor = Cursor(
        [
            ("/archive/1", 100, 200, 1, 1, 1),
            ("/archive/2", 100, 200, 2, 1, 1),
        ]
    )
    with pytest.raises(MissingRedoLogError, match="RAC"):
        select_redo_logs(cursor, 100, 150, True)


def test_archive_only_waits_when_redo_is_not_archived_yet():
    cursor = Cursor([], archive_bounds=(100, 200))
    logs, covered_end = select_redo_logs(cursor, 200, 250, True)
    assert logs == []
    assert covered_end == 199


def test_online_copy_replaces_stale_archive_for_same_sequence():
    cursor = Cursor(
        [("/archive/deleted", 100, 200, 1, 1, 1)],
        [("/online/redo", 100, 200, 1, 1, 0)],
    )
    logs, covered_end = select_redo_logs(cursor, 150, 250, False)
    assert [log.name for log in logs] == ["/online/redo"]
    assert covered_end == 199


def test_duplicate_members_register_only_one_copy_per_sequence():
    cursor = Cursor(
        [],
        [
            ("/online/a", 100, 200, 1, 1, 0),
            ("/online/b", 100, 200, 1, 1, 0),
            ("/online/c", 200, 300, 1, 2, 0),
        ],
    )
    logs, covered_end = select_redo_logs(cursor, 150, 250, False)
    assert [log.sequence for log in logs] == [1, 2]
    assert covered_end == 250


def test_archive_only_does_not_select_an_online_copy():
    cursor = Cursor(
        [("/archive/a", 100, 200, 1, 1, 1)],
        [("/online/a", 100, 200, 1, 1, 0)],
    )
    logs, _ = select_redo_logs(cursor, 150, 175, True)
    assert logs[0].archived


def test_conflicting_ranges_for_one_sequence_fail_closed():
    cursor = Cursor(
        [("/archive/a", 100, 200, 1, 1, 1)],
        [("/online/a", 100, 300, 1, 1, 0)],
    )
    with pytest.raises(MissingRedoLogError, match="Conflicting redo coverage"):
        select_redo_logs(cursor, 150, 250, False)
