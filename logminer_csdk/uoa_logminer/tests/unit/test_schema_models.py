from schema_models import ColumnSchema, TableSchema


def table_schema():
    return TableSchema(
        owner="ANIMAL_CROSSING",
        name="HOUSEWARES",
        object_id=123,
        data_object_id=124,
        columns=(
            ColumnSchema(
                name="ID",
                column_id=1,
                data_type="NUMBER",
                length=22,
                precision=10,
                scale=0,
                char_used=None,
                nullable=False,
                default=None,
            ),
            ColumnSchema(
                name="NAME",
                column_id=2,
                data_type="VARCHAR2",
                length=100,
                precision=None,
                scale=None,
                char_used="B",
                nullable=True,
                default=None,
            ),
        ),
        primary_key=("ID",),
    )


def test_fingerprint_is_stable_across_round_trip():
    original = table_schema()
    restored = TableSchema.from_dict(original.to_dict())
    assert restored.fingerprint == original.fingerprint


def test_sdk_schema_has_explicit_primary_key_and_types():
    definition = table_schema().sdk_definition()
    assert definition["table"] == "animal_crossing_housewares"
    assert definition["primary_key"] == ["id"]
    assert definition["columns"] == {"id": "LONG", "name": "STRING"}


def test_sdk_schema_declares_decimal_metadata_and_unconstrained_number():
    schema = TableSchema(
        owner="ANIMAL_CROSSING",
        name="MEASUREMENTS",
        object_id=125,
        data_object_id=126,
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
            ColumnSchema("AMOUNT", 2, "NUMBER", 22, 20, 4, None, True, None),
        ),
        primary_key=("ID",),
    )

    assert schema.sdk_definition()["columns"] == {
        "id": "LONG",
        "amount": {"type": "DECIMAL", "precision": 20, "scale": 4},
    }
