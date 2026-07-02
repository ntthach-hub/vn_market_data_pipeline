-- tạo các schema
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS analytics;

-- RAW LAYER: Lưu data thô từ API
CREATE TABLE IF NOT EXISTS raw.stock_prices (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(10),
    time        DATE,
    open        NUMERIC,
    high        NUMERIC,
    low         NUMERIC,
    close       NUMERIC,
    volume      BIGINT,
    ingested_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw.crypto_prices (
    id              SERIAL PRIMARY KEY,
    symbol          VARCHAR(20),
    timestamp_ms    BIGINT,         -- timestamp gốc từ CoinGecko
    price_usd       NUMERIC,
    ingested_at     TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw.exchange_rates (
    id          SERIAL PRIMARY KEY,
    base        VARCHAR(10),        -- USD
    target      VARCHAR(10),        -- VND, EUR...
    rate        NUMERIC,
    date        DATE,
    ingested_at TIMESTAMP DEFAULT NOW()
);

-- STAGING LAYER: Data đã làm sạch
CREATE TABLE IF NOT EXISTS staging.stock_prices (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(10),
    date        DATE,
    open        NUMERIC,
    high        NUMERIC,
    low         NUMERIC,
    close       NUMERIC,
    volume      BIGINT,
    processed_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staging.crypto_prices (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(20),
    date        DATE,               -- convert từ timestamp_ms
    hour        INT,                -- giờ trong ngày
    price_usd   NUMERIC,
    price_vnd   NUMERIC,            -- quy đổi sang VND
    processed_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staging.exchange_rates (
    id          SERIAL PRIMARY KEY,
    base        VARCHAR(10),
    target      VARCHAR(10),
    rate        NUMERIC,
    date        DATE,
    processed_at TIMESTAMP DEFAULT NOW()
);

-- ANALYTICS LAYER: Data tổng hợp để phân tích

CREATE TABLE IF NOT EXISTS analytics.daily_market_summary (
    id              SERIAL PRIMARY KEY,
    date            DATE,
    symbol          VARCHAR(20),
    asset_type      VARCHAR(10),    -- 'stock' hoặc 'crypto'
    close_price     NUMERIC,
    close_price_vnd NUMERIC,        -- quy đổi sang VND
    volume          BIGINT,
    price_change_pct NUMERIC,       -- % thay đổi so với ngày trước
    created_at      TIMESTAMP DEFAULT NOW()
);