"""Explicit source table/column selections; keys are always replicated."""

import json
from dataclasses import dataclass

from errors import ConfigurationError
from identifiers import normalize_oracle_identifier

EXCLUDED_TYPES = {"CLOB", "NCLOB", "BLOB", "BFILE", "XMLTYPE", "LONG", "LONG RAW"}


@dataclass(frozen=True)
class TableSelection:
    owner: str
    name: str
    columns: tuple[str, ...] | None = None

    @property
    def source_key(self) -> str:
        return f"{self.owner}.{self.name}"


def parse_selections(configuration: dict) -> tuple[TableSelection, ...]:
    raw = configuration.get("tables")
    if raw is None:
        owner = normalize_oracle_identifier(
            configuration.get("include_schema", ""), "include_schema"
        )
        name = normalize_oracle_identifier(
            configuration.get("include_table", ""), "include_table"
        )
        return (TableSelection(owner, name),)
    if configuration.get("include_schema") or configuration.get("include_table"):
        raise ConfigurationError("Use tables or include_schema/include_table, not both")
    try:
        values = json.loads(raw)
    except (TypeError, ValueError):
        raise ConfigurationError(
            "tables must be a JSON object encoded as a string"
        ) from None
    if not isinstance(values, dict) or not 1 <= len(values) <= 100:
        raise ConfigurationError("tables must select between 1 and 100 tables")
    selections = []
    for identity, columns in values.items():
        parts = identity.split(".")
        if len(parts) != 2:
            raise ConfigurationError("Each tables key must be OWNER.TABLE")
        owner, name = (normalize_oracle_identifier(part, "tables") for part in parts)
        if columns == "*":
            selected = None
        elif isinstance(columns, list) and 1 <= len(columns) <= 1000:
            selected = tuple(
                normalize_oracle_identifier(column, "columns") for column in columns
            )
            if len(set(selected)) != len(selected):
                raise ConfigurationError("Duplicate selected column")
        else:
            raise ConfigurationError("Table columns must be '*' or a nonempty list")
        selections.append(TableSelection(owner, name, selected))
    if len({item.source_key for item in selections}) != len(selections):
        raise ConfigurationError("Duplicate selected table")
    return tuple(sorted(selections, key=lambda item: item.source_key))
