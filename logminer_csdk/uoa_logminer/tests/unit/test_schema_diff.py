from schema_evolution.schema_diff import (
    SchemaChangeKind,
    classify_schema_change,
)
from schema_evolution.type_compatibility import TypeChangeDecision
from schema_models import ColumnSchema, TableSchema


def column(
    name,
    column_id,
    data_type="VARCHAR2",
    length=100,
    precision=None,
    scale=None,
    nullable=True,
    default=None,
):
    return ColumnSchema(
        name,
        column_id,
        data_type,
        length,
        precision,
        scale,
        "B" if "CHAR" in data_type else None,
        nullable,
        default,
    )


def table(columns, primary_key=("ID",), object_id=1):
    return TableSchema(
        "ANIMAL_CROSSING",
        "HOUSEWARES",
        object_id,
        1,
        tuple(columns),
        primary_key,
    )


def test_nullable_add_column_without_default_is_supported():
    old = table([column("ID", 1, "NUMBER", 22, 10, 0, False)])
    new = table(
        [
            column("ID", 1, "NUMBER", 22, 10, 0, False),
            column("NEW_COL", 2),
        ]
    )
    diff = classify_schema_change(old, new)
    assert diff.kind == SchemaChangeKind.ADD_COLUMN


def test_add_column_with_default_is_rejected():
    old = table([column("ID", 1, "NUMBER", 22, 10, 0, False)])
    new = table(
        [
            column("ID", 1, "NUMBER", 22, 10, 0, False),
            column("NEW_COL", 2, default="'x'"),
        ]
    )
    assert classify_schema_change(old, new).kind == SchemaChangeKind.UNSUPPORTED


def test_multiple_nullable_columns_without_defaults_are_supported():
    old = table([column("ID", 1, "NUMBER", 22, 10, 0, False)])
    new = table(
        [
            column("ID", 1, "NUMBER", 22, 10, 0, False),
            column("NEW_A", 2),
            column("NEW_B", 3, data_type="NUMBER", length=22),
        ]
    )
    diff = classify_schema_change(old, new)
    assert diff.kind == SchemaChangeKind.ADD_COLUMN
    assert [item.name for item in diff.added_columns] == ["NEW_A", "NEW_B"]


def test_varchar_widening_is_safe_with_same_destination_type():
    old = table([column("ID", 1, length=100)])
    new = table([column("ID", 1, length=500)])
    diff = classify_schema_change(old, new)
    assert diff.kind == SchemaChangeKind.COMPATIBLE_TYPE_CHANGE
    assert diff.type_decision == TypeChangeDecision.SAFE_SAME_DESTINATION_TYPE


def test_multiple_compatible_type_changes_are_supported():
    old = table([column("A", 1, length=100), column("B", 2, length=200)])
    new = table([column("A", 1, length=500), column("B", 2, length=400)])
    diff = classify_schema_change(old, new)
    assert diff.kind == SchemaChangeKind.COMPATIBLE_TYPE_CHANGE
    assert diff.type_decision is None
    assert diff.type_decisions == (
        TypeChangeDecision.SAFE_SAME_DESTINATION_TYPE,
        TypeChangeDecision.SAFE_SAME_DESTINATION_TYPE,
    )


def test_mixed_additions_and_compatible_changes_are_supported_as_batch():
    old = table([column("A", 1, length=100)])
    new = table([column("A", 1, length=500), column("B", 2)])
    diff = classify_schema_change(old, new)
    assert diff.kind == SchemaChangeKind.MULTI_COLUMN_CHANGE


def test_batch_is_rejected_when_any_change_is_unsafe():
    old = table([column("A", 1, length=100), column("B", 2, length=500)])
    new = table(
        [
            column("A", 1, length=500),
            column("B", 2, length=100),
            column("C", 3),
        ]
    )
    diff = classify_schema_change(old, new)
    assert diff.kind == SchemaChangeKind.UNSUPPORTED
    assert diff.reason == "one or more column changes are not proven compatible"


def test_non_type_metadata_change_is_rejected():
    old = table([column("A", 1, nullable=True)])
    new = table([column("A", 1, nullable=False)])
    diff = classify_schema_change(old, new)
    assert diff.kind == SchemaChangeKind.UNSUPPORTED
    assert "nullability" in diff.reason


def test_varchar_narrowing_requires_resync_and_is_rejected():
    old = table([column("ID", 1, length=500)])
    new = table([column("ID", 1, length=100)])
    diff = classify_schema_change(old, new)
    assert diff.kind == SchemaChangeKind.UNSUPPORTED
    assert diff.type_decision == TypeChangeDecision.REQUIRES_RESYNC


def test_primary_key_change_is_rejected():
    old = table([column("ID", 1)], primary_key=("ID",))
    new = table([column("ID", 1)], primary_key=())
    assert classify_schema_change(old, new).kind == SchemaChangeKind.UNSUPPORTED
