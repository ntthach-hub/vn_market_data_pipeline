import sys
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from pipelines.extract import extract_stock, run_extract, run_stock_extract


def test_stock_extraction_keeps_vietnam_trading_date_and_sql_columns(monkeypatch):
    monkeypatch.setenv("VNSTOCK_SOURCE", "fhsc")
    monkeypatch.setenv("FHSC_API_KEY", "test-key")
    market = Mock()
    monkeypatch.setitem(sys.modules, "vnstock", SimpleNamespace(Market=market))
    ohlcv = market.return_value.equity.return_value.ohlcv
    ohlcv.return_value = pd.DataFrame({
        "time": pd.to_datetime(["2026-11-19 18:00:00Z"]),
        "open": [95.0], "high": [97.0], "low": [94.0], "close": [96.0],
        "volume": [100], "extra_column": ["ignored"],
    })

    result = extract_stock("FPT", "2026-11-19", "2026-11-20")

    market.assert_called_once_with("fhsc")
    market.return_value.equity.assert_called_once_with("FPT")
    ohlcv.assert_called_once_with(start="2026-11-19", end="2026-11-20", interval="1D")
    assert list(result.columns) == [
        "time", "open", "high", "low", "close", "volume", "symbol", "ingested_at"
    ]
    assert result.loc[0, "time"] == date(2026, 11, 20)
    assert result.loc[0, "close"] == 96.0


def test_pipeline_reports_missing_stock_key_before_opening_database(monkeypatch):
    monkeypatch.delenv("STOCK_CSV_DIR", raising=False)
    monkeypatch.setenv("VNSTOCK_SOURCE", "ssi")
    monkeypatch.setenv("SSI_API_KEY", "test-key")
    monkeypatch.delenv("SSI_API_SECRET", raising=False)
    database = Mock()
    monkeypatch.setattr("pipelines.extract.get_engine", database)

    with pytest.raises(ValueError, match="SSI_API_SECRET"):
        run_extract()

    database.assert_not_called()


def test_csv_stock_source_upserts_all_tickers_without_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCK_CSV_DIR", str(tmp_path))
    monkeypatch.delenv("VNSTOCK_SOURCE", raising=False)
    api = Mock()
    upsert = Mock()
    monkeypatch.setattr("pipelines.extract.extract_stock", api)
    monkeypatch.setattr("pipelines.extract.upsert_to_raw", upsert)

    for symbol in ("VNM", "VCB", "FPT"):
        (tmp_path / f"{symbol}.csv").write_text(
            "Ticker,Date,Open,High,Low,Close,Volume\n"
            f"{symbol},2026-11-19,95,97,94,96,100\n",
            encoding="utf-8-sig",
        )

    run_stock_extract()

    api.assert_not_called()
    assert [call.args[0].iloc[0]["symbol"] for call in upsert.call_args_list] == ["VNM", "VCB", "FPT"]
    for call in upsert.call_args_list:
        rows, table = call.args
        assert table == "stock_prices"
        assert call.kwargs["conflict_cols"] == ["symbol", "time"]
        assert rows.iloc[0]["time"] == date(2026, 11, 19)
        assert rows.iloc[0]["close"] == 96

    upsert.reset_mock()
    (tmp_path / "FPT.csv").unlink()
    with pytest.raises(FileNotFoundError, match="FPT.csv"):
        run_stock_extract()
    upsert.assert_not_called()
