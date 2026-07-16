import os
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
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


# CHECK 1: ĐẾM SỐ DÒNG MỖI BẢNG
def check_row_counts(conn):
    print("  [1] Kiểm tra số dòng...")

    tables = [
        ("raw", "stock_prices"),
        ("raw", "crypto_prices"),
        ("raw", "exchange_rates"),
        ("staging", "stock_prices"),
        ("staging", "crypto_prices"),
        ("staging", "exchange_rates"),
        ("analytics", "daily_market_summary"),
    ]

    for schema, table in tables:
        count = conn.execute(
            text(f"SELECT COUNT(*) FROM {schema}.{table}")
        ).scalar_one()
        print(f"     {schema}.{table}: {count} rows")

    print("   Row count check passed!")

# CHECK 2: KHÔNG CÓ NULL Ở CỘT QUAN TRỌNG
def check_nulls(conn):
    print("\n  [2] Kiểm tra NULL...")

    checks = [
        ("staging.stock_prices",  "symbol IS NULL OR date IS NULL OR close IS NULL"),
        ("staging.crypto_prices", "symbol IS NULL OR date IS NULL OR price_usd IS NULL"),
        ("staging.exchange_rates","base IS NULL OR target IS NULL OR rate IS NULL"),
        ("analytics.daily_market_summary", "symbol IS NULL OR date IS NULL OR close_price IS NULL"),
    ]

    for table, condition in checks:
        count = conn.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE {condition}")
        ).scalar_one()
        assert count == 0, f" {table} có {count} dòng NULL!"
        print(f"     {table}: không có NULL ")

    print("  Null check passed!")


# CHECK 3: GIÁ TRỊ HỢP LỆ
def check_valid_values(conn):
    print("\n  [3] Kiểm tra giá trị hợp lệ...")

    # Giá cổ phiếu phải > 0
    invalid_stock = conn.execute(text("""
        SELECT COUNT(*) FROM staging.stock_prices
        WHERE close <= 0 OR open <= 0 OR high <= 0 OR low <= 0
    """)).scalar_one()
    assert invalid_stock == 0, f" Stock có {invalid_stock} giá trị âm!"
    print("     Stock prices > 0 ")

    # Giá crypto phải > 0
    invalid_crypto = conn.execute(text("""
        SELECT COUNT(*) FROM staging.crypto_prices
        WHERE price_usd <= 0
    """)).scalar_one()
    assert invalid_crypto == 0, f" Crypto có {invalid_crypto} giá trị âm!"
    print("     Crypto prices > 0 ")

    # Tỉ giá phải > 0
    invalid_rate = conn.execute(text("""
        SELECT COUNT(*) FROM staging.exchange_rates
        WHERE rate <= 0
    """)).scalar_one()
    assert invalid_rate == 0, f" Exchange rate có {invalid_rate} giá trị âm!"
    print("     Exchange rates > 0 ")

    # Symbol cổ phiếu chỉ được là VNM, VCB, FPT
    invalid_symbol = conn.execute(text("""
        SELECT COUNT(*) FROM staging.stock_prices
        WHERE symbol NOT IN ('VNM', 'VCB', 'FPT')
    """)).scalar_one()
    assert invalid_symbol == 0, f" Có {invalid_symbol} symbol lạ!"
    print("     Stock symbols hợp lệ ")

    print(" Valid values check passed!")


# CHECK 4: SỐ DÒNG STAGING KHỚP VỚI RAW
def check_row_consistency(conn):
    print("\n  [4] Kiểm tra tính nhất quán...")

    raw_stock = conn.execute(
        text("SELECT COUNT(DISTINCT (symbol, time)) FROM raw.stock_prices")
    ).scalar_one()

    staging_stock = conn.execute(
        text("SELECT COUNT(*) FROM staging.stock_prices")
    ).scalar_one()

    assert staging_stock >= raw_stock * 0.95, \
        f" Staging stock ({staging_stock}) mất quá nhiều dòng so với raw ({raw_stock})!"
    print(f" Raw stock: {raw_stock} → Staging stock: {staging_stock} ")

    print(" Consistency check passed!")

# HÀM CHÍNH
def run_validate():
    print("=" * 50)
    print("VALIDATE PHASE")
    print("=" * 50)

    engine = get_engine()
    with engine.connect() as conn:
        check_row_counts(conn)
        check_nulls(conn)
        check_valid_values(conn)
        check_row_consistency(conn)

    print("\n Tất cả validate passed! Pipeline data is clean!")


if __name__ == "__main__":
    run_validate()