"""Manual smoke test for the three live sources without writing to PostgreSQL."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pipelines.extract import extract_crypto, extract_exchange_rates, extract_stock


def main():
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    start = (today - timedelta(days=7)).isoformat()
    print(extract_stock("VNM", start, today.isoformat()).head(3))
    print(extract_crypto("BTC", "bitcoin", days=7).head(3))
    print(extract_exchange_rates().head(3))


if __name__ == "__main__":
    main()
