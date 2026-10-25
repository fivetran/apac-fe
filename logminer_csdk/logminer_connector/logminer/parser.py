"""Small fail-closed parser for the supported SQL_REDO DML subset.

This is a tokenizing parser, not a regular-expression extractor. Any expression
outside the explicitly supported literal grammar stops checkpoint advancement.
"""

import datetime
import decimal
import re
from dataclasses import dataclass

from errors import RedoParseError
from schema_models import TableSchema
from type_mapping import convert_number_for_sdk


def normalize_temporal_literal(value: str, oracle_type: str) -> str:
    """Accept the mining session's canonical format without precision loss."""
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(?:\s*([+-]\d{2}:\d{2}))?",
        value.strip(),
    )
    if match is None:
        raise RedoParseError("Unsupported temporal SQL_REDO literal format")
    date, time, fraction, zone = match.groups()
    fraction = fraction or ""
    if any(digit != "0" for digit in fraction[6:]):
        raise RedoParseError("Temporal SQL_REDO precision exceeds SDK microseconds")
    aware = "WITH TIME ZONE" in oracle_type
    if bool(zone) != aware:
        raise RedoParseError("Temporal SQL_REDO timezone does not match column")
    result = f"{date}T{time}"
    if fraction:
        result += "." + fraction[:6]
    result += zone or ""
    try:
        datetime.datetime.fromisoformat(result)
    except ValueError:
        raise RedoParseError("Invalid temporal SQL_REDO literal") from None
    return result


@dataclass(frozen=True)
class Token:
    kind: str
    value: str


def tokenize(sql: str) -> list[Token]:
    tokens = []
    index = 0
    while index < len(sql):
        char = sql[index]
        if char.isspace():
            index += 1
            continue
        if char in "(),=;.":
            tokens.append(Token("symbol", char))
            index += 1
            continue
        if char == '"':
            index += 1
            value = []
            while index < len(sql):
                if sql[index] == '"':
                    if index + 1 < len(sql) and sql[index + 1] == '"':
                        value.append('"')
                        index += 2
                        continue
                    index += 1
                    break
                value.append(sql[index])
                index += 1
            else:
                raise RedoParseError("Unterminated quoted identifier in SQL_REDO")
            tokens.append(Token("identifier", "".join(value)))
            continue
        if char == "'":
            index += 1
            value = []
            while index < len(sql):
                if sql[index] == "'":
                    if index + 1 < len(sql) and sql[index + 1] == "'":
                        value.append("'")
                        index += 2
                        continue
                    index += 1
                    break
                value.append(sql[index])
                index += 1
            else:
                raise RedoParseError("Unterminated string literal in SQL_REDO")
            tokens.append(Token("string", "".join(value)))
            continue
        if char.isdigit() or (
            char in "+-"
            and index + 1 < len(sql)
            and (sql[index + 1].isdigit() or sql[index + 1] == ".")
        ):
            start = index
            index += 1
            while index < len(sql) and sql[index] in "0123456789.eE+-":
                if sql[index] in "+-" and sql[index - 1] not in "eE":
                    break
                index += 1
            tokens.append(Token("number", sql[start:index]))
            continue
        if char.isalpha() or char in "_$#":
            start = index
            index += 1
            while index < len(sql) and (sql[index].isalnum() or sql[index] in "_$#"):
                index += 1
            tokens.append(Token("word", sql[start:index]))
            continue
        raise RedoParseError("Unsupported token in SQL_REDO")
    return tokens


class Parser:
    def __init__(self, tokens: list[Token], schema: TableSchema):
        self.tokens = tokens
        self.schema = schema
        self.position = 0
        self.columns = {
            column.name.upper(): column.to_dict() for column in schema.columns
        }
        self.selected = {column.name.upper() for column in schema.replicated_columns}

    def parse(self, operation: str) -> tuple[dict, dict]:
        normalized = operation.upper()
        if normalized == "INSERT":
            values, keys = self._parse_insert()
        elif normalized == "UPDATE":
            values, keys = self._parse_update()
        elif normalized == "DELETE":
            values, keys = self._parse_delete()
        else:
            raise RedoParseError(f"Unsupported DML operation: {normalized}")
        if self._peek_value() == ";":
            self.position += 1
        if self.position != len(self.tokens):
            raise RedoParseError("Trailing unsupported SQL_REDO expression")
        return values, keys

    def _parse_insert(self) -> tuple[dict, dict]:
        self._expect_word("INSERT")
        self._expect_word("INTO")
        self._parse_table()
        columns = self._parse_identifier_list()
        self._expect_word("VALUES")
        self._expect_symbol("(")
        values = [self._parse_selected_literal(columns[0])]
        for index in range(1, len(columns)):
            self._expect_symbol(",")
            values.append(self._parse_selected_literal(columns[index]))
        self._expect_symbol(")")
        if len(values) != len(columns):
            raise RedoParseError("INSERT column/value count mismatch")
        result = {
            name.lower(): value
            for name, value in zip(columns, values, strict=True)
            if name in self.selected
        }
        expected = {column.name.lower() for column in self.schema.replicated_columns}
        if set(result) != expected:
            raise RedoParseError("INSERT redo does not contain a complete after-image")
        keys = {name.lower(): result[name.lower()] for name in self.schema.primary_key}
        return result, keys

    def _parse_update(self) -> tuple[dict, dict]:
        self._expect_word("UPDATE")
        self._parse_table()
        self._expect_word("SET")
        values = self._parse_assignments(stop_word="WHERE")
        self._expect_word("WHERE")
        keys = self._parse_where_predicates()
        return values, keys

    def _parse_delete(self) -> tuple[dict, dict]:
        self._expect_word("DELETE")
        self._expect_word("FROM")
        self._parse_table()
        self._expect_word("WHERE")
        return {}, self._parse_where_predicates()

    def _parse_assignments(self, stop_word: str) -> dict:
        result = {}
        while True:
            name = self._identifier().upper()
            self._column(name)
            self._expect_symbol("=")
            value = self._parse_selected_literal(name)
            if name in self.selected:
                result[name.lower()] = value
            if self._peek_word(stop_word):
                return result
            self._expect_symbol(",")

    def _parse_where_predicates(self) -> dict:
        result = {}
        primary_keys = {name.upper() for name in self.schema.primary_key}
        seen = set()
        while True:
            name = self._identifier().upper()
            column = (
                {"data_type": "VARCHAR2"} if name == "ROWID" else self._column(name)
            )
            if name in seen:
                raise RedoParseError("Duplicate column predicate in SQL_REDO")
            seen.add(name)
            if self._peek_word("IS"):
                self.position += 1
                self._expect_word("NULL")
                value = None
            else:
                self._expect_symbol("=")
                if name in self.selected or name == "ROWID":
                    value = self._parse_literal(column)
                else:
                    self._skip_literal()
                    value = None
            if name in primary_keys:
                if value is None:
                    raise RedoParseError("Primary-key predicate is NULL in SQL_REDO")
                result[name.lower()] = value
            if self._peek_value() in {None, ";"}:
                break
            self._expect_word("AND")
        if set(result) != {name.lower() for name in primary_keys}:
            raise RedoParseError("SQL_REDO does not contain the complete primary key")
        return result

    def _parse_selected_literal(self, name: str):
        column = self._column(name)
        if name in self.selected:
            return self._parse_literal(column)
        self._skip_literal()
        return None

    def _skip_literal(self) -> None:
        """Consume an excluded expression without reading or interpreting its value."""
        depth = 0
        start = self.position
        while self.position < len(self.tokens):
            token = self.tokens[self.position]
            if depth == 0 and (
                (token.kind == "symbol" and token.value in {",", ")", ";"})
                or (token.kind == "word" and token.value.upper() in {"AND", "WHERE"})
            ):
                break
            if token.kind == "symbol":
                if token.value == "(":
                    depth += 1
                elif token.value == ")":
                    depth -= 1
            self.position += 1
        if self.position == start or depth != 0:
            raise RedoParseError("Invalid excluded-column expression")

    def _parse_identifier_list(self) -> list[str]:
        self._expect_symbol("(")
        result = [self._identifier().upper()]
        while self._peek_value() == ",":
            self.position += 1
            result.append(self._identifier().upper())
        self._expect_symbol(")")
        if len(set(result)) != len(result):
            raise RedoParseError("Duplicate column in SQL_REDO")
        return result

    def _parse_table(self) -> None:
        parts = [self._identifier().upper()]
        while self._peek_value() == ".":
            self.position += 1
            parts.append(self._identifier().upper())
        if len(parts) == 1:
            owner = self.schema.owner.upper()
            table = parts[0]
        elif len(parts) == 2:
            owner, table = parts
        else:
            raise RedoParseError("Unsupported qualified table name")
        if owner != self.schema.owner.upper() or table != self.schema.name.upper():
            raise RedoParseError("SQL_REDO table does not match schema metadata")

    def _parse_literal(self, column: dict):
        token = self._current()
        oracle_type = str(column["data_type"]).upper()
        if token.kind == "word" and token.value.upper() == "NULL":
            self.position += 1
            return None
        if token.kind == "word" and token.value.upper() == "HEXTORAW":
            self.position += 1
            self._expect_symbol("(")
            value = self._expect_kind("string").value
            self._expect_symbol(")")
            try:
                return bytes.fromhex(value)
            except ValueError as exc:
                raise RedoParseError("Invalid HEXTORAW literal") from exc
        if token.kind == "word" and token.value.upper() in {
            "TO_DATE",
            "TO_TIMESTAMP",
            "TO_TIMESTAMP_TZ",
        }:
            self.position += 1
            self._expect_symbol("(")
            value = self._expect_kind("string").value.strip()
            if self._peek_value() == ",":
                self.position += 1
                self._expect_kind("string")
            self._expect_symbol(")")
            return normalize_temporal_literal(value, oracle_type)
        if (
            token.kind == "word"
            and token.value.upper() == "TIMESTAMP"
            and self.position + 1 < len(self.tokens)
        ):
            self.position += 1
            return normalize_temporal_literal(
                self._expect_kind("string").value, oracle_type
            )
        self.position += 1
        if token.kind == "string":
            if oracle_type == "NUMBER":
                try:
                    numeric_value = decimal.Decimal(token.value)
                    return convert_number_for_sdk(numeric_value, column)
                except (decimal.InvalidOperation, ValueError) as exc:
                    raise RedoParseError("Invalid NUMBER literal") from exc
            return token.value
        if token.kind == "number":
            try:
                numeric_value = decimal.Decimal(token.value)
                return convert_number_for_sdk(numeric_value, column)
            except (decimal.InvalidOperation, ValueError) as exc:
                raise RedoParseError("Invalid numeric literal") from exc
        raise RedoParseError("Unsupported SQL_REDO value expression")

    def _column(self, name: str) -> dict:
        column = self.columns.get(name.upper())
        if column is None:
            if self.schema.selected_columns is not None and name not in self.selected:
                # A frozen projection can replay across changes to unselected
                # columns. Their expressions are consumed without decoding.
                return {}
            raise RedoParseError(f"Unknown column in SQL_REDO: {name}")
        return column

    def _identifier(self) -> str:
        token = self._current()
        if token.kind not in {"identifier", "word"}:
            raise RedoParseError("Expected identifier in SQL_REDO")
        self.position += 1
        return token.value

    def _expect_word(self, value: str) -> None:
        token = self._expect_kind("word")
        if token.value.upper() != value:
            raise RedoParseError(f"Expected {value} in SQL_REDO")

    def _expect_symbol(self, value: str) -> None:
        token = self._expect_kind("symbol")
        if token.value != value:
            raise RedoParseError(f"Expected symbol {value} in SQL_REDO")

    def _expect_kind(self, kind: str) -> Token:
        token = self._current()
        if token.kind != kind:
            raise RedoParseError(f"Expected {kind} in SQL_REDO")
        self.position += 1
        return token

    def _current(self) -> Token:
        if self.position >= len(self.tokens):
            raise RedoParseError("Unexpected end of SQL_REDO")
        return self.tokens[self.position]

    def _peek_value(self) -> str | None:
        if self.position >= len(self.tokens):
            return None
        return self.tokens[self.position].value

    def _peek_word(self, value: str) -> bool:
        if self.position >= len(self.tokens):
            return False
        token = self.tokens[self.position]
        return token.kind == "word" and token.value.upper() == value


def parse_sql_redo(
    sql_redo: str, operation: str, schema: TableSchema
) -> tuple[dict, dict]:
    if not sql_redo or len(sql_redo) > 16 * 1024 * 1024:
        raise RedoParseError("SQL_REDO is empty or exceeds the parser limit")
    return Parser(tokenize(sql_redo), schema).parse(operation)
