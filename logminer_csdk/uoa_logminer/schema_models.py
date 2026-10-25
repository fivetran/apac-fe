"""Immutable Oracle table schema metadata."""

import hashlib
import json
from dataclasses import dataclass, replace

from errors import SchemaMismatchError, UnsupportedThinModeFeatureError
from identifiers import destination_table_name, source_table_key
from selection import EXCLUDED_TYPES
from type_mapping import sdk_schema_type_for, sdk_type_for


@dataclass(frozen=True)
class ColumnSchema:
    name: str
    column_id: int
    data_type: str
    length: int | None
    precision: int | None
    scale: int | None
    char_used: str | None
    nullable: bool
    default: str | None
    sdk_type_override: str | None = None

    def to_dict(self) -> dict:
        value = {
            "name": self.name,
            "column_id": self.column_id,
            "data_type": self.data_type,
            "length": self.length,
            "precision": self.precision,
            "scale": self.scale,
            "char_used": self.char_used,
            "nullable": self.nullable,
            "default": self.default,
            "sdk_type_override": self.sdk_type_override,
        }
        try:
            value["sdk_type"] = sdk_type_for(value)
        except UnsupportedThinModeFeatureError:
            value["sdk_type"] = None
        return value

    @classmethod
    def from_dict(cls, value: dict) -> "ColumnSchema":
        return cls(
            name=str(value["name"]),
            column_id=int(value["column_id"]),
            data_type=str(value["data_type"]),
            length=value.get("length"),
            precision=value.get("precision"),
            scale=value.get("scale"),
            char_used=value.get("char_used"),
            nullable=bool(value["nullable"]),
            default=value.get("default"),
            sdk_type_override=value.get("sdk_type_override"),
        )


@dataclass(frozen=True)
class TableSchema:
    owner: str
    name: str
    object_id: int
    data_object_id: int | None
    columns: tuple[ColumnSchema, ...]
    primary_key: tuple[str, ...]
    selected_columns: tuple[str, ...] | None = None

    @property
    def replicated_columns(self) -> tuple[ColumnSchema, ...]:
        names = self.selected_columns
        return tuple(
            column
            for column in self.columns
            if column.data_type.upper() not in EXCLUDED_TYPES
            and (names is None or column.name in names)
        )

    def select(self, names: tuple[str, ...] | None) -> "TableSchema":
        available = {column.name: column for column in self.columns}
        if names is not None and set(names) - set(available):
            raise SchemaMismatchError(
                f"Selected column is unavailable for {self.source_key}"
            )
        requested = set(names or available) | set(self.primary_key)
        if any(
            available[key].data_type.upper() in EXCLUDED_TYPES
            for key in self.primary_key
        ):
            raise SchemaMismatchError("LOB/complex primary keys are not supported")
        selected = tuple(
            column.name
            for column in self.columns
            if column.name in requested
            and column.data_type.upper() not in EXCLUDED_TYPES
        )
        for column in self.columns:
            if column.name in selected:
                sdk_schema_type_for(column.to_dict())
        return replace(self, selected_columns=selected)

    def retain_contract(self, original: "TableSchema") -> "TableSchema":
        """Freeze destination columns/types across a DDL-triggered resnapshot."""
        if (
            self.object_id != original.object_id
            or self.primary_key != original.primary_key
        ):
            raise SchemaMismatchError(
                f"Table identity or primary-key definition changed for {self.source_key}"
            )
        current = {column.name: column for column in self.columns}
        frozen = {column.name: column for column in original.replicated_columns}
        for name, old in frozen.items():
            new = current.get(name)
            if new is None or new.data_type != old.data_type:
                raise SchemaMismatchError(
                    f"Selected column removed or changed type for {self.source_key}"
                )
            if (old.length, old.precision, old.scale, old.char_used) != (
                new.length,
                new.precision,
                new.scale,
                new.char_used,
            ):
                from schema_evolution.type_compatibility import (
                    TypeChangeDecision,
                    assess_type_change,
                )

                if (
                    assess_type_change(old, new)
                    != TypeChangeDecision.SAFE_SAME_DESTINATION_TYPE
                    or sdk_schema_type_for(old.to_dict())
                    != sdk_schema_type_for(new.to_dict())
                ):
                    raise SchemaMismatchError(
                        f"Selected column change requires a new destination contract for {self.source_key}"
                    )
        columns = tuple(frozen.get(column.name, column) for column in self.columns)
        return replace(self, columns=columns, selected_columns=tuple(frozen))

    @property
    def source_key(self) -> str:
        return source_table_key(self.owner, self.name)

    @property
    def destination_name(self) -> str:
        return destination_table_name(self.owner, self.name)

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            self.to_dict(include_fingerprint=False),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def has_same_row_schema(self, other: "TableSchema") -> bool:
        """Compare metadata that affects row decoding, ignoring storage identity."""
        return (
            self.owner == other.owner
            and self.name == other.name
            and self.object_id == other.object_id
            and self.columns == other.columns
            and self.primary_key == other.primary_key
        )

    def to_dict(self, include_fingerprint: bool = True) -> dict:
        value = {
            "owner": self.owner,
            "name": self.name,
            "object_id": self.object_id,
            "data_object_id": self.data_object_id,
            "columns": [column.to_dict() for column in self.columns],
            "primary_key": list(self.primary_key),
        }
        if self.selected_columns is not None:
            value["selected_columns"] = list(self.selected_columns)
        if include_fingerprint:
            value["fingerprint"] = self.fingerprint
        return value

    @classmethod
    def from_dict(cls, value: dict) -> "TableSchema":
        return cls(
            owner=str(value["owner"]),
            name=str(value["name"]),
            object_id=int(value["object_id"]),
            data_object_id=(
                int(value["data_object_id"])
                if value.get("data_object_id") is not None
                else None
            ),
            columns=tuple(
                ColumnSchema.from_dict(column) for column in value["columns"]
            ),
            primary_key=tuple(str(item) for item in value["primary_key"]),
            selected_columns=tuple(value["selected_columns"])
            if value.get("selected_columns") is not None
            else None,
        )

    def sdk_definition(self) -> dict:
        by_name = {column.name: column.to_dict() for column in self.replicated_columns}
        columns = {}
        for name, metadata in by_name.items():
            sdk_schema_type = sdk_schema_type_for(metadata)
            if sdk_schema_type is not None:
                columns[name.lower()] = sdk_schema_type
        return {
            "table": self.destination_name,
            "primary_key": [name.lower() for name in self.primary_key],
            "columns": columns,
        }
