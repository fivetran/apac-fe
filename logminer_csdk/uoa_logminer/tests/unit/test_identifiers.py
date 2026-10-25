import pytest

from errors import ConfigurationError
from identifiers import (
    destination_table_name,
    normalize_oracle_identifier,
    quote_oracle_identifier,
)


def test_identifier_normalization_and_quoting():
    assert normalize_oracle_identifier("housewares", "table") == "HOUSEWARES"
    assert quote_oracle_identifier("housewares") == '"HOUSEWARES"'


def test_identifier_rejects_sql_text():
    with pytest.raises(ConfigurationError):
        quote_oracle_identifier('HOUSEWARES" WHERE 1=1 --')


def test_destination_name_includes_owner():
    assert (
        destination_table_name("ANIMAL_CROSSING", "HOUSEWARES")
        == "animal_crossing_housewares"
    )
