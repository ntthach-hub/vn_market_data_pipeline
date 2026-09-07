import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, Table, MetaData
from sqlalchemy.dialects.postgresql import insert as pg_insert
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

# UPSERT VÀO RAW LAYER (thay cho load_to_raw + TRUNCATE cũ)
def upsert_to_raw(df: pd.DataFrame, table: str, conflict_cols: list):
    if df.empty:
        print(f"  Không có dòng mới cho raw.{table}, bỏ qua.")
        return

    # --- DEBUG: Kiểm tra dữ liệu trước khi insert ---
    print(f"  DEBUG - Columns: {df.columns.tolist()}")
    print(f"  DEBUG - Shape: {df.shape}")
    print(f"  DEBUG - First 2 rows:\n{df.head(2)}")
    
    # Chuyển đổi cột datetime thành string để SQLAlchemy xử lý đúng
    for col in df.select_dtypes(include=['datetime64']).columns:
        df[col] = df[col].astype(str)
    # --- HẾT DEBUG ---

    engine = get_engine()
    metadata = MetaData(schema="raw")
    tbl = Table(table, metadata, autoload_with=engine)

    records = df.to_dict(orient="records")
    
    # In ra bản ghi đầu tiên để kiểm tra
    if records:
        print(f"  DEBUG - First record keys: {list(records[0].keys())}")
        print(f"  DEBUG - First record values: {list(records[0].values())}")

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
    print(f"  Extracting stock: {symbol} from {start} to {end}...")
    stock = Vnstock().stock(symbol=symbol, source='VCI')
    df = stock.quote.history(start=start, end=end, interval='1D')

    # --- DEBUG ---
    print(f"  DEBUG - Columns: {df.columns.tolist()}")
    print(f"  DEBUG - First 2 rows:\n{df.head(2)}")
    # --- HẾT DEBUG ---

    # Tìm cột thời gian (có thể là 'time', 'Date', 'TradingDate', hoặc 'datetime')
    time_col = None
    for col in ['time', 'Date', 'TradingDate', 'datetime', 'trading_date']:
        if col in df.columns:
            time_col = col
            break
    
    if time_col is None:
        raise KeyError(f"Không tìm thấy cột thời gian. Các cột hiện có: {df.columns.tolist()}")
    
    # Đảm bảo cột thời gian là datetime và chỉ lấy phần ngày
    df['time'] = pd.to_datetime(df[time_col]).dt.normalize()
    
    # Xóa cột time cũ (nếu tên khác)
    if time_col != 'time':
        df = df.drop(columns=[time_col])

    # Thêm cột symbol và ingested_at
    df["symbol"] = symbol
    df["ingested_at"] = datetime.now()


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


    end_date = datetime.now().strftime("%Y-%m-%d")
    
 
    # Stock: chỉ fetch từ ngày cuối cùng đã có trong DB tới hiện tại.
    # Lần đầu (chưa có data) -> fallback lấy 365 ngày.
    for symbol in ["VNM", "VCB", "FPT"]:
        last_date = get_last_extracted_date("stock_prices", symbol, "time")
        if last_date:
            start_date = last_date.strftime("%Y-%m-%d")
        else:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
 
        df = extract_stock(symbol, start_date, end_date)
        upsert_to_raw(df, "stock_prices", conflict_cols=["symbol", "time"])
 
    # Crypto: CoinGecko luôn trả nguyên cửa sổ N ngày gần nhất,
    # upsert xử lý phần trùng lặp giúp mình.
    df = extract_crypto("BTC", "bitcoin", days=30)
    upsert_to_raw(df, "crypto_prices", conflict_cols=["symbol", "timestamp_ms"])
 
    df = extract_crypto("ETH", "ethereum", days=30)
    upsert_to_raw(df, "crypto_prices", conflict_cols=["symbol", "timestamp_ms"])
 
    # Exchange rate: API luôn trả tỉ giá tại thời điểm gọi.
    df = extract_exchange_rates("USD", ["VND", "EUR", "JPY"])
    upsert_to_raw(df, "exchange_rates", conflict_cols=["base", "target", "date"])
 
    print("\n Extract phase complete (incremental)!")
 

if __name__ == "__main__":
    run_extract()