"""Oracle metadata to Connector SDK type mapping and value conversion."""

import datetime
import decimal
import re

from errors import OperationSizeLimitError, UnsupportedThinModeFeatureError

SUPPORTED_STRING_TYPES = {
    "VARCHAR2",
    "NVARCHAR2",
    "CHAR",
    "NCHAR",
    "CLOB",
    "NCLOB",
    "LONG",
    "ROWID",
    "UROWID",
}


def sdk_type_for(column: dict) -> str:
    sdk_type_override = column.get("sdk_type_override")
    if sdk_type_override is not None:
        return str(sdk_type_override)
    oracle_type = str(column["data_type"]).upper()
    precision = column.get("precision")
    scale = column.get("scale")
    if oracle_type == "NUMBER":
        if precision is None or scale is None:
            return "FLOAT"
        if scale == 0 and precision is not None:
            if precision <= 4:
                return "SHORT"
            if precision <= 9:
                return "INT"
            if precision <= 18:
                return "LONG"
        return "DECIMAL"
    if oracle_type in {"FLOAT", "BINARY_DOUBLE"}:
        return "DOUBLE"
    if oracle_type == "BINARY_FLOAT":
        return "FLOAT"
    if oracle_type in SUPPORTED_STRING_TYPES:
        return "STRING"
    if oracle_type in {"RAW", "LONG RAW", "BLOB"}:
        return "BINARY"
    if oracle_type == "DATE":
        return "NAIVE_DATETIME"
    if oracle_type.startswith("TIMESTAMP") and "TIME ZONE" in oracle_type:
        raise UnsupportedThinModeFeatureError(
            "Time-zone timestamp replication requires verified offset-preserving fetches"
        )
    if oracle_type.startswith("TIMESTAMP"):
        precision = column.get("scale")
        if precision is None:
            match = re.match(r"TIMESTAMP\((\d+)\)", oracle_type)
            precision = int(match.group(1)) if match else 6
        if int(precision) > 6:
            raise UnsupportedThinModeFeatureError(
                "Timestamp precision exceeds the offset-free SDK microsecond contract"
            )
        return "NAIVE_DATETIME"
    if oracle_type == "XMLTYPE":
        return "XML"
    if oracle_type == "JSON":
        return "JSON"
    if oracle_type.startswith("INTERVAL"):
        return "STRING"
    raise UnsupportedThinModeFeatureError(
        f"Unsupported included Oracle type: {oracle_type}"
    )


def exact_sdk_type_for_unconstrained_number_key(
    minimum: decimal.Decimal | int | None,
    maximum: decimal.Decimal | int | None,
    has_fractional_value: bool,
) -> str:
    """Choose an exact, stable SDK type for an unconstrained NUMBER key.

    Connector SDK FLOAT is single precision and cannot safely identify large
    Oracle NUMBER primary-key values. Empty and integral signed-64-bit key
    domains can use LONG. Other unconstrained NUMBER key domains fail closed
    until an exact schema representation is explicitly supported.
    """
    if has_fractional_value:
        raise UnsupportedThinModeFeatureError(
            "Unconstrained NUMBER primary key contains fractional values"
        )
    signed_long_minimum = -(2**63)
    signed_long_maximum = (2**63) - 1
    if minimum is not None and minimum < signed_long_minimum:
        raise UnsupportedThinModeFeatureError(
            "Unconstrained NUMBER primary key is below the SDK LONG range"
        )
    if maximum is not None and maximum > signed_long_maximum:
        raise UnsupportedThinModeFeatureError(
            "Unconstrained NUMBER primary key exceeds the SDK LONG range"
        )
    return "LONG"


def convert_number_for_sdk(value: decimal.Decimal, column: dict):
    """Convert an exact Oracle numeric value to the SDK schema's Python type."""
    sdk_type = sdk_type_for(column)
    if sdk_type in {"SHORT", "INT", "LONG"}:
        integral = value.to_integral_value()
        if value != integral:
            raise ValueError(
                f"Non-integral Oracle NUMBER cannot be emitted as SDK {sdk_type}"
            )
        return int(integral)
    if sdk_type in {"FLOAT", "DOUBLE"}:
        return float(value)
    if sdk_type == "DECIMAL":
        return str(value)
    raise ValueError(f"Oracle numeric value has non-numeric SDK type {sdk_type}")


def sdk_schema_type_for(column: dict) -> str | dict | None:
    """Return the SDK schema declaration for an Oracle column.

    This follows Fivetran's Oracle connector mapping: NUMBER without specified
    precision or scale is FLOAT, while constrained big-decimal values retain
    their precision and scale in an explicit DECIMAL declaration.
    """
    sdk_type = sdk_type_for(column)
    if sdk_type != "DECIMAL":
        return sdk_type

    precision = column.get("precision")
    scale = column.get("scale")
    if precision is None or scale is None:
        return "FLOAT"
    return {
        "type": "DECIMAL",
        "precision": int(precision),
        "scale": int(scale),
    }


def convert_snapshot_value(value, column: dict, max_lob_bytes: int):
    if value is None:
        return None
    oracle_type = str(column["data_type"]).upper()
    if hasattr(value, "read") and oracle_type in {"CLOB", "NCLOB", "BLOB"}:
        raise UnsupportedThinModeFeatureError(
            "LOB replication is disabled; exclude the column"
        )
    if oracle_type == "NUMBER":
        if isinstance(value, decimal.Decimal):
            return convert_number_for_sdk(value, column)
        if isinstance(value, int):
            return convert_number_for_sdk(decimal.Decimal(value), column)
        raise UnsupportedThinModeFeatureError(
            "Oracle NUMBER must be fetched exactly as Decimal, not binary floating point"
        )
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return str(value)
    if oracle_type.startswith("INTERVAL"):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        result = bytes(value)
        if len(result) > max_lob_bytes:
            raise OperationSizeLimitError(
                f"Binary value exceeds configured max_lob_bytes={max_lob_bytes}"
            )
        return result
    if isinstance(value, str):
        if len(value.encode("utf-8")) > max_lob_bytes and oracle_type in {
            "CLOB",
            "NCLOB",
            "XMLTYPE",
            "JSON",
        }:
            raise OperationSizeLimitError(
                f"Text value exceeds configured max_lob_bytes={max_lob_bytes}"
            )
        return value
    return value


def estimate_operation_bytes(data: dict) -> int:
    total = 64
    for key, value in data.items():
        total += len(str(key).encode("utf-8")) + 8
        if value is None:
            total += 4
        elif isinstance(value, bytes):
            total += len(value)
        else:
            total += len(str(value).encode("utf-8"))
    return total


def enforce_operation_limit(data: dict, maximum: int) -> None:
    estimated = estimate_operation_bytes(data)
    if estimated > maximum:
        raise OperationSizeLimitError(
            f"Operation estimate {estimated} exceeds max_operation_bytes={maximum}"
        )
