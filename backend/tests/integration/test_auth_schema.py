import pytest
from sqlalchemy import inspect, text

from app.db.session import SessionFactory

pytestmark = pytest.mark.integration


def test_auth_schema_exists() -> None:
    with SessionFactory() as session:
        result = session.execute(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = 'vantage_auth'")
        ).scalar()
    assert result == 1


def test_expected_tables_exist() -> None:
    with SessionFactory() as session:
        names = set(inspect(session.connection()).get_table_names(schema="vantage_auth"))
    assert {"users", "refresh_tokens", "email_tokens", "auth_attempts"} <= names


def test_email_is_unique() -> None:
    with SessionFactory() as session:
        indexes = inspect(session.connection()).get_indexes("users", schema="vantage_auth")
        uniques = inspect(session.connection()).get_unique_constraints(
            "users", schema="vantage_auth"
        )
    unique_cols = [tuple(i["column_names"]) for i in indexes if i["unique"]]
    unique_cols += [tuple(u["column_names"]) for u in uniques]
    assert ("email",) in unique_cols


def test_public_id_is_unique_so_it_can_be_a_foreign_key_target() -> None:
    with SessionFactory() as session:
        uniques = inspect(session.connection()).get_unique_constraints(
            "users", schema="vantage_auth"
        )
        indexes = inspect(session.connection()).get_indexes("users", schema="vantage_auth")
    unique_cols = [tuple(u["column_names"]) for u in uniques]
    unique_cols += [tuple(i["column_names"]) for i in indexes if i["unique"]]
    assert ("public_id",) in unique_cols


def test_public_holds_no_grants_on_auth_tables() -> None:
    # Mirrors the Phase 1 least-privilege assertion. In Compose and CI this is
    # enforced; see the spec for why production on Essential-tier Heroku
    # Postgres cannot make the same guarantee.
    with SessionFactory() as session:
        leaked = session.execute(
            text(
                """
                SELECT count(*) FROM information_schema.role_table_grants
                WHERE table_schema = 'vantage_auth' AND grantee = 'PUBLIC'
                """
            )
        ).scalar()
    assert leaked == 0
