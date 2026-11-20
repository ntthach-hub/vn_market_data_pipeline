import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, Table, MetaData
from sqlalchemy.dialects.postgresql import insert as pg_insert
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

load_dotenv()

STOCK_SOURCE_KEYS = {
    "ssi": ("SSI_API_KEY", "SSI_API_SECRET"),
    "dnse": ("DNSE_API_KEY", "DNSE_API_SECRET"),
    "fhsc": ("FHSC_API_KEY",),
    "tcbs": ("TCBS_API_KEY",),
}
STOCK_SYMBOLS = ("VNM", "VCB", "FPT")


def get_stock_source() -> str:
    source = os.getenv("VNSTOCK_SOURCE", "").strip().lower()
    if source not in STOCK_SOURCE_KEYS:
        raise ValueError(
            "Set STOCK_CSV_DIR=data/stocks in .env to read CSV files, "
            "or set VNSTOCK_SOURCE to ssi, dnse, fhsc or tcbs to use Open API."
        )
    missing = [name for name in STOCK_SOURCE_KEYS[source] if not os.getenv(name, "").strip()]
    if missing:
        raise ValueError(f"Missing credentials for {source}: set {', '.join(missing)} in .env.")
    return source

# KẾT NỐI DATABASE
def get_engine():
    user = os.getenv('DB_USER')
    password = quote_plus(os.getenv('DB_PASSWORD'))
    host = os.getenv('DB_HOST')
    port = os.getenv('DB_PORT')
    dbname = os.getenv('DB_NAME')
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
    return create_engine(url)

# UPSERT VÀO RAW LAYER
def upsert_to_raw(df: pd.DataFrame, table: str, conflict_cols: list):
    if df.empty:
        print(f"  Không có dòng mới cho raw.{table}, bỏ qua.")
        return

    # Chuyển đổi cột datetime thành string để SQLAlchemy xử lý đúng
    for col in df.select_dtypes(include=['datetime64']).columns:
        df[col] = df[col].astype(str)

    engine = get_engine()
    metadata = MetaData(schema="raw")
    tbl = Table(table, metadata, autoload_with=engine)

    records = df.to_dict(orient="records")

    update_cols = {
        c.name: c
        for c in tbl.columns
        if c.name not in conflict_cols and c.name not in ("id", "ingested_at")
    }

    stmt = pg_insert(tbl).values(records)
    stmt = stmt.on_conflict_do_update(
        index_elements=conflict_cols,
        set_={col: getattr(stmt.excluded, col) for col in update_cols},
    )

    with engine.begin() as conn:
        conn.execute(stmt)

    print(f"  Upserted {len(records)} rows vào raw.{table}")

# Lấy ngày cuối cùng đã extract (QUAN TRỌNG - PHẢI CÓ)
def get_last_extracted_date(table: str, symbol: str, date_col: str):
    engine = get_engine()
    query = text(f"SELECT MAX({date_col}) FROM raw.{table} WHERE symbol = :symbol")
    with engine.connect() as conn:
        result = conn.execute(query, {"symbol": symbol}).scalar()
    return result
# EXTRACT 1: VNSTOCK - Giá cổ phiếu
def extract_stock(symbol: str, start: str, end: str) -> pd.DataFrame:
    source = get_stock_source()
    from vnstock import Market

    print(f"  Extracting stock: {symbol} from {source} ({start} to {end})...")
    bars = Market(source).equity(symbol).ohlcv(start=start, end=end, interval="1D")
    columns = ["time", "open", "high", "low", "close", "volume"]
    if bars.empty:
        return pd.DataFrame(columns=[*columns, "symbol", "ingested_at"])
    df = bars.loc[:, columns].copy()
    trading_time = pd.to_datetime(df["time"])
    if trading_time.dt.tz is not None:
        trading_time = trading_time.dt.tz_convert("Asia/Ho_Chi_Minh")
    df["time"] = trading_time.dt.date
    df = df.drop_duplicates(subset=["time"], keep="last")
    df["symbol"] = symbol
    df["ingested_at"] = datetime.now()

    print(f"  Got {len(df)} rows for {symbol}")
    return df


def extract_stock_csv(directory: Path, symbol: str) -> pd.DataFrame:
    """Read a daily OHLCV export with prices in thousands of VND."""
    path = directory / f"{symbol}.csv"
    if not path.is_file():
        raise FileNotFoundError(f"Stock CSV not found: {path}")
    columns = ["Ticker", "Date", "Open", "High", "Low", "Close", "Volume"]
    rows = pd.read_csv(path, encoding="utf-8-sig")
    missing = set(columns) - set(rows.columns)
    if missing:
        raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")
    rows = rows.loc[:, columns].copy()
    rows.columns = ["symbol", "time", "open", "high", "low", "close", "volume"]
    rows["symbol"] = rows["symbol"].astype("string").str.strip().str.upper()
    if rows.empty or rows["symbol"].isna().any() or (rows["symbol"] != symbol).any():
        raise ValueError(f"{path}: expected at least one row and only ticker {symbol}.")
    rows["time"] = pd.to_datetime(rows["time"], format="%Y-%m-%d", errors="raise").dt.date
    if rows["time"].isna().any() or rows.duplicated(["symbol", "time"]).any():
        raise ValueError(f"{path}: found missing or duplicate trading dates.")
    prices = ["open", "high", "low", "close"]
    for column in [*prices, "volume"]:
        rows[column] = pd.to_numeric(rows[column], errors="raise")
    if not ((rows[prices] > 0) & (rows[prices] < float("inf"))).all().all():
        raise ValueError(f"{path}: OHLC prices must be finite and greater than zero.")
    volume = rows["volume"]
    if not ((volume >= 0) & (volume % 1 == 0) & (volume < 2**63)).all():
        raise ValueError(f"{path}: volume must be a non-negative integer within BIGINT range.")
    rows["volume"] = volume.astype("int64")
    print(f"  Read {len(rows)} historical stock rows from {path.name} ({rows['time'].min()} to {rows['time'].max()}).")
    return rows


def run_stock_extract():
    directory = os.getenv("STOCK_CSV_DIR", "").strip()
    if directory:
        # Validate all requested files before writing any stock rows.
        batches = [extract_stock_csv(Path(directory), symbol) for symbol in STOCK_SYMBOLS]
        for batch in batches:
            upsert_to_raw(batch, "stock_prices", conflict_cols=["symbol", "time"])
        return

    get_stock_source()
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    for symbol in STOCK_SYMBOLS:
        last_date = get_last_extracted_date("stock_prices", symbol, "time")
        start = last_date or today - timedelta(days=365)
        batch = extract_stock(symbol, start.isoformat(), today.isoformat())
        upsert_to_raw(batch, "stock_prices", conflict_cols=["symbol", "time"])


# EXTRACT 2: COINGECKO - Giá crypto
def extract_crypto(symbol: str, coin_id: str, days: int = 30) -> pd.DataFrame:
    print(f"  Extracting crypto: {symbol} ({days} days)...")

    response = requests.get(
        f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
        params={"vs_currency": "usd", "days": str(days)}
    )
    data = response.json()

    df = pd.DataFrame(data["prices"], columns=["timestamp_ms", "price_usd"])
    df["symbol"] = symbol
    df["ingested_at"] = datetime.now()

    print(f"   Got {len(df)} rows for {symbol}")
    return df

# EXTRACT 3: EXCHANGE RATE - Tỉ giá
def extract_exchange_rates(base: str = "USD", targets: list = ["VND", "EUR"]) -> pd.DataFrame:
    print(f"  Extracting exchange rates: {base} -> {targets}...")

    response = requests.get(f"https://api.exchangerate-api.com/v4/latest/{base}")
    data = response.json()

    rows = []
    for target in targets:
        rows.append({
            "base": base,
            "target": target,
            "rate": data["rates"][target],
            "date": data["date"],
            "ingested_at": datetime.now()
        })

    df = pd.DataFrame(rows)
    print(f"   Got {len(df)} exchange rates")
    return df

# HÀM CHÍNH
def run_extract():
    print("=" * 50)
    print("EXTRACT PHASE")
    print("=" * 50)


    run_stock_extract()
 
    # Crypto: CoinGecko luôn trả nguyên cửa sổ N ngày gần nhất,
    # upsert xử lý phần trùng lặp giúp mình.
    df = extract_crypto("BTC", "bitcoin", days=30)
    upsert_to_raw(df, "crypto_prices", conflict_cols=["symbol", "timestamp_ms"])
 
    df = extract_crypto("ETH", "ethereum", days=30)
    upsert_to_raw(df, "crypto_prices", conflict_cols=["symbol", "timestamp_ms"])
 
    # Exchange rate: API luôn trả tỉ giá tại thời điểm gọi.
    df = extract_exchange_rates("USD", ["VND", "EUR", "JPY"])
    upsert_to_raw(df, "exchange_rates", conflict_cols=["base", "target", "date"])
 
    print("\n Extract phase complete!")
if __name__ == "__main__":
    run_extract()
