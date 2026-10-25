from logminer.continuation import ContinuationAssembler
from logminer.models import RedoRecord


def record(sql, csf, scn=100):
    return RedoRecord(
        scn=scn,
        commit_scn=None,
        operation="UPDATE",
        operation_code=3,
        xid="1",
        owner="A",
        table="T",
        sql_redo=sql,
        csf=csf,
        rs_id="1",
        ssn=1,
        thread=1,
        sequence=1,
        row_id=None,
    )


def test_single_fragment_is_returned_complete():
    assembler = ContinuationAssembler()
    result = assembler.add(record("UPDATE X;", 0))
    assert result is not None
    assert result.sql_redo == "UPDATE X;"
    assert assembler.incomplete_scn is None


def test_many_fragments_are_joined():
    assembler = ContinuationAssembler()
    assert assembler.add(record("UP", 1)) is None
    assert assembler.incomplete_scn == 100
    assert assembler.add(record("DA", 1, 101)) is None
    result = assembler.add(record("TE", 0, 102))
    assert result is not None
    assert result.sql_redo == "UPDATE"
