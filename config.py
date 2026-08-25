import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN", "8436067790:AAFG6ENO7k5o3WgxwNvAaMx8xz6DmmAG-zU")

# Super Admin ID lari (Sizning Telegram ID ingiz)
# Masalan: [123456789]
SUPER_ADMIN_IDS = [int(i) for i in os.getenv("SUPER_ADMIN_IDS", "").split(",") if i.strip()]

# Baza fayli joylashuvi
DB_PATH = os.path.join(os.path.dirname(__file__), "qarz_daftari.db")
