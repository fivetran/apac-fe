from contextlib import contextmanager

from logminer.session import LogMinerSession


class Cursor:
    def __init__(self):
        self.arraysize = None
        self.sql = None
        self.statements = []

    def execute(self, sql, **binds):
        self.sql = sql
        self.statements.append(sql)

    def fetchmany(self, size):
        return []


class Client:
    def __init__(self):
        self.last_cursor = None

    @contextmanager
    def cursor(self):
        self.last_cursor = Cursor()
        yield self.last_cursor


def test_record_query_selects_safety_and_complex_value_operations():
    client = Client()
    session = LogMinerSession(client)
    session.started = True

    assert list(session.records("A", "T")) == []

    sql = client.last_cursor.sql
    for operation_code in (9, 10, 11, 29, 34, 68, 70, 71, 255):
        assert str(operation_code) in sql


def test_mining_session_normalizes_nls_before_starting_logminer():
    from logminer.redo_log_selector import RedoLog

    client = Client()
    session = LogMinerSession(client)
    session.start([RedoLog("test-redo", 1, 100, 1, 1, True)], 1, 99)
    statements = client.last_cursor.statements
    assert all(sql.startswith("ALTER SESSION") for sql in statements[:4])
    assert "HH24:MI:SS.FF9" in statements[1]
    assert "TZH:TZM" in statements[2]
    assert "NLS_NUMERIC_CHARACTERS = '.,'" in statements[3]
    assert "START_LOGMNR" in statements[-1]
