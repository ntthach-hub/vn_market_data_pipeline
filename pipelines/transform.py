import os
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, Table, MetaData
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
 
    df = pd.read_sql("SELECT * FROM raw.stock_prices", con=engine)
    df = df.rename(columns={"time": "date"})
    df = df.drop(columns=["id", "ingested_at"])
 
    df["date"] = pd.to_datetime(df["date"])
    df["symbol"] = df["symbol"].str.upper().str.strip()
 
    df = df.drop_duplicates(subset=["symbol", "date"], keep="first")
 
    null_count = df[["symbol", "date", "close"]].isnull().sum().sum()
    assert null_count == 0, f" Stock có {null_count} NULL ở cột quan trọng!"
 
    df["processed_at"] = datetime.now()
 
    print(f" Stock: {len(df)} rows sau transform")
    return df
 
 
# TRANSFORM 2: CRYPTO PRICES
def transform_crypto() -> pd.DataFrame:
    print("  Transforming crypto prices...")
    engine = get_engine()
 
    df_crypto = pd.read_sql("SELECT * FROM raw.crypto_prices", con=engine)
    df_rates = pd.read_sql(
        "SELECT rate FROM raw.exchange_rates WHERE target = 'VND' ORDER BY id DESC LIMIT 1",
        con=engine
    )
    usd_vnd_rate = df_rates["rate"].iloc[0]
    print(f" Ti gia USD/VND: {usd_vnd_rate}")
 
    df_crypto["datetime"] = pd.to_datetime(df_crypto["timestamp_ms"], unit="ms")
    df_crypto["date"] = df_crypto["datetime"].dt.date
    df_crypto["hour"] = df_crypto["datetime"].dt.hour
 
    df_crypto["price_vnd"] = df_crypto["price_usd"] * usd_vnd_rate
    df_crypto = df_crypto.drop(columns=["id", "timestamp_ms", "datetime", "ingested_at"])
 
    df_crypto = df_crypto.drop_duplicates(subset=["symbol", "date", "hour"], keep="first")
 
    null_count = df_crypto[["symbol", "date", "price_usd"]].isnull().sum().sum()
    assert null_count == 0, f" Crypto có {null_count} NULL!"
 
    df_crypto["processed_at"] = datetime.now()
 
    print(f" Crypto: {len(df_crypto)} rows sau transform")
    return df_crypto
 
 
# TRANSFORM 3: EXCHANGE RATES
def transform_exchange_rates() -> pd.DataFrame:
    print("Transform exchange rates...")
    engine = get_engine()
 
    df = pd.read_sql("SELECT * FROM raw.exchange_rates", con=engine)
    df = df.drop(columns=["id", "ingested_at"])
 
    df["date"] = pd.to_datetime(df["date"])
    df["base"] = df["base"].str.upper().str.strip()
    df["target"] = df["target"].str.upper().str.strip()
 
    df = df.drop_duplicates(subset=["base", "target", "date"], keep="first")
 
    df["processed_at"] = datetime.now()
 
    print(f" Exchange rates: {len(df)} rows sau transform")
    return df
 
 
# UPSERT VÀO STAGING LAYER (thay cho TRUNCATE + append)
def upsert_to_staging(df: pd.DataFrame, table: str, conflict_cols: list):
    if df.empty:
        print(f"  Không có dòng nào cho staging.{table}, bỏ qua.")
        return
 
    engine = get_engine()
    metadata = MetaData(schema="staging")
    tbl = Table(table, metadata, autoload_with=engine)
 
    records = df.to_dict(orient="records")
 
    # processed_at bị loại khỏi update_cols -> row cũ giữ nguyên
    # processed_at gốc, chỉ cột data được cập nhật.
    update_cols = {
        c.name: c
        for c in tbl.columns
        if c.name not in conflict_cols and c.name not in ("id", "processed_at")
    }
 
    stmt = pg_insert(tbl).values(records)
    stmt = stmt.on_conflict_do_update(
        index_elements=conflict_cols,
        set_={col: getattr(stmt.excluded, col) for col in update_cols},
    )
 
    with engine.begin() as conn:
        conn.execute(stmt)
 
    print(f" Upserted {len(records)} rows vào staging.{table}")
 
 
# HÀM CHÍNH
def run_transform():
    print("=" * 50)
    print("TRANSFORM PHASE")
    print("=" * 50)
 
    df_stock = transform_stock()
    upsert_to_staging(df_stock, "stock_prices", conflict_cols=["symbol", "date"])
 
    df_crypto = transform_crypto()
    upsert_to_staging(df_crypto, "crypto_prices", conflict_cols=["symbol", "date", "hour"])
 
    df_rates = transform_exchange_rates()
    upsert_to_staging(df_rates, "exchange_rates", conflict_cols=["base", "target", "date"])
 
    print("\n Transform phase complete!")
 
 
if __name__ == "__main__":
    run_transform()
