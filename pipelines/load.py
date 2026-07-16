import os
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine ,text
from urllib.parse import quote_plus

load_dotenv()

# Ket noi database
def get_engine():
    user = os.getenv('DB_USER')
    password = quote_plus(os.getenv('DB_PASSWORD'))
    host = os.getenv('DB_HOST')
    port = os.getenv('DB_PORT')
    dbname = os.getenv('DB_NAME')
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
    return create_engine(url)

# BUILD ANALYTICS: DAILY MARKET SUMMARY
def build_daily_summary() -> pd.DataFrame:
    print("  Building daily market summary...")
    engine = get_engine()

    # Lấy tỉ giá USD/VND mới nhất
    df_rates = pd.read_sql(
        "SELECT rate FROM staging.exchange_rates WHERE target = 'VND' ORDER BY date DESC LIMIT 1",
        con=engine
    )
    usd_vnd = df_rates["rate"].iloc[0]

    # --- STOCK DATA ---
    df_stock = pd.read_sql("""
        SELECT
            date,
            symbol,
            'stock'     AS asset_type,
            close       AS close_price,
            volume
        FROM staging.stock_prices
    """, con=engine)

    df_stock["close_price_vnd"] = df_stock["close_price"] * 1000
    df_stock["date"] = pd.to_datetime(df_stock["date"])  # ← thêm dòng này

    # --- CRYPTO DATA ---
    df_crypto = pd.read_sql("""
        SELECT
            date,
            symbol,
            'crypto'        AS asset_type,
            AVG(price_usd)  AS close_price,
            NULL            AS volume
        FROM staging.crypto_prices
        GROUP BY date, symbol
    """, con=engine)

    df_crypto["close_price_vnd"] = df_crypto["close_price"] * usd_vnd
    df_crypto["date"] = pd.to_datetime(df_crypto["date"]) 

    # --- GỘP LẠI ---
    df = pd.concat([df_stock, df_crypto], ignore_index=True)
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)

    # --- TÍNH % THAY ĐỔI GIÁ SO VỚI NGÀY TRƯỚC ---
    df["price_change_pct"] = (
        df.groupby("symbol")["close_price"]
        .pct_change() * 100
    ).round(2)

    df["created_at"] = datetime.now()

    print(f" Daily summary: {len(df)} rows")
    return df

# LOAD VÀO ANALYTICS LAYER
def load_to_analytics(df: pd.DataFrame):
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE analytics.daily_market_summary"))
        conn.commit()    
    df.to_sql(
        "daily_market_summary",
        schema="analytics",
        con=engine,
        if_exists="append",
        index=False
    )
    print(f"  Loaded {len(df)} rows to analytics.daily_market_summary")


# HÀM CHÍNH
def run_load():
    print("=" * 50)
    print("LOAD PHASE")
    print("=" * 50)

    df = build_daily_summary()
    load_to_analytics(df)

    print("\n Load phase complete!")


if __name__ == "__main__":
    run_load()