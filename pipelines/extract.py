import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from sqlalchemy import create_engine
from vnstock import Vnstock
from urllib.parse import quote_plus

load_dotenv()


# KẾT NỐI DATABASE
def get_engine():
    user = os.getenv('DB_USER')
    password = quote_plus(os.getenv('DB_PASSWORD'))
    host = os.getenv('DB_HOST')
    port = os.getenv('DB_PORT')
    dbname = os.getenv('DB_NAME')
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
    return create_engine(url)

# EXTRACT 1: VNSTOCK - Giá cổ phiếu
def extract_stock(symbol: str, start: str, end: str) -> pd.DataFrame:
    print(f"  Extracting stock: {symbol} from {start} to {end}...")

    stock = Vnstock().stock(symbol=symbol, source="VCI")
    df = stock.quote.history(start=start, end=end, interval="1D")

    # Thêm cột symbol và ingested_at
    df["symbol"] = symbol
    df["ingested_at"] = datetime.now()

    # Đổi tên cột time → time (giữ nguyên)
    df = df.rename(columns={"time": "time"})

    print(f"  Got {len(df)} rows for {symbol}")
    return df

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

# LOAD VÀO RAW LAYER

def load_to_raw(df: pd.DataFrame, table: str):
    engine = get_engine()
    df.to_sql(
        table,
        schema="raw",
        con=engine,
        if_exists="append",
        index=False
    )
    print(f"  Loaded {len(df)} rows to raw.{table}")


# HÀM CHÍNH
def run_extract():
    print("=" * 50)
    print("EXTRACT PHASE")
    print("=" * 50)

    # Lấy data 1 năm gần nhất
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    # Extract và load stock (3 mã cổ phiếu)
    for symbol in ["VNM", "VCB", "FPT"]:
        df = extract_stock(symbol, start_date, end_date)
        load_to_raw(df, "stock_prices")

    # Extract và load crypto
    df = extract_crypto("BTC", "bitcoin", days=30)
    load_to_raw(df, "crypto_prices")

    df = extract_crypto("ETH", "ethereum", days=30)
    load_to_raw(df, "crypto_prices")

    # Extract và load exchange rates
    df = extract_exchange_rates("USD", ["VND", "EUR", "JPY"])
    load_to_raw(df, "exchange_rates")

    print("\n Extract phase complete!")


if __name__ == "__main__":
    run_extract()