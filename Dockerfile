# Dùng Python 3.12
FROM python:3.12-slim

# Tạo thư mục làm việc trong container
WORKDIR / app
# Copy requirements trước (để cache layer)
COPY requirements.txt .

# Cài thư viện
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code vào container
COPY . .

# Lệnh chạy khi container start
CMD [ "python", "main.py" ]