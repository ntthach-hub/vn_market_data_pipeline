# Development Log — VN Market Data Pipeline

Nhật ký này lưu các mốc phát triển cũ. Xem [README](../README.MD) để chạy phiên bản hiện tại và [data flow](data-flow.md) để biết phạm vi incremental.

Bản gốc được kiểm tra lại ở trạng thái trước khi nạp CSV. Bảng analytics có 851 dòng, gồm 789 dòng cổ phiếu và 62 dòng crypto, đến 07/09/2026. Truy vấn theo khóa `(date, symbol)` trả về 0 dòng trùng.

Ghi lại quá trình làm, những thứ đã sửa, đã bỏ và lý do tại sao.

---

## Giai đoạn 1 — Setup & Extract

### Đã làm
- Tạo cấu trúc project với các folder: `pipelines/`, `sql/`, `producers/`, `consumers/`, `spark_jobs/`, `dags/`, `docs/`
- Tạo database `vn_market_db` với 3 schema: `raw`, `staging`, `analytics`
- Test kết nối 3 nguồn API: VNStock, CoinGecko, ExchangeRate-API
- Viết `extract.py` — kéo data từ 3 API, load vào raw layer

### Vấn đề gặp
| Vấn đề | Nguyên nhân | Fix |
|---|---|---|
| `cannot import stock_historical_data` | vnstock đổi API mới | Dùng `Vnstock().stock()` |
| `could not translate host name` | Password có `@` làm hỏng URL | Dùng `quote_plus()` |
| `password authentication failed` | Sai user/password trong `.env` | Kiểm tra `.env` không có space xung quanh `=` |
| `get_engine not defined` | Hàm đặt sai chỗ | Đưa ra ngoài cùng |

---

## Giai đoạn 2 — Transform & Load

### Đã làm
- Viết `transform.py`:
  - Đổi tên cột `time` → `date`
  - Convert `timestamp_ms` → `date` + `hour`
  - Tính `price_vnd` = `price_usd` × tỉ giá
  - Xóa duplicate bằng `drop_duplicates()`
- Viết `load.py`:
  - Gộp stock + crypto
  - Tính `price_change_pct` (% thay đổi so với ngày trước)
  - Load vào `analytics.daily_market_summary`

### Vấn đề gặp
| Vấn đề | Nguyên nhân | Fix |
|---|---|---|
| `TypeError: Cannot compare Timestamp with datetime.date` | 2 DataFrame có kiểu date khác nhau khi concat | Convert cả 2 về `pd.to_datetime()` trước khi gộp |
| Duplicate data mỗi lần chạy | `if_exists='append'` không xóa data cũ | TRUNCATE trước khi insert |
| Chỉ còn FPT trong raw | TRUNCATE nằm trong vòng lặp → xóa sau mỗi symbol | Chuyển TRUNCATE lên TRƯỚC vòng lặp |

---

## Giai đoạn 3 — Validate

### Đã làm
- Viết `validate.py` với 4 check tự động:
  1. Đếm số dòng mỗi bảng
  2. Kiểm tra NULL ở cột quan trọng
  3. Kiểm tra giá trị hợp lệ (giá > 0, symbol đúng)
  4. Kiểm tra tính nhất quán raw vs staging
- Thêm `run_validate()` vào `main.py`

---

## Giai đoạn 4 — Docker

### Đã làm
- Tạo `Dockerfile` — đóng gói pipeline vào container Python 3.12
- Tạo `docker-compose.yml` — orchestrate PostgreSQL + pipeline
- Tạo `.env.example` — template cho người khác khi clone về
- Thêm UNIQUE constraint vào `create_table.sql` để tránh duplicate

### Vấn đề gặp
| Vấn đề | Nguyên nhân | Fix |
|---|---|---|
| `port 5433 already allocated` | Port đang bị dùng | Đổi sang port 5434 |
| `POSTGRES_PASSWORD not set` | Thiếu biến trong `.env` | Thêm `POSTGRES_PASSWORD` vào `.env` |
| `schema "raw" does not exist` | Volume cũ → PostgreSQL bỏ qua init script | `docker-compose down -v` rồi up lại |

---
## Giai đoạn 5 — Fix lỗi ON CONFLICT & UNIQUE Constraint

### Vấn đề
Pipeline chạy extract thành công nhưng bị lỗi khi transform: psycopg2.errors.InvalidColumnReference: there is no unique or exclusion constraint matching the ON CONFLICT specification

### Nguyên nhân
- File `sql/create_table.sql` đã định nghĩa UNIQUE constraint nhưng chưa được áp dụng vào database.
- PostgreSQL bỏ qua file init.sql vì volume đã có dữ liệu từ lần chạy trước: PostgreSQL Database directory appears to contain a database; Skipping initialization

### ⚠️ Quan trọng: Phân biệt môi trường

**Trong Development (khi đang xây dựng):**
- Có thể xóa sạch và khởi tạo lại vì dữ liệu chưa quan trọng.
- Cách này nhanh nhưng KHÔNG dùng được trong production.

**Trong Production (khi hệ thống đã chạy thật):**
- Tuyệt đối không xóa volume hay down -v vì sẽ mất dữ liệu.
- Phải dùng migration (ALTER TABLE) để thay đổi schema mà không làm mất dữ liệu.

### Các cách fix đã thử

| Cách thử | Kết quả | Áp dụng cho |
|---|---|---|
| Sửa file `create_table.sql` rồi chạy lại `docker-compose up` | ❌ Không được (Postgres bỏ qua init.sql) | Dev |
| `docker-compose down -v` rồi chạy lại | ❌ Vẫn lỗi (volume chưa xóa hết) | Dev |
| `docker volume rm vietnamstock_postgres_data` | ✅ Xóa sạch volume cũ | Dev |

### Cách fix CUỐI CÙNG (đã áp dụng)

**Cách 1 (Migration - DÙNG CHO PRODUCTION):**
Không xóa dữ liệu, chỉ thêm constraint bằng migration:
```sql
ALTER TABLE staging.stock_prices ADD CONSTRAINT uq_staging_stock_symbol_date UNIQUE (symbol, date);
ALTER TABLE staging.crypto_prices ADD CONSTRAINT uq_staging_crypto_symbol_date_hour UNIQUE (symbol, date, hour);
ALTER TABLE staging.exchange_rates ADD CONSTRAINT uq_staging_fx_base_target_date UNIQUE (base, target, date);
```

Cách 2 (Xóa sạch - CHỈ DÙNG CHO DEVELOPMENT):
docker-compose down -v
docker volume rm vietnamstock_postgres_data
docker-compose up --build

## Bài học rút ra cho production
Luôn dùng migration (ALTER TABLE) khi cần thay đổi schema.

Không xóa dữ liệu để fix lỗi trong production.

File init.sql chỉ chạy 1 lần khi container được tạo lần đầu.

Sau này khi dùng Airflow, sẽ có migration pipeline riêng để quản lý schema thay đổi một cách an toàn.

## Kết quả
✅ Pipeline chạy thành công với tất cả 4 phases: Extract → Transform → Load → Validate
✅ Data được lưu đầy đủ trong cả 3 layers: raw (789), staging (789), analytics (851)


---

## 🎯 LÝ DO THAY ĐỔI

| Trước đây | Sau khi sửa |
|---|---|
| Chỉ nêu cách xóa sạch | ✅ Phân biệt rõ Dev vs Prod |
| Không giải thích lý do | ✅ Giải thích tại sao chỉ dùng trong dev |
| Không đề cập migration | ✅ Thêm migration (`ALTER TABLE`) là cách đúng cho prod |
| Thiếu bài học rút ra | ✅ Thêm bài học về quản lý schema trong production |

---

## 💡 TƯ DUY ĐÚNG CỦA DATA ENGINEER

1. **Development:** Thoải mái thử nghiệm, xóa sạch, làm lại → dùng `down -v`
2. **Production:** Không được mất dữ liệu → dùng `ALTER TABLE`, `migration scripts`, `blue-green deployment`
3. **File init.sql:** Chỉ dùng để khởi tạo database **lần đầu**, không phải để update schema.

---
## Những thứ đã bỏ và lý do

### Kafka
**Đã làm:** Thêm Zookeeper + Kafka vào `docker-compose.yml`, tạo folder `producers/` và `consumers/`

**Lý do bỏ:** Data từ API là batch (theo ngày), không phải streaming — Kafka không có ý nghĩa thực tế với data nhỏ như vậy. Sẽ thêm lại khi có nguồn data streaming thật sự.

### Spark
**Đã làm:** Tạo folder `spark_jobs/`

**Lý do bỏ:** Data hiện tại chỉ ~1700 rows — dùng Spark giống như dùng xe tải chở 1 túi gạo. Pandas đủ dùng cho scale này.

### HDFS
**Không làm:** Data không đủ lớn để cần distributed storage.

### Airflow
**Chưa làm:** Sẽ thêm trong giai đoạn tiếp theo — schedule pipeline chạy mỗi ngày tự động.

---

## Bài học rút ra

### Về kỹ thuật
- Password có ký tự đặc biệt trong URL → luôn dùng `quote_plus()`
- TRUNCATE phải đặt TRƯỚC vòng lặp, không đặt bên trong
- Docker container phụ thuộc nhau → dùng `healthcheck` + `depends_on`
- PostgreSQL lưu tên cột lowercase → không dùng ngoặc kép `"Age"` trong SQL

### Về thiết kế
- Không nên thêm công nghệ phức tạp (Kafka, Spark) khi data nhỏ — interviewer sẽ hỏi lý do và bạn không trả lời được
- TRUNCATE phù hợp cho demo/học, UPSERT (`ON CONFLICT`) phù hợp cho production
- 3-layer architecture (raw/staging/analytics) là pattern chuẩn — giữ nguyên dù tech stack thay đổi

### Về workflow
- Push GitHub thường xuyên — tránh mất code
- Ghi lại lỗi và cách fix ngay khi gặp — không cần nhớ lại sau
- Test từng bước nhỏ trước khi ghép lại — dễ tìm lỗi hơn

---

## Kết luận cuối cùng

### Những gì đã hoàn thành
1. ✅ ETL Pipeline batch hoàn chỉnh với 3 layers (Raw → Staging → Analytics)
2. ✅ Incremental loading để tối ưu thời gian
3. ✅ UPSERT với ON CONFLICT để tránh duplicate
4. ✅ Data validation với 4 automated checks
5. ✅ Containerization với Docker
6. ✅ Documentation đầy đủ (README, Journal)
7. ✅ Sẵn sàng để showcase trong CV

### Những gì sẽ làm tiếp
- ⬜ Airflow để schedule pipeline chạy tự động
- ⬜ Dashboard (Power BI / Streamlit) để visualize dữ liệu
- ⬜ Unit tests cho các hàm ETL
- ⬜ Project streaming với Kafka (bài toán thứ 2)

---
