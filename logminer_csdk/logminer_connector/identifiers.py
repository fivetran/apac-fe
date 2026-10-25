"""Oracle and destination identifier validation."""

import re

from errors import ConfigurationError

_ORACLE_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,127}$")


def normalize_oracle_identifier(value: str, field: str) -> str:
    candidate = str(value).strip()
    if not _ORACLE_IDENTIFIER.fullmatch(candidate):
        raise ConfigurationError(f"{field} is not a valid simple Oracle identifier")
    return candidate.upper()


def quote_oracle_identifier(value: str) -> str:
    normalized = normalize_oracle_identifier(value, "identifier")
    return f'"{normalized}"'


def source_table_key(owner: str, table: str) -> str:
    return (
        f"{normalize_oracle_identifier(owner, 'owner')}."
        f"{normalize_oracle_identifier(table, 'table')}"
    )


def destination_table_name(owner: str, table: str) -> str:
    raw = f"{owner}_{table}".lower()
    normalized = re.sub(r"[^a-z0-9_]", "_", raw)
    if not normalized or not (normalized[0].islower() or normalized[0] == "_"):
        normalized = f"_{normalized}"
    return normalized
