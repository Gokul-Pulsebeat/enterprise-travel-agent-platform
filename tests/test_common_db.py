"""Unit tests for common/db.py. No database needed."""

import pytest

from common.db import DEFAULT_DATABASE_URL, build_engine, env_flag, get_database_url, normalize_database_url


def test_postgresql_scheme_is_rewritten_for_asyncpg():
    url = normalize_database_url("postgresql://user:secret@db.example.com:5432/travel")
    assert url.drivername == "postgresql+asyncpg"
    assert (url.username, url.host, url.port, url.database) == ("user", "db.example.com", 5432, "travel")


def test_postgres_scheme_alias_is_accepted():
    assert normalize_database_url("postgres://user:secret@db.example.com/travel").drivername == "postgresql+asyncpg"


def test_asyncpg_scheme_is_left_alone():
    assert normalize_database_url("postgresql+asyncpg://user:secret@db.example.com/travel").drivername == (
        "postgresql+asyncpg"
    )


def test_neon_style_uri_is_made_asyncpg_compatible():
    # Neon hands out sslmode and channel_binding; asyncpg rejects sslmode and does not implement channel_binding.
    url = normalize_database_url(
        "postgresql://travel_app:s3cret@ep-cool-name-123456.us-east-2.aws.neon.tech/travel_agent"
        "?sslmode=require&channel_binding=require"
    )
    assert dict(url.query) == {"ssl": "require"}


def test_explicit_ssl_option_wins_over_sslmode():
    url = normalize_database_url("postgresql://u:p@h/db?sslmode=require&ssl=verify-full")
    assert dict(url.query) == {"ssl": "verify-full"}


def test_url_without_query_options_stays_without_them():
    assert dict(normalize_database_url("postgresql://u:p@h/db").query) == {}


def test_percent_encoded_password_is_preserved():
    assert normalize_database_url("postgresql://u:p%40ss%2Fword@h/db").password == "p@ss/word"


def test_other_schemes_are_rejected_without_leaking_the_password():
    with pytest.raises(ValueError) as error:
        normalize_database_url("mysql://user:topsecret@h/db")
    assert "mysql" in str(error.value)
    assert "topsecret" not in str(error.value)


def test_database_url_defaults_to_the_compose_development_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_database_url() == DEFAULT_DATABASE_URL


def test_database_url_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@elsewhere/db")
    assert get_database_url() == "postgresql://u:p@elsewhere/db"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("1", True), ("YES", True), (" on ", True), ("false", False), ("0", False), ("", False)],
)
def test_env_flag_parsing(monkeypatch, raw, expected):
    monkeypatch.setenv("SOME_FLAG", raw)
    assert env_flag("SOME_FLAG", default=not expected) is expected


def test_env_flag_uses_the_default_when_unset(monkeypatch):
    monkeypatch.delenv("SOME_FLAG", raising=False)
    assert env_flag("SOME_FLAG", default=True) is True
    assert env_flag("SOME_FLAG", default=False) is False


def test_engine_pool_defaults_are_small(monkeypatch):
    monkeypatch.delenv("DB_POOL_SIZE", raising=False)
    # Creating an engine does not connect, so this needs no database.
    assert build_engine("postgresql://u:p@h/db").pool.size() == 3


def test_engine_pool_size_is_configurable(monkeypatch):
    monkeypatch.setenv("DB_POOL_SIZE", "5")
    assert build_engine("postgresql://u:p@h/db").pool.size() == 5
