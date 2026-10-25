import pytest

from errors import RedoParseError
from logminer.parser import parse_sql_redo
from schema_models import ColumnSchema, TableSchema


def test_canonical_timestamp_redo_matches_sdk_serializer():
    from dataclasses import replace

    from fivetran_connector_sdk.operations import map_defined_data_type
    from fivetran_connector_sdk.protos import common_pb2

    temporal = replace(
        schema(),
        columns=(
            schema().columns[0],
            ColumnSchema("UPDATED_AT", 2, "TIMESTAMP", 11, None, 6, None, True, None),
        ),
    )
    values, _ = parse_sql_redo(
        'update "APP"."ORDERS" set "UPDATED_AT" = '
        "TO_TIMESTAMP('2026-10-01 00:00:00.123456000') where \"ID\" = 1;",
        "UPDATE",
        temporal,
    )
    mapped = {}
    map_defined_data_type(
        common_pb2.DataType.NAIVE_DATETIME, "updated_at", mapped, values["updated_at"]
    )
    assert values["updated_at"] == "2026-10-01T00:00:00.123456"
    assert mapped["updated_at"].naive_datetime.nanos == 123456000


@pytest.mark.parametrize(
    "literal",
    [
        "01-OCT-26 12.00.00 AM",
        "2026-10-01 00:00:00.123456789",
        "2026-99-01 00:00:00",
        "2026-10-01 00:00:00+01:00",
    ],
)
def test_temporal_redo_rejects_ambiguous_or_lossy_values(literal):
    from logminer.parser import normalize_temporal_literal

    with pytest.raises(RedoParseError):
        normalize_temporal_literal(literal, "TIMESTAMP")


def schema():
    return TableSchema(
        owner="APP",
        name="ORDERS",
        object_id=1,
        data_object_id=1,
        columns=(
            ColumnSchema("ID", 1, "NUMBER", 22, 10, 0, None, False, None),
            ColumnSchema("NAME", 2, "VARCHAR2", 100, None, None, "B", True, None),
            ColumnSchema("NOTE", 3, "VARCHAR2", 100, None, None, "B", True, None),
        ),
        primary_key=("ID",),
    )


def test_insert_parses_escaped_string_and_null():
    values, keys = parse_sql_redo(
        'insert into "APP"."ORDERS"'
        '("ID","NAME","NOTE") values (1,\'O\'\'Brien\',NULL);',
        "INSERT",
        schema(),
    )
    assert values == {
        "id": 1,
        "name": "O'Brien",
        "note": None,
    }
    assert keys == {"id": 1}


def test_update_preserves_absent_columns():
    values, keys = parse_sql_redo(
        'update "APP"."ORDERS" set "NOTE" = NULL where "ID" = 1;',
        "UPDATE",
        schema(),
    )
    assert values == {"note": None}
    assert "name" not in values
    assert keys == {"id": 1}


def test_update_extracts_key_from_supplemental_before_image():
    values, keys = parse_sql_redo(
        'update "APP"."ORDERS" set "NOTE" = \'new\' '
        'where "ID" = 1 and "NAME" = \'old\' and "NOTE" IS NULL;',
        "UPDATE",
        schema(),
    )
    assert values == {"note": "new"}
    assert keys == {"id": 1}


def test_update_ignores_rowid_pseudocolumn_but_requires_declared_key():
    values, keys = parse_sql_redo(
        'update "APP"."ORDERS" set "NOTE" = \'new\' '
        'where "ROWID" = \'AAAIQRAAEAAAAIlAAA\' and "ID" = 1;',
        "UPDATE",
        schema(),
    )
    assert values == {"note": "new"}
    assert keys == {"id": 1}


def test_rowid_does_not_replace_declared_primary_key():
    with pytest.raises(RedoParseError, match="complete primary key"):
        parse_sql_redo(
            'update "APP"."ORDERS" set "NOTE" = \'new\' '
            "where \"ROWID\" = 'AAAIQRAAEAAAAIlAAA';",
            "UPDATE",
            schema(),
        )


def test_delete_requires_complete_primary_key():
    _, keys = parse_sql_redo(
        'delete from "APP"."ORDERS" where "ID" = 1;',
        "DELETE",
        schema(),
    )
    assert keys == {"id": 1}


def test_delete_extracts_key_from_supplemental_before_image():
    _, keys = parse_sql_redo(
        'delete from "APP"."ORDERS" '
        'where "NAME" = \'old\' and "NOTE" IS NULL and "ID" = 1;',
        "DELETE",
        schema(),
    )
    assert keys == {"id": 1}


def test_unconstrained_number_key_override_preserves_large_integer():
    exact_key_schema = TableSchema(
        owner="APP",
        name="ORDERS",
        object_id=1,
        data_object_id=1,
        columns=(
            ColumnSchema(
                "ID",
                1,
                "NUMBER",
                22,
                None,
                None,
                None,
                False,
                None,
                "LONG",
            ),
            ColumnSchema("NAME", 2, "VARCHAR2", 100, None, None, "B", True, None),
            ColumnSchema("NOTE", 3, "VARCHAR2", 100, None, None, "B", True, None),
        ),
        primary_key=("ID",),
    )
    _, keys = parse_sql_redo(
        'update "APP"."ORDERS" set "NOTE" = \'exact\' where "ID" = 920726000001;',
        "UPDATE",
        exact_key_schema,
    )
    assert keys == {"id": 920_726_000_001}


def test_where_predicates_reject_unknown_columns():
    with pytest.raises(RedoParseError, match="Unknown column"):
        parse_sql_redo(
            'delete from "APP"."ORDERS" where "ID" = 1 and "MISSING" = \'x\';',
            "DELETE",
            schema(),
        )


def test_primary_key_predicate_cannot_be_null():
    with pytest.raises(RedoParseError, match="Primary-key predicate is NULL"):
        parse_sql_redo(
            'delete from "APP"."ORDERS" where "ID" IS NULL;',
            "DELETE",
            schema(),
        )


def test_insert_rejects_partial_after_image():
    with pytest.raises(RedoParseError, match="complete after-image"):
        parse_sql_redo(
            'insert into "APP"."ORDERS"("ID","NAME") values (1,\'x\');',
            "INSERT",
            schema(),
        )


def test_unsupported_expression_fails_closed():
    with pytest.raises(RedoParseError):
        parse_sql_redo(
            'update "APP"."ORDERS" set "NOTE" = SYS_GUID() where "ID" = 1;',
            "UPDATE",
            schema(),
        )
