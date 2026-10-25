import pytest

from schema_evolution.ddl_detector import DdlKind, classify_ddl


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        (
            (
                'ALTER SESSION SET CURRENT_SCHEMA = "ANIMAL_CROSSING"; '
                'GRANT INSERT ON "ANIMAL_CROSSING"."HOUSEWARES" TO "FIVETRAN"'
            ),
            DdlKind.NON_STRUCTURAL,
        ),
        (
            'REVOKE UPDATE ON "ANIMAL_CROSSING"."HOUSEWARES" FROM "FIVETRAN"',
            DdlKind.NON_STRUCTURAL,
        ),
        (
            (
                'COMMENT ON TABLE "ANIMAL_CROSSING"."HOUSEWARES" IS '
                "'TRUNCATE TABLE ignored inside a string'"
            ),
            DdlKind.NON_STRUCTURAL,
        ),
        (
            'TRUNCATE TABLE "ANIMAL_CROSSING"."HOUSEWARES" DROP STORAGE',
            DdlKind.TRUNCATE,
        ),
        (
            (
                'ALTER TABLE "ANIMAL_CROSSING"."HOUSEWARES" '
                'ADD ("A" VARCHAR2(20), "B" NUMBER)'
            ),
            DdlKind.TABLE_SCHEMA_CHANGE,
        ),
        (
            'FLASHBACK TABLE "ANIMAL_CROSSING"."HOUSEWARES" TO SCN 100',
            DdlKind.DATA_REWRITE,
        ),
        ("BEGIN NULL; END;", DdlKind.UNKNOWN),
    ],
)
def test_classifies_ddl_without_matching_keywords_in_literals(sql, expected):
    assert classify_ddl(sql) == expected
