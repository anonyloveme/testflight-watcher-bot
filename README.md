# 🔍 TestFlight Watcher Bot

Bot Telegram theo dõi slot beta TestFlight tự động.
Nhận thông báo ngay khi có slot trống!

## ✨ Tính năng
- Theo dõi nhiều app TestFlight cùng lúc
- Thông báo realtime khi slot mở/đóng
- Danh sách app phổ biến để theo dõi nhanh
- Auto unwatch sau khi slot mở
- Web dashboard xem trạng thái
- Thống kê app được theo dõi nhiều nhất

## 🤖 Sử dụng Bot
Link: https://t.me/testflightchecker888bot

Các lệnh:
- /start - Khởi động bot
- /help  - Hướng dẫn sử dụng

## 🛠 Tự deploy

### Yêu cầu
- Python 3.11+
- Telegram Bot Token từ @BotFather

### Chạy local
# Clone repo
git clone https://github.com/anonyloveme/testflight-watcher-bot
cd testflight-watcher-bot

# Tạo môi trường ảo
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Cài thư viện
pip install -r requirements.txt

# Tạo file .env từ mẫu
cp .env.example .env
# Điền thông tin vào .env

# Chạy
python app.py

### Deploy Render
(hướng dẫn các bước bên dưới)

## 📊 Web Dashboard
Sau khi deploy, truy cập:
- / → Dashboard tổng quan
- /apps → Danh sách tất cả app
- /health → Health check
- /api/stats → API thống kê
- /api/apps → API danh sách app

## 📝 License
MIT
