"""Classify Oracle DDL without logging or exposing the original SQL text."""

from enum import Enum


class DdlKind(str, Enum):
    NON_STRUCTURAL = "NON_STRUCTURAL"
    TRUNCATE = "TRUNCATE"
    TABLE_SCHEMA_CHANGE = "TABLE_SCHEMA_CHANGE"
    DATA_REWRITE = "DATA_REWRITE"
    UNKNOWN = "UNKNOWN"


def _tokens(sql: str) -> list[str]:
    """Tokenize enough Oracle SQL to classify DDL safely.

    Quoted strings and comments are consumed as opaque tokens so keywords
    embedded in literals cannot affect classification.
    """
    result = []
    index = 0
    while index < len(sql):
        char = sql[index]
        if char.isspace():
            index += 1
            continue
        if sql.startswith("--", index):
            newline = sql.find("\n", index + 2)
            index = len(sql) if newline == -1 else newline + 1
            continue
        if sql.startswith("/*", index):
            end = sql.find("*/", index + 2)
            index = len(sql) if end == -1 else end + 2
            continue
        if char == "'":
            index += 1
            while index < len(sql):
                if sql[index] == "'" and index + 1 < len(sql) and sql[index + 1] == "'":
                    index += 2
                    continue
                if sql[index] == "'":
                    index += 1
                    break
                index += 1
            result.append("<STRING>")
            continue
        if char == '"':
            index += 1
            value = []
            while index < len(sql):
                if sql[index] == '"' and index + 1 < len(sql) and sql[index + 1] == '"':
                    value.append('"')
                    index += 2
                    continue
                if sql[index] == '"':
                    index += 1
                    break
                value.append(sql[index])
                index += 1
            result.append("".join(value).upper())
            continue
        if char.isalnum() or char in "_$#":
            end = index + 1
            while end < len(sql) and (sql[end].isalnum() or sql[end] in "_$#"):
                end += 1
            result.append(sql[index:end].upper())
            index = end
            continue
        result.append(char)
        index += 1
    return result


def _without_session_preamble(tokens: list[str]) -> list[str]:
    remaining = tokens
    while remaining[:3] == ["ALTER", "SESSION", "SET"]:
        try:
            separator = remaining.index(";")
        except ValueError:
            return []
        remaining = remaining[separator + 1 :]
    return remaining


def classify_ddl(sql: str) -> DdlKind:
    tokens = _without_session_preamble(_tokens(sql))
    words = [token for token in tokens if token not in {";", "(", ")", ",", ".", "="}]
    if words[:2] == ["TRUNCATE", "TABLE"]:
        return DdlKind.TRUNCATE
    if words and words[0] in {
        "ANALYZE",
        "AUDIT",
        "COMMENT",
        "GRANT",
        "NOAUDIT",
        "REVOKE",
    }:
        return DdlKind.NON_STRUCTURAL
    if tuple(words[:2]) in {
        ("ALTER", "INDEX"),
        ("DROP", "INDEX"),
    } or words[:3] == ["CREATE", "UNIQUE", "INDEX"]:
        return DdlKind.NON_STRUCTURAL
    if words[:2] == ["CREATE", "INDEX"]:
        return DdlKind.NON_STRUCTURAL
    if words[:2] == ["FLASHBACK", "TABLE"]:
        return DdlKind.DATA_REWRITE
    if tuple(words[:2]) in {
        ("ALTER", "TABLE"),
        ("CREATE", "TABLE"),
        ("DROP", "TABLE"),
        ("RENAME", "TABLE"),
    }:
        return DdlKind.TABLE_SCHEMA_CHANGE
    return DdlKind.UNKNOWN
