from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_superadmin_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏪 Barcha do'konlar"), KeyboardButton(text="➕ Yangi do'kon qo'shish")],
            [KeyboardButton(text="📊 Platforma statistikasi"), KeyboardButton(text="🔙 Asosiy menyu")]
        ],
        resize_keyboard=True
    )

def get_shops_list_kb(shops: list) -> InlineKeyboardMarkup:
    inline_keyboard = []
    for s in shops:
        status_icon = "🟢" if s['is_active'] else "🔴"
        btn_text = f"{status_icon} {s['name']} (ID: {s['id']})"
        inline_keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"sa_shop_{s['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

def get_shop_manage_kb(shop_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Bloklash" if is_active else "🟢 Faollashtirish"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ 1 oy (+30 kun)", callback_data=f"sa_ext_{shop_id}_30"),
                InlineKeyboardButton(text="➕ 3 oy (+90 kun)", callback_data=f"sa_ext_{shop_id}_90")
            ],
            [
                InlineKeyboardButton(text="➕ 1 yil (+365 kun)", callback_data=f"sa_ext_{shop_id}_365")
            ],
            [InlineKeyboardButton(text=toggle_text, callback_data=f"sa_toggle_{shop_id}")],
            [InlineKeyboardButton(text="🗑 Do'konni o'chirish", callback_data=f"sa_del_{shop_id}")],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="sa_back_shops")]
        ]
    )
