from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_client_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💳 Mening qarzlarim")],
            [KeyboardButton(text="📜 Xaridlar tarixi"), KeyboardButton(text="🔄 Yangilash")],
            [KeyboardButton(text="📲 Ekranga znachok qilish")]
        ],
        resize_keyboard=True
    )
