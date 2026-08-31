import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN", "8436067790:AAFG6ENO7k5o3WgxwNvAaMx8xz6DmmAG-zU")

# PostgreSQL Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://qarz_db_6s8b_user:cseRxemuwWUHSWBtHiGF7btSfahr4ZWe@dpg-da832qqd0e5s73a5ulgg-a/qarz_db_6s8b")

# Admin va to'lov rekvizitlari
CARD_NUMBER = "5614 6816 2779 4484"
CARD_HOLDER = "Dilshod M"
ADMIN_USERNAME = "DilshodMuhammad00"

# Super Admin ID lari (Sizning Telegram ID ingiz)
SUPER_ADMIN_IDS = list(set([8976731089] + [int(i) for i in os.getenv("SUPER_ADMIN_IDS", "").split(",") if i.strip()]))

# Baza fayli joylashuvi
DB_PATH = os.path.join(os.path.dirname(__file__), "qarz_daftari.db")
