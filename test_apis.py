import requests
from vnstock import Vnstock

# TEST 1: VNSTOCK - Giá cổ phiếu VN
print("=" * 50)
print("TEST 1: VNSTOCK")
print("=" * 50)
stock = Vnstock().stock(symbol="VNM", source="VCI")
df_stock = stock.quote.history(
    start="2024-01-01",
    end="2024-12-31",
    interval="1D"
)
print(df_stock.head(3))
print("Shape:", df_stock.shape)
print("Columns:", df_stock.columns.tolist())

# TEST 2: COINGECKO - Giá crypto
print("\n" + "=" * 50)
print("TEST 2: COINGECKO")
print("=" * 50)

response = requests.get(
    "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
    params={"vs_currency": "usd", "days": "7"}
)
data = response.json()
prices = data["prices"][:3]
print("Sample prices (timestamp, price):")
for p in prices:
    print(p)

# TEST 3: EXCHANGE RATE - Tỉ giá USD/VND
print("\n" + "=" * 50)
print("TEST 3: EXCHANGE RATE")
print("=" * 50)

response = requests.get(
    "https://api.exchangerate-api.com/v4/latest/USD"
)
data = response.json()
print("USD -> VND:", data["rates"]["VND"])
print("USD -> EUR:", data["rates"]["EUR"])
print("Date:", data["date"])