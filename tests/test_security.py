from ubs_hackathon.datasource import ALLOWED_SQL_START, FORBIDDEN_SQL


def test_mutating_sql_is_detected() -> None:
    assert FORBIDDEN_SQL.search("DROP TABLE users") is not None
    assert FORBIDDEN_SQL.search("insert into t values (1)") is not None


def test_read_only_sql_allowed_pattern() -> None:
    assert ALLOWED_SQL_START.search("SELECT * FROM customers") is not None
    assert (
        ALLOWED_SQL_START.search("  with x as (select 1) select * from x") is not None
    )
