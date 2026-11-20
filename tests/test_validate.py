"""Regression tests; use an in-memory DB, never the project's PostgreSQL."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, text


spec = importlib.util.spec_from_file_location(
    "pipeline_validate", Path(__file__).resolve().parents[1] / "pipelines" / "validate.py"
)
validate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate)


def test_empty_table_fails():
    conn = Mock()
    conn.execute.return_value.scalar_one.return_value = 0
    with pytest.raises(ValueError, match="raw.stock_prices"):
        validate.check_row_counts(conn)


def test_all_tables_must_have_rows():
    conn = Mock()
    conn.execute.return_value.scalar_one.side_effect = [1, 1, 1, 1, 1, 1, 0]
    with pytest.raises(ValueError, match="analytics.daily_market_summary"):
        validate.check_row_counts(conn)


@pytest.mark.parametrize("staging_symbol,expect_error", [("FPT", False), ("VCB", True), (None, True)])
def test_stock_keys_must_match_even_when_counts_match(staging_symbol, expect_error):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("ATTACH DATABASE ':memory:' AS raw"))
        conn.execute(text("ATTACH DATABASE ':memory:' AS staging"))
        conn.execute(text("CREATE TABLE raw.stock_prices (symbol TEXT, time DATE)"))
        conn.execute(text("CREATE TABLE staging.stock_prices (symbol TEXT, date DATE)"))
        conn.execute(text("INSERT INTO raw.stock_prices VALUES ('FPT', '2026-01-01')"))
        if staging_symbol is not None:
            conn.execute(text("INSERT INTO staging.stock_prices VALUES (:symbol, '2026-01-01')"), {"symbol": staging_symbol})
        if expect_error:
            with pytest.raises(ValueError, match="business key"):
                validate.check_row_consistency(conn)
        else:
            validate.check_row_consistency(conn)
    engine.dispose()


def test_extra_staging_key_fails():
    conn = Mock()
    conn.execute.return_value.scalar_one.side_effect = [0, 1]
    with pytest.raises(ValueError, match="business key"):
        validate.check_row_consistency(conn)


def test_null_data_fails():
    conn = Mock()
    conn.execute.return_value.scalar_one.return_value = 1
    with pytest.raises(ValueError, match="NULL"):
        validate.check_nulls(conn)
