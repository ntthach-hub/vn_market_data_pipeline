import os
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine ,text
from urllib.parse import quote_plus

load_dotenv()

def get_engine():
    user = os.getenv('DB_USER')
    password = quote_plus(os.getenv('DB_PASSWORD'))
    host = os.getenv('DB_HOST')
    port = os.getenv('DB_PORT')
    dbname = os.getenv('DB_NAME')
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
    return create_engine(url)


# TRANSFORM 1: STOCK PRICES
def transform_stock() -> pd.DataFrame:
    print("  Transforming stock prices...")
    engine = get_engine()

    # đọc từ raw layer
    df = pd.read_sql("SELECT * FROM raw.stock_prices", con=engine)
    # doi ten cot time -> date
    df = df.rename(columns={"time": "date"})
    # xoa cot id va ingested_at (khong can trong staging)
    df = df.drop(columns=["id","ingested_at"])
    # Chuan hoa du lieu
    df["date"] = pd.to_datetime(df["date"])
    df["symbol"] = df["symbol"].str.upper().str.strip()

    df = df.drop_duplicates(subset=["symbol", "date"], keep="first")
    # Kiểm tra NULL
    null_count = df[["symbol", "date", "close"]].isnull().sum().sum()
    assert null_count == 0, f" Stock có {null_count} NULL ở cột quan trọng!"

    # Thêm cột processed_at
    df["processed_at"] = datetime.now()

    print(f" Stock: {len(df)} rows sau transform")
    return df

# TRANSFORM 2: CRYPTO PRICES
def transform_crypto() -> pd.DataFrame:
    print("  Transforming crypto prices...")
    engine = get_engine()

    # Đọc từ raw layer
    df_crypto = pd.read_sql("SELECT * FROM raw.crypto_prices", con=engine)
    df_rates = pd.read_sql(
        "SELECT rate FROM raw.exchange_rates WHERE target = 'VND' ORDER BY id DESC LIMIT 1",
        con=engine
    )
    # Lay ti gia USD/VND moi nhat
    usd_vnd_rate = df_rates["rate"].iloc[0]
    print(f" Ti gia USD/VND: {usd_vnd_rate}")
    # Convert timestamp_ms → date và hour
    df_crypto["datetime"] = pd.to_datetime(df_crypto["timestamp_ms"], unit="ms")
    df_crypto["date"] = df_crypto["datetime"].dt.date
    df_crypto["hour"] = df_crypto["datetime"].dt.hour

    # tinh price_vnd
    df_crypto["price_vnd"] = df_crypto["price_usd"]* usd_vnd_rate
    # Xóa cột không cần
    df_crypto = df_crypto.drop(columns=["id", "timestamp_ms", "datetime", "ingested_at"])

    # Xóa dòng trùng lặp
    df_crypto = df_crypto.drop_duplicates(subset=["symbol", "date", "hour"], keep="first")

    # Kiểm tra NULL
    null_count = df_crypto[["symbol", "date", "price_usd"]].isnull().sum().sum()
    assert null_count == 0, f" Crypto có {null_count} NULL!"

    # Thêm cột processed_at
    df_crypto["processed_at"] = datetime.now()

    print(f" Crypto: {len(df_crypto)} rows sau transform")
    return df_crypto

# TRANSFORM 3: EXCHANGE RATES
def transform_exchange_rates() -> pd.DataFrame:
    print("Transform exchange rates...")
    engine = get_engine()

    df = pd.read_sql("SELECT * FROM raw.exchange_rates", con=engine)

    df = df.drop(columns=["id", "ingested_at"])

    # Chuẩn hóa kiểu dữ liệu
    df["date"] = pd.to_datetime(df["date"])
    df["base"] = df["base"].str.upper().str.strip()
    df["target"] = df["target"].str.upper().str.strip()

    # Xóa dòng trùng lặp
    df = df.drop_duplicates(subset=["base", "target", "date"], keep="first")

    # Thêm cột processed_at
    df["processed_at"] = datetime.now()

    print(f" Exchange rates: {len(df)} rows sau transform")
    return df

#lOAD VAO STAGING LAYER
def load_to_staging(df: pd.DataFrame, table: str):
    engine = get_engine()
    # Xóa data cũ trước khi insert mới (tránh duplicate)
    with engine.connect() as conn:
        conn.execute(text(f"TRUNCATE TABLE staging.{table}"))
        conn.commit()
    df.to_sql(
        table,
        schema="staging",
        con=engine,
        if_exists="append",
        index=False
    )
    print(f" Loaded {len(df)} rows to staging.{table}")

#HAM CHINH
def run_transform():
    print("=" * 50)
    print("TRANSFORM PHASE")
    print("=" * 50)

    # Transform và load stock
    df_stock = transform_stock()
    load_to_staging(df_stock, "stock_prices")
    
    # Transform và load crypto
    df_crypto = transform_crypto()
    load_to_staging(df_crypto, "crypto_prices")

    # Transform và load exchange rates
    df_rates = transform_exchange_rates()
    load_to_staging(df_rates, "exchange_rates")
    print("\n Transform phase complete!")

if __name__ == "__main__":
    run_transform()