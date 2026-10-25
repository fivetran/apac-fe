"""Full-table schema diff and supported-change classification."""

from dataclasses import dataclass
from enum import Enum

from schema_evolution.type_compatibility import (
    TypeChangeDecision,
    assess_type_change,
)
from schema_models import ColumnSchema, TableSchema


class SchemaChangeKind(str, Enum):
    NONE = "NONE"
    ADD_COLUMN = "ADD_COLUMN"
    COMPATIBLE_TYPE_CHANGE = "COMPATIBLE_TYPE_CHANGE"
    MULTI_COLUMN_CHANGE = "MULTI_COLUMN_CHANGE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class SchemaDiff:
    kind: SchemaChangeKind
    added_columns: tuple[ColumnSchema, ...] = ()
    changed_columns: tuple[tuple[ColumnSchema, ColumnSchema], ...] = ()
    type_decision: TypeChangeDecision | None = None
    type_decisions: tuple[TypeChangeDecision, ...] = ()
    reason: str | None = None


def classify_schema_change(old: TableSchema, new: TableSchema) -> SchemaDiff:
    if old.fingerprint == new.fingerprint:
        return SchemaDiff(kind=SchemaChangeKind.NONE)
    if (
        old.owner != new.owner
        or old.name != new.name
        or old.object_id != new.object_id
        or old.primary_key != new.primary_key
    ):
        return SchemaDiff(
            kind=SchemaChangeKind.UNSUPPORTED,
            reason="table identity or primary key changed",
        )
    old_by_name = {column.name: column for column in old.columns}
    new_by_name = {column.name: column for column in new.columns}
    removed = set(old_by_name) - set(new_by_name)
    added = tuple(new_by_name[name] for name in new_by_name if name not in old_by_name)
    changed = tuple(
        (old_by_name[name], new_by_name[name])
        for name in old_by_name
        if name in new_by_name and old_by_name[name] != new_by_name[name]
    )
    if removed:
        return SchemaDiff(
            kind=SchemaChangeKind.UNSUPPORTED,
            reason="one or more columns were removed or renamed",
        )
    unsupported_metadata_changes = tuple(
        (old_column, new_column)
        for old_column, new_column in changed
        if (
            old_column.name != new_column.name
            or old_column.column_id != new_column.column_id
            or old_column.nullable != new_column.nullable
            or old_column.default != new_column.default
            or old_column.char_used != new_column.char_used
        )
    )
    if unsupported_metadata_changes:
        return SchemaDiff(
            kind=SchemaChangeKind.UNSUPPORTED,
            added_columns=added,
            changed_columns=changed,
            reason="column identity, nullability, default, or character semantics changed",
        )
    if added:
        unsupported_additions = tuple(
            column
            for column in added
            if not column.nullable or column.default is not None
        )
        if unsupported_additions:
            return SchemaDiff(
                kind=SchemaChangeKind.UNSUPPORTED,
                added_columns=added,
                changed_columns=changed,
                reason="only nullable added columns without defaults are supported",
            )

    decisions = tuple(assess_type_change(*change) for change in changed)
    safe_decisions = {
        TypeChangeDecision.SAFE_SAME_DESTINATION_TYPE,
        TypeChangeDecision.SAFE_DESTINATION_WIDENING,
    }
    if any(decision not in safe_decisions for decision in decisions):
        first_unsafe = next(
            decision for decision in decisions if decision not in safe_decisions
        )
        return SchemaDiff(
            kind=SchemaChangeKind.UNSUPPORTED,
            added_columns=added,
            changed_columns=changed,
            type_decision=first_unsafe if len(changed) == 1 else None,
            type_decisions=decisions,
            reason="one or more column changes are not proven compatible",
        )

    if added and not changed:
        return SchemaDiff(kind=SchemaChangeKind.ADD_COLUMN, added_columns=added)
    if changed and not added:
        return SchemaDiff(
            kind=SchemaChangeKind.COMPATIBLE_TYPE_CHANGE,
            changed_columns=changed,
            type_decision=decisions[0] if len(decisions) == 1 else None,
            type_decisions=decisions,
        )
    if added and changed:
        return SchemaDiff(
            kind=SchemaChangeKind.MULTI_COLUMN_CHANGE,
            added_columns=added,
            changed_columns=changed,
            type_decisions=decisions,
        )
    return SchemaDiff(
        kind=SchemaChangeKind.UNSUPPORTED,
        added_columns=added,
        changed_columns=changed,
        reason="schema changed without a supported column transition",
    )
