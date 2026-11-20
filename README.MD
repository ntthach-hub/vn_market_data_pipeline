# VN Market Data Pipeline

Batch ETL với Python, Pandas, SQLAlchemy, PostgreSQL 15 và Docker Compose. Pipeline nạp giá cổ phiếu Việt Nam, giá crypto và tỷ giá vào 7 bảng trong 3 schema.

```text
(OHLCV CSV hoặc Vnstock) + CoinGecko + ExchangeRate-API
    → Extract → raw → Transform → staging → Load → analytics → Validate
```

[ERD và khóa của 7 bảng](docs/data-model.md) · [Luồng dữ liệu, logic và giới hạn](docs/data-flow.md)

## Chạy với dữ liệu thật từ CSV và API

Đây là cách chạy chính cho người xem portfolio. Cổ phiếu lấy từ các file lịch sử đã tải về. BTC, ETH và tỷ giá USD/VND, USD/EUR, USD/JPY lấy qua API. Luồng này không cần mở tài khoản chứng khoán.

1. Mở Docker Desktop. Làm việc trong thư mục repo. Nếu chưa có `.env`, chạy `Copy-Item .env.example .env` trên PowerShell và điền `DB_PASSWORD`. Nếu đã chạy PostgreSQL trước đây, giữ cấu hình database hiện tại.
2. Tải CSV OHLCV cho FPT, VCB và VNM, ví dụ từ [trang tải CSV EasyStock](https://easystock.vn/easystock-download.html). Đặt tên file là `FPT.csv`, `VCB.csv` và `VNM.csv` trong `data/stocks/`. CSV cần có tiêu đề `Ticker,Date,Open,High,Low,Close,Volume`, ngày dạng `YYYY-MM-DD` và giá tính theo nghìn đồng. File tải về chỉ dùng cục bộ và được Git bỏ qua.
3. Kiểm tra `.env` có `STOCK_CSV_DIR=data/stocks`, rồi chạy:

```powershell
docker compose up -d --wait postgres
docker compose run --rm --build pipeline
```

Lượt chạy này ghi vào `vn_market_db`, database kết nối từ pgAdmin qua `localhost:5434` theo cấu hình mặc định. Log đầu lượt hiện database đích. Khi thấy `Pipeline complete`, chạy truy vấn dưới đây trong Query Tool của `vn_market_db` để lấy kết quả mới:

```sql
SELECT asset_type, symbol, COUNT(*) AS rows,
       MIN(date) AS first_date, MAX(date) AS last_date
FROM analytics.daily_market_summary
GROUP BY asset_type, symbol
ORDER BY asset_type, symbol;
```

Lưu nguồn CSV, khoảng ngày và log của lượt chạy. Khi có snapshot mới, thay CSV rồi chạy lại. UPSERT cập nhật giá của các ngày trùng khóa, nên giữ cùng nguồn và quy ước giá giữa các lần nạp.

## Kiểm tra và trạng thái

Ngày 20/11/2026, luồng CSV kết hợp API chạy thành công hai lần trong dự án Compose kiểm thử riêng `vietnam-stock-verify`. Kết quả dưới đây thuộc database của lượt kiểm thử.

| Đầu ra | Lượt 1 | Lượt 2 |
|---|---:|---:|
| Giá cổ phiếu trong raw và staging | 747 | 747 |
| Quan sát crypto trong raw | 1.442 | 1.443 |
| Bản ghi crypto theo giờ trong staging | 1.440 | 1.440 |
| Cặp tỷ giá trong raw và staging | 3 | 3 |
| Dòng tổng hợp trong analytics | 809 | 809 |

Giá cổ phiếu có 249 dòng mỗi mã, từ 20/11/2025 đến 20/11/2026. Analytics có 62 dòng crypto theo ngày cho BTC và ETH. Sau lượt hai, truy vấn PostgreSQL trả về 0 khóa `(date, symbol)` trùng trong analytics. API trả thêm một timestamp crypto ở lượt hai, còn số dòng theo giờ và theo ngày giữ nguyên.

- Bộ test hồi quy kiểm tra một số hành vi của Extract và Validate bằng mock/SQLite, không gọi API thật. Chạy `python -m pytest tests -q` sau khi cài `requirements-dev.txt`.
- Kết quả bản gốc nằm trong [nhật ký phát triển](docs/development%20log.md).
- Nhánh Open API lấy cổ phiếu qua Vnstock 6 vẫn cần khóa để xác minh.

<details>
<summary>Tùy chọn lấy cổ phiếu qua Open API</summary>

**Lấy cổ phiếu qua Open API.** Để `STOCK_CSV_DIR` trống, chọn `VNSTOCK_SOURCE` và điền khóa của nguồn đã có quyền truy cập. Nguồn được cấu hình trong code gồm SSI, DNSE, FHSC và TCBS. TCBS cần phiên OTP. Nhánh này lấy cổ phiếu từ ngày mới nhất đã lưu theo từng mã. Transform và Load vẫn xử lý toàn bảng. [Cách thiết lập khóa Vnstock 6](https://vnstocks.com/docs/vnstock/v6/cai-dat)

</details>
