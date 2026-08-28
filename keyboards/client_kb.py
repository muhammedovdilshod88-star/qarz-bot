from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_client_main_kb(has_own_shop: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="💳 Qayerda qancha qarzim bor?")],
        [KeyboardButton(text="📜 Xaridlarim tarixi"), KeyboardButton(text="🔄 Yangilash")]
    ]
    if has_own_shop:
        buttons.append([KeyboardButton(text="🏪 Mening do'konim (Do'konchi rejimi)")])
    buttons.append([KeyboardButton(text="📲 Ekranga znachok qilish")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
