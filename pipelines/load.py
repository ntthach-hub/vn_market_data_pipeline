import os
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, Table, MetaData
from sqlalchemy.dialects.postgresql import insert as pg_insert
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

# UPSERT VÀO ANALYTICS LAYER (thay cho TRUNCATE + append)
def load_to_analytics(df: pd.DataFrame, conflict_cols=["date", "symbol"]):
    if df.empty:
        print("  Không có dòng nào để load vào analytics.daily_market_summary")
        return
 
    engine = get_engine()
    metadata = MetaData(schema="analytics")
    tbl = Table("daily_market_summary", metadata, autoload_with=engine)
 
    records = df.to_dict(orient="records")
 
    # created_at bị loại khỏi update_cols -> row cũ giữ nguyên created_at
    # gốc, chỉ các cột số liệu (close_price, volume, price_change_pct...)
    # được cập nhật giá trị mới.
    update_cols = {
        c.name: c
        for c in tbl.columns
        if c.name not in conflict_cols and c.name  not in ("id", "created_at")
    }
 
    stmt = pg_insert(tbl).values(records)
    stmt = stmt.on_conflict_do_update(
        index_elements=conflict_cols,
        set_={col: getattr(stmt.excluded, col) for col in update_cols},
    )
 
    with engine.begin() as conn:
        conn.execute(stmt)
 
    print(f"  Upserted {len(records)} rows vào analytics.daily_market_summary")
 
 

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