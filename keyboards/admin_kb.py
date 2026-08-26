from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def format_money(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ") + " so'm"

def get_admin_main_kb(is_superadmin: bool = False, days_left: int = 30) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="📋 Mijozlar ro'yxati"), KeyboardButton(text="➕ Yangi mijoz")],
        [KeyboardButton(text="🔍 Qidirish"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="📲 Do'kon QR kodi"), KeyboardButton(text="👥 Sheriklar (Adminlar)")],
        [KeyboardButton(text="⚙️ Do'kon nomi"), KeyboardButton(text=f"⏳ Obuna: {days_left} kun qoldi")],
    ]
    if is_superadmin:
        buttons.append([KeyboardButton(text="👑 Super Admin Paneli")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_contact_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Telefon raqamni ulashish", request_contact=True)],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_open_store_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏪 O'z do'konimni ochish (30 kun BEPUL)", callback_data="start_open_my_store")]
        ]
    )

def get_staff_list_kb(staff_list: list, can_add: bool = True) -> InlineKeyboardMarkup:
    rows = []
    for s in staff_list:
        role_label = "👑 Asosiy ega" if s['role'] == 'owner' else "👤 Sherik"
        text = f"{role_label}: {s['name'] or 'Ismsiz'} (ID: {s['telegram_id']})"
        if s['role'] == 'staff':
            rows.append([
                InlineKeyboardButton(text=text, callback_data="none"),
                InlineKeyboardButton(text="❌ O'chirish", callback_data=f"del_staff_{s['id']}")
            ])
        else:
            rows.append([InlineKeyboardButton(text=text, callback_data="none")])
            
    if can_add:
        rows.append([InlineKeyboardButton(text="➕ Yangi sherik qo'shish", callback_data="add_new_staff")])
    rows.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_add_customer_menu_kb(bot_username: str, shop_id: int) -> InlineKeyboardMarkup:
    from urllib.parse import quote
    shop_link = f"https://t.me/{bot_username}?start=shop_{shop_id}"
    share_url = f"https://t.me/share/url?url={quote(shop_link)}&text={quote('Assalomu alaykum! Do‘konimizdagi qarz daftari va xaridlar tarixingizni kuzatib borish uchun ushbu botga kiring:')}"
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Qo'lda kiritish (Ism, Telefon)", callback_data="manual_add_cust")],
            [InlineKeyboardButton(text="📤 Havolani Telegramdan yuborish", url=share_url)],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_main")]
        ]
    )

def get_stats_period_kb(current_period: str = 'all') -> InlineKeyboardMarkup:
    periods = [
        ("today", "📅 Bugun"),
        ("week", "🗓 Shu hafta"),
        ("month", "📆 Shu oy"),
        ("all", "📊 Barchasi")
    ]
    buttons = []
    row = []
    for code, label in periods:
        text = f"✅ {label}" if code == current_period else label
        row.append(InlineKeyboardButton(text=text, callback_data=f"stat_{code}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

def get_customer_actions_kb(customer_id: int, bot_username: str, shop_id: int, phone: str = None) -> InlineKeyboardMarkup:
    from urllib.parse import quote
    # Har bir mijoz uchun shaxsiy hisob havolasi (start=c_ID)
    customer_link = f"https://t.me/{bot_username}?start=c_{customer_id}"
    share_url = f"https://t.me/share/url?url={quote(customer_link)}&text={quote('Assalomu alaykum! Do‘konimizdagi qarz daftari va xaridlar tarixingizni kuzatib borish uchun ushbu havolani bosing:')}"
    
    rows = [
        [
            InlineKeyboardButton(text="➕ Qarz yozish", callback_data=f"debt_{customer_id}"),
            InlineKeyboardButton(text="➖ To'lov olish", callback_data=f"pay_{customer_id}")
        ],
        [
            InlineKeyboardButton(text="📜 Qarz tarixi", callback_data=f"history_{customer_id}"),
            InlineKeyboardButton(text="📤 Taklif yuborish", url=share_url)
        ]
    ]
    
    if phone:
        # Telefon raqamdan belgilarni tozalash
        clean_phone = "".join([c for c in phone if c.isdigit()])
        if clean_phone:
            rows.append([InlineKeyboardButton(text="💬 Mijoz Telegramiga o'tish", url=f"https://t.me/+{clean_phone}")])
            
    rows.append([
        InlineKeyboardButton(text="🗑 Mijozni o'chirish", callback_data=f"del_cust_{customer_id}"),
        InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_list")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_customers_list_kb(customers: list, page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
    inline_keyboard = []
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_items = customers[start_idx:end_idx]
    
    for c in page_items:
        balance_str = format_money(c['balance'])
        btn_text = f"👤 {c['full_name']} — {balance_str}"
        inline_keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"view_cust_{c['id']}")])
        
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"page_{page-1}"))
    if end_idx < len(customers):
        nav_buttons.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"page_{page+1}"))
    
    if nav_buttons:
        inline_keyboard.append(nav_buttons)
        
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
