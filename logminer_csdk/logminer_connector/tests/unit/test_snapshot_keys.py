import datetime
import decimal

import pytest

from errors import SchemaMismatchError
from snapshot import _decode_key, _encode_key


@pytest.mark.parametrize(
    "value",
    [
        decimal.Decimal("123.45"),
        datetime.datetime(2026, 7, 25, 12, 0, tzinfo=datetime.UTC),
        datetime.date(2026, 7, 25),
        "value",
        42,
        None,
    ],
)
def test_snapshot_key_round_trip(value):
    assert _decode_key(_encode_key(value)) == value


def test_unsupported_snapshot_key_type_fails_closed():
    with pytest.raises(SchemaMismatchError):
        _encode_key(b"not-supported-as-a-key")
