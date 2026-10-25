import decimal

import pytest

from errors import OperationSizeLimitError, UnsupportedThinModeFeatureError
from type_mapping import (
    convert_number_for_sdk,
    convert_snapshot_value,
    enforce_operation_limit,
    exact_sdk_type_for_unconstrained_number_key,
    sdk_schema_type_for,
    sdk_type_for,
)


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        ({"data_type": "NUMBER", "precision": 9, "scale": 0}, "INT"),
        ({"data_type": "NUMBER", "precision": 20, "scale": 0}, "DECIMAL"),
        ({"data_type": "NUMBER", "precision": None, "scale": None}, "FLOAT"),
        ({"data_type": "VARCHAR2"}, "STRING"),
        ({"data_type": "BLOB"}, "BINARY"),
        ({"data_type": "DATE"}, "NAIVE_DATETIME"),
    ],
)
def test_sdk_type_mapping(column, expected):
    assert sdk_type_for(column) == expected


def test_decimal_schema_type_includes_required_precision_and_scale():
    assert sdk_schema_type_for(
        {"data_type": "NUMBER", "precision": 20, "scale": 4}
    ) == {"type": "DECIMAL", "precision": 20, "scale": 4}


def test_unconstrained_number_is_declared_as_fivetran_float():
    assert (
        sdk_schema_type_for({"data_type": "NUMBER", "precision": None, "scale": None})
        == "FLOAT"
    )


def test_unconstrained_integral_number_primary_key_uses_exact_long():
    assert (
        exact_sdk_type_for_unconstrained_number_key(
            -1,
            920_726_000_001,
            False,
        )
        == "LONG"
    )


@pytest.mark.parametrize(
    ("minimum", "maximum", "fractional"),
    [
        (0, 1, True),
        (-(2**63) - 1, 0, False),
        (0, 2**63, False),
    ],
)
def test_unsafe_unconstrained_number_primary_key_fails_closed(
    minimum, maximum, fractional
):
    with pytest.raises(UnsupportedThinModeFeatureError):
        exact_sdk_type_for_unconstrained_number_key(
            minimum,
            maximum,
            fractional,
        )


def test_decimal_is_not_converted_through_float():
    value = decimal.Decimal("12345678901234567890.1234")
    assert convert_number_for_sdk(
        value,
        {"data_type": "NUMBER", "precision": 24, "scale": 4},
    ) == str(value)


def test_number_is_converted_to_declared_sdk_runtime_type():
    assert (
        convert_number_for_sdk(
            decimal.Decimal(920726000001),
            {
                "data_type": "NUMBER",
                "precision": None,
                "scale": None,
                "sdk_type_override": "LONG",
            },
        )
        == 920_726_000_001
    )
    assert isinstance(
        convert_number_for_sdk(
            decimal.Decimal("1.25"),
            {"data_type": "NUMBER", "precision": None, "scale": None},
        ),
        float,
    )


def test_operation_limit_fails_closed():
    with pytest.raises(OperationSizeLimitError):
        enforce_operation_limit({"id": "x", "payload": "y" * 100}, 50)


def test_snapshot_decimal_matches_installed_sdk_serializer():
    from fivetran_connector_sdk.operations import map_defined_data_type
    from fivetran_connector_sdk.protos import common_pb2

    value = decimal.Decimal("1234567890.12")
    converted = convert_snapshot_value(
        value, {"data_type": "NUMBER", "precision": 12, "scale": 2}, 1024
    )
    mapped = {}
    map_defined_data_type(common_pb2.DataType.DECIMAL, "price", mapped, converted)
    assert mapped["price"].decimal == "1234567890.12"


def test_snapshot_number_cannot_accept_lossy_driver_float():
    with pytest.raises(UnsupportedThinModeFeatureError, match="fetched exactly"):
        convert_snapshot_value(
            0.1, {"data_type": "NUMBER", "precision": 12, "scale": 2}, 1024
        )
