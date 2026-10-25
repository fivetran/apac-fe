import pytest

from schema_evolution.ddl_detector import DdlKind, classify_ddl


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        (
            (
                'ALTER SESSION SET CURRENT_SCHEMA = "APP"; '
                'GRANT INSERT ON "APP"."ORDERS" TO "FIVETRAN"'
            ),
            DdlKind.NON_STRUCTURAL,
        ),
        (
            'REVOKE UPDATE ON "APP"."ORDERS" FROM "FIVETRAN"',
            DdlKind.NON_STRUCTURAL,
        ),
        (
            (
                'COMMENT ON TABLE "APP"."ORDERS" IS '
                "'TRUNCATE TABLE ignored inside a string'"
            ),
            DdlKind.NON_STRUCTURAL,
        ),
        (
            'TRUNCATE TABLE "APP"."ORDERS" DROP STORAGE',
            DdlKind.TRUNCATE,
        ),
        (
            ('ALTER TABLE "APP"."ORDERS" ADD ("A" VARCHAR2(20), "B" NUMBER)'),
            DdlKind.TABLE_SCHEMA_CHANGE,
        ),
        (
            'FLASHBACK TABLE "APP"."ORDERS" TO SCN 100',
            DdlKind.DATA_REWRITE,
        ),
        ("BEGIN NULL; END;", DdlKind.UNKNOWN),
    ],
)
def test_classifies_ddl_without_matching_keywords_in_literals(sql, expected):
    assert classify_ddl(sql) == expected
