# 🇻🇳 VN Market Data Pipeline

[![Status](https://img.shields.io/badge/Status-Completed-brightgreen.svg)](https://github.com/ntthach-hub/vn-market-data-pipeline)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue.svg)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-20.10+-blue.svg)](https://www.docker.com/)

**Batch ETL pipeline** thu thập dữ liệu thị trường Việt Nam (cổ phiếu, crypto, tỉ giá) và tổ chức vào PostgreSQL theo kiến trúc 3 layer.

---

## 🎯 Results

- **789** stock records (VNM, VCB, FPT)
- **1,442** crypto records (BTC, ETH)
- **851** daily summary records generated
- Các kiểm tra chất lượng được cấu hình đã passed ở lần chạy demo được ghi lại; chưa phải cam kết toàn bộ dữ liệu hợp lệ.

Các số lượng trên là kết quả demo được ghi lại trước đây, chưa được xác minh lại trong đợt review hiện tại.

---

## 🏗️ Architecture
```text
VNStock API ──┐
CoinGecko API ─┼──► Extract ──► RAW ──► Transform ──► STAGING ──► Load ──► ANALYTICS
ExchangeRate ──┘
Validate chạy sau Load và kiểm tra các bảng đã ghi.
```


**3 data sources → 3-layer PostgreSQL warehouse → automated quality checks**

- [ERD và grain/business key của 7 bảng](docs/data-model.md)
- [Data flow, thứ tự xử lý và giới hạn hiện tại](docs/data-flow.md)

Stock extraction có incremental theo ngày cuối mỗi symbol; Transform/Load hiện đọc và xử lý toàn bộ bảng. Project chưa có scheduler và chưa được xác nhận sẵn sàng vận hành production.

---

## 📊 Data Sources

| Source | Data | Volume |
|---|---|---|
| VNStock | VNM, VCB, FPT (daily) | ~264 rows/symbol/year |
| CoinGecko | BTC, ETH (hourly) | ~721 rows/coin/30 days |
| ExchangeRate-API | USD/VND, USD/EUR, USD/JPY | Latest rates |

---

## 🛠️ Tech Stack

`Python 3.12` · `PostgreSQL 15` · `Docker Compose` · `Pandas` · `SQLAlchemy`

---

## 🚀 Quickstart

### Prerequisites
- Docker Desktop (or Docker Engine + Compose)
- 4GB+ available RAM

### Run
```bash
git clone https://github.com/ntthach-hub/vn-market-data-pipeline.git
cd vn-market-data-pipeline
cp .env.example .env    # điền password
docker-compose up --build
```

### Kiểm thử hồi quy

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

Các test validation dùng mock và SQLite in-memory; không ghi vào PostgreSQL, không gọi API. Chúng không thay thế kiểm thử end-to-end với PostgreSQL thực tế.

📁 Project Structure
pipelines/
├── extract.py      # Pull data from 3 APIs
├── transform.py    # Clean, standardize, convert currency
├── load.py         # Aggregate to analytics layer
└── validate.py     # 4 automated quality checks
sql/
└── create_table.sql
main.py             # Run full pipeline: E → T → L → V

🗺️ Roadmap
☑ ETL Pipeline với 3 layers
☑ Docker containerization
☑ Automated validation (4 checks)
□ Apache Airflow (scheduling)
□ Kafka (streaming)
□ Streamlit dashboard

Author: ntthach-hub · LinkedIn
