"""Pure compatibility decisions for supported Oracle widening changes."""

from enum import Enum

from schema_models import ColumnSchema
from type_mapping import sdk_type_for


class TypeChangeDecision(str, Enum):
    SAFE_SAME_DESTINATION_TYPE = "SAFE_SAME_DESTINATION_TYPE"
    SAFE_DESTINATION_WIDENING = "SAFE_DESTINATION_WIDENING"
    REQUIRES_RESYNC = "REQUIRES_RESYNC"
    UNSUPPORTED = "UNSUPPORTED"


_LENGTH_TYPES = {"VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR", "RAW"}
_SDK_WIDENING = {
    ("SHORT", "INT"),
    ("SHORT", "LONG"),
    ("SHORT", "DECIMAL"),
    ("INT", "LONG"),
    ("INT", "DECIMAL"),
    ("LONG", "DECIMAL"),
    ("FLOAT", "DOUBLE"),
}


def assess_type_change(old: ColumnSchema, new: ColumnSchema) -> TypeChangeDecision:
    old_type = old.data_type.upper()
    new_type = new.data_type.upper()
    old_sdk = sdk_type_for(old.to_dict())
    new_sdk = sdk_type_for(new.to_dict())
    if old_type != new_type:
        return TypeChangeDecision.UNSUPPORTED

    safe_oracle_change = False
    if old_type in _LENGTH_TYPES:
        safe_oracle_change = (
            old.length is not None
            and new.length is not None
            and new.length >= old.length
        )
    elif old_type == "NUMBER":
        old_precision = old.precision or 38
        new_precision = new.precision or 38
        old_scale = old.scale or 0
        new_scale = new.scale or 0
        old_integer_digits = old_precision - old_scale
        new_integer_digits = new_precision - new_scale
        safe_oracle_change = (
            new_precision >= old_precision
            and new_scale >= old_scale
            and new_integer_digits >= old_integer_digits
        )
    elif old_type.startswith("TIMESTAMP"):
        old_precision = old.scale if old.scale is not None else 6
        new_precision = new.scale if new.scale is not None else 6
        safe_oracle_change = new_precision >= old_precision
    else:
        if old.to_dict() == new.to_dict():
            return TypeChangeDecision.SAFE_SAME_DESTINATION_TYPE
        return TypeChangeDecision.UNSUPPORTED

    if not safe_oracle_change:
        return TypeChangeDecision.REQUIRES_RESYNC
    if old_sdk == new_sdk:
        return TypeChangeDecision.SAFE_SAME_DESTINATION_TYPE
    if (old_sdk, new_sdk) in _SDK_WIDENING:
        return TypeChangeDecision.SAFE_DESTINATION_WIDENING
    return TypeChangeDecision.UNSUPPORTED
