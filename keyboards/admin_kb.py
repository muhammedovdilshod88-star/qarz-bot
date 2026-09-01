from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import config

def format_money(amount: float, currency: str = 'UZS') -> str:
    if not amount:
        amount = 0.0
    if currency == 'USD':
        val_str = f"{amount:,.2f}".replace(",", " ")
        if val_str.endswith(".00"):
            val_str = val_str[:-3]
        return f"{val_str} $"
    return f"{amount:,.0f}".replace(",", " ") + " so'm"

def get_currency_select_kb(action: str, customer_id: int) -> InlineKeyboardMarkup:
    """action: 'debt' or 'pay'"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇿 SO'M (UZS)", callback_data=f"curr_{action}_{customer_id}_UZS"),
                InlineKeyboardButton(text="🇺🇸 DOLLAR ($)", callback_data=f"curr_{action}_{customer_id}_USD")
            ],
            [
                InlineKeyboardButton(text="🔙 Bekor qilish", callback_data=f"view_cust_{customer_id}")
            ]
        ]
    )

def get_admin_main_kb(is_superadmin: bool = False, days_left: int = 30, ledger_type: str = 'receivable') -> ReplyKeyboardMarkup:
    if ledger_type == 'payable':
        # 🔴 MENING QARZLARIM REJIMI (Men berishim kerak bo'lgan qarzlar - Shaxsiy)
        tabs_row = [
            KeyboardButton(text="🟢 Olishim kerak 🔄"),
            KeyboardButton(text="🔴 BERISHIM KERAK (Faol ✅)")
        ]
        list_btn = KeyboardButton(text="📋 Haqdorlar (Qarz beruvchilar)")
        add_btn = KeyboardButton(text="➕ Yangi qarz olish")
        buttons = [
            tabs_row,
            [list_btn, add_btn],
            [KeyboardButton(text="🔍 Qidirish"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="📥 Excel hisoboti"), KeyboardButton(text="⚙️ Daftar nomi")],
            [KeyboardButton(text=f"⏳ Obuna: {days_left} kun qoldi"), KeyboardButton(text="📲 Ekranga znachok")],
        ]
    else:
        # 🟢 MENGA QARZLAR REJIMI (Menga qaytarishi kerak bo'lgan qarzlar - Do'kon/Daftar)
        tabs_row = [
            KeyboardButton(text="🟢 MENGA QARZLAR (Faol ✅)"),
            KeyboardButton(text="🔴 Berishim kerak 🔄")
        ]
        list_btn = KeyboardButton(text="📋 Qarzdorlar ro'yxati")
        add_btn = KeyboardButton(text="➕ Yangi qo'shish")
        buttons = [
            tabs_row,
            [list_btn, add_btn],
            [KeyboardButton(text="🔍 Qidirish"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="📥 Excel hisoboti"), KeyboardButton(text="📲 Ulanish QR kodi")],
            [KeyboardButton(text="👥 Sheriklar (Adminlar)"), KeyboardButton(text="⚙️ Daftar nomi")],
            [KeyboardButton(text=f"⏳ Obuna: {days_left} kun qoldi"), KeyboardButton(text="📲 Ekranga znachok")],
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

def get_subscription_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 To'lov chekini yuborish", url=f"https://t.me/{config.ADMIN_USERNAME}")],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_main")]
        ]
    )

def get_open_store_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📒 Yangi Qarz Daftarimni ochish (30 kun BEPUL)", callback_data="start_open_my_store")],
            [InlineKeyboardButton(text="🔐 Daftarni tiklash (Telefon orqali)", callback_data="start_recover_my_store")]
        ]
    )

def get_phone_input_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏩ Raqamsiz davom etish")],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_desc_input_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏩ Izohsiz saqlash")],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_recovery_contact_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Telefon raqamni yuborish (Tiklash)", request_contact=True)],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
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

def get_due_date_select_kb(customer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⏳ 3 kun", callback_data=f"setdue_{customer_id}_3"),
                InlineKeyboardButton(text="⏳ 7 kun (1 hafta)", callback_data=f"setdue_{customer_id}_7"),
            ],
            [
                InlineKeyboardButton(text="⏳ 15 kun", callback_data=f"setdue_{customer_id}_15"),
                InlineKeyboardButton(text="⏳ 30 kun (1 oy)", callback_data=f"setdue_{customer_id}_30"),
            ],
            [InlineKeyboardButton(text="❌ Muddatni olib tashlash", callback_data=f"setdue_{customer_id}_0")],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"view_cust_{customer_id}")]
        ]
    )

def get_customer_actions_kb(customer_id: int, bot_username: str, shop_id: int, phone: str = None, telegram_id: int = None, due_date_str: str = None, ledger_type: str = 'receivable') -> InlineKeyboardMarkup:
    from urllib.parse import quote
    customer_link = f"https://t.me/{bot_username}?start=c_{customer_id}"
    
    if ledger_type == 'payable':
        # 🔴 HAQDOR (Qarz beruvchi) UCHUN TOZA TUGMALAR
        btn_due_text = f"📅 Qaytarish muddati ({due_date_str})" if due_date_str else "📅 Qaytarish muddati"
        rows = [
            [
                InlineKeyboardButton(text="➕ Qarz olish", callback_data=f"debt_{customer_id}"),
                InlineKeyboardButton(text="➖ Qarzni to'lash", callback_data=f"pay_{customer_id}")
            ],
            [
                InlineKeyboardButton(text="📜 Amallar tarixi", callback_data=f"history_{customer_id}"),
                InlineKeyboardButton(text=btn_due_text, callback_data=f"due_{customer_id}")
            ]
        ]
        if telegram_id:
            rows.append([InlineKeyboardButton(text="💬 Telegramiga yozish", url=f"tg://user?id={telegram_id}")])
            
        rows.append([
            InlineKeyboardButton(text="🗑 Haqdor o'chirish", callback_data=f"del_cust_{customer_id}"),
            InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_list")
        ])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    else:
        # 🟢 QARZDOR (Mijoz) UCHUN TUGMALAR
        share_text = "Assalomu alaykum! Qarz va nasiya hisobingizni kuzatib borish uchun ushbu havolani bosing:"
        share_url = f"https://t.me/share/url?url={quote(customer_link)}&text={quote(share_text)}"
        btn_due_text = f"📅 To'lov muddati ({due_date_str})" if due_date_str else "📅 Muddat belgilash"
        
        rows = [
            [
                InlineKeyboardButton(text="➕ Qarz / Nasiya", callback_data=f"debt_{customer_id}"),
                InlineKeyboardButton(text="➖ To'lov olish", callback_data=f"pay_{customer_id}")
            ],
            [
                InlineKeyboardButton(text="🔔 Eslatma yuborish", callback_data=f"remind_{customer_id}"),
                InlineKeyboardButton(text=btn_due_text, callback_data=f"due_{customer_id}")
            ],
            [
                InlineKeyboardButton(text="📜 Amallar tarixi", callback_data=f"history_{customer_id}"),
                InlineKeyboardButton(text="📤 Taklif yuborish", url=share_url)
            ]
        ]
        
        comm_row = [InlineKeyboardButton(text="📲 SMS shabloni", callback_data=f"sms_{customer_id}")]
        if telegram_id:
            comm_row.append(InlineKeyboardButton(text="💬 Telegramiga yozish", url=f"tg://user?id={telegram_id}"))
        rows.append(comm_row)
        
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
        bal_uzs = c.get('balance', 0.0) or 0.0
        bal_usd = c.get('balance_usd', 0.0) or 0.0
        
        if bal_uzs > 0 and bal_usd > 0:
            balance_str = f"{format_money(bal_uzs, 'UZS')} | {format_money(bal_usd, 'USD')}"
        elif bal_usd > 0:
            balance_str = format_money(bal_usd, 'USD')
        else:
            balance_str = format_money(bal_uzs, 'UZS')
            
        due_icon = " ⏰" if c.get('due_date') else ""
        btn_text = f"👤 {c['full_name']} — {balance_str}{due_icon}"
        inline_keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"view_cust_{c['id']}")])
        
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"page_{page-1}"))
    if end_idx < len(customers):
        nav_buttons.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"page_{page+1}"))
    
    if nav_buttons:
        inline_keyboard.append(nav_buttons)
        
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

