from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_superadmin_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏪 Barcha do'konlar"), KeyboardButton(text="➕ Yangi do'kon qo'shish")],
            [KeyboardButton(text="📊 Platforma statistikasi"), KeyboardButton(text="🔙 Asosiy menyu")]
        ],
        resize_keyboard=True
    )

def get_shops_list_kb(shops: list, filter_type: str = "all") -> InlineKeyboardMarkup:
    inline_keyboard = []
    
    # 1. Filter tanlash tugmalari
    filter_buttons = [
        InlineKeyboardButton(
            text="🟢 Faol (Top)" if filter_type != "active" else "• 🟢 Faol •", 
            callback_data="sa_filter_active"
        ),
        InlineKeyboardButton(
            text="🔴 Passiv (0)" if filter_type != "passive" else "• 🔴 Passiv •", 
            callback_data="sa_filter_passive"
        ),
    ]
    filter_buttons2 = [
        InlineKeyboardButton(
            text="⏳ Oz qolgan" if filter_type != "expiring" else "• ⏳ Oz qolgan •", 
            callback_data="sa_filter_expiring"
        ),
        InlineKeyboardButton(
            text="📋 Barchasi" if filter_type != "all" else "• 📋 Barchasi •", 
            callback_data="sa_filter_all"
        ),
    ]
    inline_keyboard.append(filter_buttons)
    inline_keyboard.append(filter_buttons2)
    
    # 2. Do'konlar ro'yxati
    for s in shops:
        c_count = s.get('customers_count', 0)
        days = s.get('days_left', 30)
        days = days if days is not None else 30
        
        # Holat belgisi
        if not s['is_active']:
            status_icon = "⛔️"
        elif c_count > 0:
            status_icon = "🟢"
        else:
            status_icon = "🔴"
            
        btn_text = f"{status_icon} {s['name']} (👥 {c_count} | ⏳ {days}k)"
        inline_keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"sa_shop_{s['id']}")])
        
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

def get_shop_manage_kb(shop_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Bloklash" if is_active else "🟢 Faollashtirish"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ 1 oy (+30)", callback_data=f"sa_ext_{shop_id}_30"),
                InlineKeyboardButton(text="➕ 3 oy (+90)", callback_data=f"sa_ext_{shop_id}_90"),
            ],
            [
                InlineKeyboardButton(text="➕ 1 yil (+365 kun)", callback_data=f"sa_ext_{shop_id}_365"),
                InlineKeyboardButton(text="🔄 Adminni o'zgartirish", callback_data=f"sa_chadmin_{shop_id}")
            ],
            [InlineKeyboardButton(text=toggle_text, callback_data=f"sa_toggle_{shop_id}")],
            [InlineKeyboardButton(text="🗑 Do'konni o'chirish", callback_data=f"sa_del_{shop_id}")],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="sa_back_shops")]
        ]
    )
