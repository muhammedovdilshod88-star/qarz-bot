from aiogram import Router, F, Bot
from aiogram.filters import StateFilter
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db
from keyboards.admin_kb import (
    get_admin_main_kb, get_cancel_kb, get_customer_actions_kb, 
    get_customers_list_kb, format_money, get_staff_list_kb, 
    get_add_customer_menu_kb, get_stats_period_kb
)
from utils.qr import generate_shop_qr
import config

router = Router()

class AdminStates(StatesGroup):
    add_customer_name = State()
    add_customer_phone = State()
    search_customer = State()
    change_shop_name = State()
    add_debt_amount = State()
    add_debt_desc = State()
    add_payment_amount = State()
    add_staff_name = State()
    add_staff_tg_id = State()

@router.message(StateFilter('*'), F.text.in_(["❌ Bekor qilish", "/cancel"]))
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    shop = await db.get_shop_by_admin(message.from_user.id)
    if shop:
        is_valid, days_left, _ = await db.check_shop_subscription(shop['id'])
        is_sa = message.from_user.id in config.SUPER_ADMIN_IDS
        await message.answer("Amal bekor qilindi.", reply_markup=get_admin_main_kb(is_sa, days_left=days_left))
    else:
        await message.answer("Amal bekor qilindi.")

# ==================== SHERIKLAR (ADMINLAR) BOSHQARUVI ====================

@router.message(StateFilter('*'), F.text.contains("Sheriklar"))
async def show_staff_menu(message: Message, state: FSMContext):
    await state.clear()
    shop = await db.get_shop_by_admin(message.from_user.id)
    if not shop:
        return
    
    admins = await db.list_shop_admins(shop['id'])
    staff_count = sum(1 for a in admins if a['role'] == 'staff')
    can_add = staff_count < 2 # Maksimal 2 ta qo'shimcha sherik
    
    kb = get_staff_list_kb(admins, can_add=can_add)
    text = (
        f"👥 <b>{shop['name']} — Do'kon Administratorlari</b>\n\n"
        f"Bu yerda siz do'konni birgalikda boshqarish, qarz yozish va to'lovlarni qabul qilish uchun "
        f"<b>2 tagacha qo'shimcha sherik (qarindosh yoki sotuvchi)</b> qo'shishingiz mumkin.\n\n"
        f"Mavjud adminlar:"
    )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "add_new_staff")
async def start_add_staff(call: CallbackQuery, bot: Bot):
    shop_row = await db.get_shop_by_admin(call.from_user.id)
    if not shop_row:
        await call.answer()
        return
    
    shop = dict(shop_row)
    # Faqat asosiy do'kon egasi sherik qo'sha oladi
    if shop.get('admin_role') == 'staff':
        await call.answer("⚠️ Faqat asosiy do'kon egasi yangi sotuvchi/sherik qo'sha oladi!", show_alert=True)
        return
        
    admins = await db.list_shop_admins(shop['id'])
    staff_count = sum(1 for a in admins if a['role'] == 'staff')
    if staff_count >= 5:
        await call.answer("⚠️ Siz allaqachon maksimal (5 ta) sotuvchi/sherik qo'shgansiz!", show_alert=True)
        return
        
    token = await db.create_staff_invite(shop['id'])
    bot_info = await bot.get_me()
    invite_url = f"https://t.me/{bot_info.username}?start=staff_{token}"
    
    from urllib.parse import quote
    shop_name = shop['name']
    invite_text = f"Assalomu alaykum! {shop_name} do'koni admin paneliga ulanish uchun ushbu taklif havolasini bosing:"
    share_url = f"https://t.me/share/url?url={quote(invite_url)}&text={quote(invite_text)}"
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Sotuvchi/Sherikka yuborish", url=share_url)],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_staff_list")]
    ])
    
    text = (
        f"🔗 <b>Yangi sotuvchi / sherik uchun taklif havolasi tayyor!</b>\n\n"
        f"Ushbu havolani sotuvchingiz yoki qarindoshingizga yuboring. U havolani bitta bosishi bilan avtomatik do'kon administratoriga aylanadi va qarz daftarini yurgiza oladi:\n\n"
        f"<code>{invite_url}</code>\n\n"
        f"<i>(Bir martalik xavfsiz havola)</i>"
    )
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data == "back_to_staff_list")
async def back_to_staff_list_cb(call: CallbackQuery):
    shop = await db.get_shop_by_admin(call.from_user.id)
    if not shop:
        await call.answer()
        return
    admins = await db.list_shop_admins(shop['id'])
    staff_count = sum(1 for a in admins if a['role'] == 'staff')
    can_add = staff_count < 5
    kb = get_staff_list_kb(admins, can_add=can_add)
    await call.message.edit_text("👥 <b>Do'kon Administratorlari (Sotuvchilar / Sheriklar):</b>", reply_markup=kb, parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data.startswith("del_staff_"))
async def delete_staff_callback(call: CallbackQuery):
    staff_id = int(call.data.split("_")[2])
    shop_row = await db.get_shop_by_admin(call.from_user.id)
    if not shop_row:
        await call.answer()
        return
        
    shop = dict(shop_row)
    if shop.get('admin_role') == 'staff':
        await call.answer("⚠️ Faqat asosiy do'kon egasi sotuvchini o'chira oladi!", show_alert=True)
        return
        
    await db.delete_shop_staff(staff_id, shop['id'])
    await call.answer("Sotuvchi o'chirildi!", show_alert=True)
    
    admins = await db.list_shop_admins(shop['id'])
    staff_count = sum(1 for a in admins if a['role'] == 'staff')
    can_add = staff_count < 5
    kb = get_staff_list_kb(admins, can_add=can_add)
    await call.message.edit_reply_markup(reply_markup=kb)

@router.callback_query(F.data == "back_to_admin_main")
async def back_to_admin_panel(call: CallbackQuery):
    await call.message.delete()
    await call.answer()

# ==================== DO'KON MA'LUMOTLARI VA SOZLAMALAR ====================

@router.message(StateFilter('*'), F.text == "⚙️ Do'kon nomi")
async def edit_shop_name_start(message: Message, state: FSMContext):
    await state.clear()
    shop = await db.get_shop_by_admin(message.from_user.id)
    if not shop:
        return
    await state.set_state(AdminStates.change_shop_name)
    await message.answer(
        f"Hozirgi do'kon nomi: <b>{shop['name']}</b>\n\nYangi nomni kiriting:",
        parse_mode="HTML",
        reply_markup=get_cancel_kb()
    )

@router.message(AdminStates.change_shop_name)
async def process_shop_name_change(message: Message, state: FSMContext):
    new_name = message.text.strip()
    shop = await db.get_shop_by_admin(message.from_user.id)
    if shop:
        await db.update_shop_name(shop['id'], new_name)
        is_valid, days_left, _ = await db.check_shop_subscription(shop['id'])
        is_sa = message.from_user.id in config.SUPER_ADMIN_IDS
        await message.answer(
            f"✅ Do'kon nomi muvaffaqiyatli o'zgartirildi: <b>{new_name}</b>",
            parse_mode="HTML",
            reply_markup=get_admin_main_kb(is_sa, days_left=days_left)
        )
    await state.clear()

from keyboards.admin_kb import get_subscription_kb

@router.message(StateFilter('*'), F.text.contains("Obuna"))
async def show_subscription_info(message: Message, state: FSMContext):
    await state.clear()
    shop = await db.get_shop_by_admin(message.from_user.id)
    if not shop:
        return
    
    is_valid, days_left, expires_at = await db.check_shop_subscription(shop['id'])
    status_icon = "🟢 Faol" if days_left > 0 else "🔴 Muddati tugagan"
    date_formatted = str(expires_at)[:10] if expires_at else "Noma'lum"
    
    text = (
        f"⏳ <b>{shop['name']} — Obuna va Billing Ma'lumotlari</b>\n\n"
        f"⚡ <b>Holati:</b> {status_icon}\n"
        f"📅 <b>Qolgan muddat:</b> <b>{days_left} kun</b>\n"
        f"📆 <b>Amal qilish sanasi:</b> <code>{date_formatted}</code> gacha\n\n"
        f"────────────────────\n"
        f"💳 <b>Obunani uzaytirish uchun to'lov rekvizitlari:</b>\n"
        f"💳 Karta raqami: <code>{config.CARD_NUMBER}</code>\n"
        f"👤 Qabul qiluvchi: <b>{config.CARD_HOLDER}</b>\n\n"
        f"📌 <i>To'lov amalga oshirilgach, chekni pastdagi tugma orqali yuboring. Obunangiz darhol uzaytirib beriladi!</i>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_subscription_kb())

@router.message(StateFilter('*'), F.text == "📲 Ekranga znachok qilish")
async def show_add_to_homescreen_guide(message: Message):
    text = (
        "📲 <b>Botni telefon ekraniga Znachok (Ilova) qilish qo'llanmasi:</b>\n\n"
        "Buni 1 marta qilib qo'ysangiz, Telegram ichidan qidirib o'tirmaysiz — telefoningiz ish stolida xuddi ilovadek turadi!\n\n"
        "👉 <b>Qanday qilinadi (3 ta oddiy qadam):</b>\n"
        "1️⃣ Yuqoridagi <b>«Qarz daftari bot»</b> nomiga (profiliga) bosing.\n"
        "2️⃣ O'ng burchakdagi <b>3 ta nuqta (⋮)</b> ni bosing.\n"
        "3️⃣ <b>«Добавить на главный экран»</b> (yoki <i>«Add to Home screen» / «Asosiy ekranga qo'shish»</i>) ni bosing!\n\n"
        "🎉 <b>Tayyor!</b> Endi telefoningiz ekranidan 1 marta bosib to'g'ridan-to'g'ri qarz daftariga kirasiz."
    )
    await message.answer(text, parse_mode="HTML")

@router.message(StateFilter('*'), F.text == "📲 Do'kon QR kodi")
async def send_shop_qr_code(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    shop = await db.get_shop_by_admin(message.from_user.id)
    if not shop:
        return
    
    bot_info = await bot.get_me()
    qr_bio = generate_shop_qr(bot_info.username, shop['id'])
    
    caption = (
        f"🏪 <b>{shop['name']}</b> — Maxsus QR Kodi\n\n"
        f"📌 Ushbu QR kodni chop etib do'kon peshtaxtasiga yoki devorga ilib qo'yishingiz mumkin.\n"
        f"Mijozlar telefon kamerasi orqali skaner qilib botga ulanishadi va o'z qarzlarini ko'rib borishadi.\n\n"
        f"🔗 Havola: https://t.me/{bot_info.username}?start=shop_{shop['id']}"
    )
    
    photo_file = BufferedInputFile(qr_bio.getvalue(), filename=f"shop_{shop['id']}.png")
    await message.answer_photo(photo=photo_file, caption=caption, parse_mode="HTML")

def build_stats_message(shop_name: str, stats: dict) -> str:
    period_names = {
        'today': '📅 Bugungi hisobot',
        'week': '🗓 Oxirgi 7 kunlik hisobot',
        'month': '📆 Oxirgi 30 kunlik hisobot',
        'all': '📊 Barcha vaqt bo‘yicha umumiy hisobot'
    }
    period_title = period_names.get(stats['period'], '📊 Hisobot')
    
    top_text = ""
    if stats['top_debtors']:
        top_text = "\n🏆 <b>Eng katta qarzdorlar (TOP):</b>\n"
        for i, d in enumerate(stats['top_debtors'], 1):
            top_text += f"{i}. 👤 {d['full_name']} — <b>{format_money(d['balance'])}</b>\n"
    else:
        top_text = "\n<i>(Hozircha hech kimda faol qarz yo'q)</i>\n"

    return (
        f"🏪 <b>{shop_name} — Moliya va Nasiya Statistikasi</b>\n"
        f"<b>{period_title}</b>\n"
        f"────────────────────\n"
        f"💰 <b>Joriy faol nasiyalar (Do'kon haqi):</b> <b>{format_money(stats['total_active_debt'])}</b>\n\n"
        f"📈 <b>Tanlangan davr bo'yicha:</b>\n"
        f"➕ Berilgan yangi qarz: <b>+{format_money(stats['period_debt'])}</b>\n"
        f"➖ Undirilgan to'lov: <b>-{format_money(stats['period_payment'])}</b>\n"
        f"🔄 Operatsiyalar soni: <b>{stats['total_tx_count']} ta</b>\n\n"
        f"👥 <b>Mijozlar holati:</b>\n"
        f"• Jami mijozlar: <b>{stats['total_customers']} nafar</b>\n"
        f"• ⚠️ Qarzda turganlar: <b>{stats['indebted_customers']} nafar</b>\n"
        f"• ✅ Qarzi yo'qlar: <b>{stats['clear_customers']} nafar</b>\n"
        f"{top_text}\n"
        f"👇 <i>Boshqa davrni ko'rish uchun quyidagi tugmalarni bosing:</i>"
    )

@router.message(StateFilter('*'), F.text == "📊 Statistika")
async def show_shop_statistics(message: Message, state: FSMContext):
    await state.clear()
    shop = await db.get_shop_by_admin(message.from_user.id)
    if not shop:
        return
    
    stats = await db.get_detailed_shop_statistics(shop['id'], period='all')
    text = build_stats_message(shop['name'], stats)
    kb = get_stats_period_kb(current_period='all')
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("stat_"))
async def switch_stats_period(call: CallbackQuery):
    period = call.data.replace("stat_", "")
    shop = await db.get_shop_by_admin(call.from_user.id)
    if not shop:
        await call.answer()
        return
        
    stats = await db.get_detailed_shop_statistics(shop['id'], period=period)
    text = build_stats_message(shop['name'], stats)
    kb = get_stats_period_kb(current_period=period)
    
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await call.answer()

# ==================== MIJOZLARNI RO'YXATI VA FILTR ====================

@router.message(StateFilter('*'), F.text == "📋 Mijozlar ro'yxati")
async def list_customers_cmd(message: Message, state: FSMContext):
    await state.clear()
    shop = await db.get_shop_by_admin(message.from_user.id)
    if not shop:
        return
    
    customers = await db.list_shop_customers(shop['id'], sort_by_debt=True)
    if not customers:
        await message.answer("Sizda hali mijozlar mavjud emas. '➕ Yangi mijoz' tugmasi orqali qo'shishingiz yoki QR kodni mijozlarga berishingiz mumkin.")
        return
    
    kb = get_customers_list_kb(customers, page=0)
    await message.answer("📋 <b>Mijozlar ro'yxati</b> (Eng katta qarz egalari tepada):\nKerakli mijozni tanlang:", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("page_"))
async def paginate_customers(call: CallbackQuery):
    page = int(call.data.split("_")[1])
    shop = await db.get_shop_by_admin(call.from_user.id)
    if not shop:
        await call.answer()
        return
    
    customers = await db.list_shop_customers(shop['id'], sort_by_debt=True)
    kb = get_customers_list_kb(customers, page=page)
    await call.message.edit_reply_markup(reply_markup=kb)
    await call.answer()

@router.callback_query(F.data == "back_to_list")
async def back_to_customers_list(call: CallbackQuery):
    shop = await db.get_shop_by_admin(call.from_user.id)
    if not shop:
        await call.answer()
        return
    
    customers = await db.list_shop_customers(shop['id'], sort_by_debt=True)
    kb = get_customers_list_kb(customers, page=0)
    await call.message.edit_text("📋 <b>Mijozlar ro'yxati:</b>", reply_markup=kb, parse_mode="HTML")
    await call.answer()

# ==================== MIJOZNI KO'RISH ====================

from keyboards.admin_kb import get_due_date_select_kb

@router.callback_query(F.data.startswith("view_cust_"))
async def view_customer_detail(call: CallbackQuery, bot: Bot):
    customer_id = int(call.data.split("_")[2])
    customer = await db.get_customer(customer_id)
    if not customer:
        await call.answer("Mijoz topilmadi!", show_alert=True)
        return
    
    bot_info = await bot.get_me()
    status_tg = "✅ Telegram ulangan" if customer['telegram_id'] else "❌ Telegram hali ulanmagan"
    phone_text = customer['phone'] if customer['phone'] else "Kiritilmagan"
    due_str = str(customer['due_date'])[:10] if customer.get('due_date') else None
    due_display = f"📅 <b>To'lov muddati:</b> <code>{due_str}</code> gacha\n" if due_str else ""
    
    text = (
        f"👤 <b>Mijoz:</b> {customer['full_name']}\n"
        f"📞 <b>Telefon:</b> <code>{phone_text}</code>\n"
        f"📱 <b>Holat:</b> {status_tg}\n"
        f"{due_display}"
        f"💰 <b>Joriy qarz/nasiya balansi:</b> <b>{format_money(customer['balance'])}</b>\n\n"
        f"Quyidagi amallardan birini tanlang:"
    )
    kb = get_customer_actions_kb(
        customer_id=customer_id, 
        bot_username=bot_info.username, 
        shop_id=customer['shop_id'], 
        phone=customer['phone'],
        has_telegram=bool(customer['telegram_id']),
        due_date_str=due_str
    )
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

# ==================== 1. TELEGRAM ORQALI ESLATISH ====================

@router.callback_query(F.data.startswith("remind_"))
async def send_customer_reminder(call: CallbackQuery, bot: Bot):
    customer_id = int(call.data.split("_")[1])
    customer = await db.get_customer(customer_id)
    if not customer:
        await call.answer("Mijoz topilmadi!", show_alert=True)
        return
        
    if customer['balance'] <= 0:
        await call.answer("Bu mijozda faol qarz yo'q!", show_alert=True)
        return
        
    shop = await db.get_shop_by_id(customer['shop_id'])
    shop_name = shop['name'] if shop else "Do'kon"
    
    if not customer['telegram_id']:
        await call.answer("⚠️ Mijoz hali botga ulanmagan! Pastdagi '📲 SMS shabloni' orqali yuborishingiz mumkin.", show_alert=True)
        return
        
    # Madaniyatli va rasmiy eslatma matni
    reminder_msg = (
        f"🔔 <b>Hurmatli {customer['full_name']}!</b>\n\n"
        f"<b>«{shop_name}»</b> do'konidagi qarz va nasiya hisobingiz bo'yicha joriy qoldiq: <b>{format_money(customer['balance'])}</b>.\n\n"
        f"💳 <i>Imkoningiz bo'lganda to'lovni amalga oshirishingizni so'raymiz. Xaridingiz uchun rahmat!</i>\n\n"
        f"💬 <a href='tg://user?id={shop['admin_id']}'>Do'konchi bilan bog'lanish</a>"
    )
    
    try:
        await bot.send_message(chat_id=customer['telegram_id'], text=reminder_msg, parse_mode="HTML")
        await call.answer(f"✅ {customer['full_name']} ga Telegram orqali eslatma yuborildi!", show_alert=True)
    except Exception as e:
        await call.answer(f"⚠️ Xatolik: {e}", show_alert=True)

# ==================== 2. MUDDAT BELGILASH ====================

@router.callback_query(F.data.startswith("due_"))
async def start_set_due_date(call: CallbackQuery):
    customer_id = int(call.data.split("_")[1])
    customer = await db.get_customer(customer_id)
    if not customer:
        await call.answer("Mijoz topilmadi!", show_alert=True)
        return
        
    text = (
        f"📅 <b>{customer['full_name']}</b> uchun to'lov muddatini tanlang:\n\n"
        f"<i>(Belgilangan muddat kelganda bot mijozga avtomatik eslatma yuboradi)</i>"
    )
    await call.message.edit_text(text, reply_markup=get_due_date_select_kb(customer_id), parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data.startswith("setdue_"))
async def process_set_due_date(call: CallbackQuery, bot: Bot):
    parts = call.data.split("_")
    customer_id = int(parts[1])
    days = int(parts[2])
    
    await db.set_customer_due_date(customer_id, days)
    msg = "✅ To'lov muddati olib tashlandi." if days == 0 else f"✅ To'lov muddati {days} kunga belgilandi!"
    await call.answer(msg, show_alert=True)
    
    # Qayta mijoz oynasiga qaytish
    call.data = f"view_cust_{customer_id}"
    await view_customer_detail(call, bot)

# ==================== 3. SMS SHABLONI ====================

@router.callback_query(F.data.startswith("sms_"))
async def show_sms_template(call: CallbackQuery):
    customer_id = int(call.data.split("_")[1])
    customer = await db.get_customer(customer_id)
    if not customer:
        await call.answer("Mijoz topilmadi!", show_alert=True)
        return
        
    shop = await db.get_shop_by_id(customer['shop_id'])
    shop_name = shop['name'] if shop else "Do'kon"
    phone = customer['phone'] or ""
    
    sms_text = (
        f"Assalomu alaykum, {customer['full_name']}! "
        f"'{shop_name}' do'konidagi qarz/nasiyangiz: {format_money(customer['balance'])}. "
        f"Imkoningiz bo'lganda to'lovni amalga oshirishingizni so'raymiz. Rahmat!"
    )
    
    from urllib.parse import quote
    clean_phone = "".join([c for c in phone if c.isdigit()])
    sms_url = f"sms:+{clean_phone}?body={quote(sms_text)}" if clean_phone else None
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    if sms_url:
        buttons.append([InlineKeyboardButton(text="📱 SMS ilovasida ochish", url=sms_url)])
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"view_cust_{customer_id}")])
    
    text = (
        f"📲 <b>Mijoz uchun tayyor SMS shabloni:</b>\n\n"
        f"<code>{sms_text}</code>\n\n"
        f"<i>(Matn ustiga bosing — nusxalanadi va telefondan SMS qilib yuborishingiz mumkin)</i>"
    )
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await call.answer()

# ==================== QARZ TARIXI ====================

@router.callback_query(F.data.startswith("history_"))
async def show_customer_history(call: CallbackQuery, bot: Bot):
    customer_id = int(call.data.split("_")[1])
    customer = await db.get_customer(customer_id)
    if not customer:
        await call.answer("Mijoz topilmadi!", show_alert=True)
        return
    
    bot_info = await bot.get_me()
    txs = await db.get_customer_transactions(customer_id, limit=15)
    
    text = f"📜 <b>{customer['full_name']}</b> — Qarz va to'lovlar tarixi:\n\n"
    if not txs:
        text += "<i>Hozircha hech qanday operatsiya yozilmagan.</i>"
    else:
        for t in txs:
            icon = "🔴 Qarz:" if t['type'] == 'debt' else "🟢 To'lov:"
            desc = f" ({t['description']})" if t['description'] else ""
            date_str = str(t['created_at'])[:16]
            text += f"{icon} {format_money(t['amount'])}{desc}\n📅 <i>{date_str}</i>\n───────────────\n"
            
    text += f"\n💰 <b>Jami qoldiq qarz: {format_money(customer['balance'])}</b>"
    
    kb = get_customer_actions_kb(customer_id, bot_info.username, customer['shop_id'], customer['phone'])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

# ==================== MIJOZNI O'CHIRISH ====================

@router.callback_query(F.data.startswith("del_cust_"))
async def delete_customer_callback(call: CallbackQuery):
    customer_id = int(call.data.split("_")[2])
    customer = await db.get_customer(customer_id)
    if not customer:
        await call.answer("Mijoz topilmadi!", show_alert=True)
        return
    
    await db.delete_customer(customer_id)
    await call.answer(f"✅ {customer['full_name']} ro'yxatdan o'chirildi.", show_alert=True)
    
    shop = await db.get_shop_by_admin(call.from_user.id)
    if shop:
        customers = await db.list_shop_customers(shop['id'], sort_by_debt=True)
        if customers:
            kb = get_customers_list_kb(customers, page=0)
            await call.message.edit_text("📋 <b>Mijozlar ro'yxati:</b>", reply_markup=kb, parse_mode="HTML")
        else:
            await call.message.edit_text("Sizda hali mijozlar mavjud emas.")

# ==================== YANGI MIJOZ QO'SHISH ====================

@router.message(StateFilter('*'), F.text == "➕ Yangi mijoz")
async def add_customer_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    shop = await db.get_shop_by_admin(message.from_user.id)
    if not shop:
        return
        
    bot_info = await bot.get_me()
    qr_bio = generate_shop_qr(bot_info.username, shop['id'])
    
    caption = (
        f"➕ <b>Yangi mijoz qo'shish usullari:</b>\n\n"
        f"1️⃣ <b>📲 QR Kod orqali (Tavsiya etiladi):</b>\n"
        f"Mijoz ushbu QR kodni telefon kamerasi bilan skaner qilsa, bir zumda do'koningizga ulanadi va hisobotlarni ko'rib boradi.\n\n"
        f"2️⃣ <b>✍️ Qo'lda kiritish:</b>\n"
        f"Agar mijozning telefoni bo'lmasa yoki hozir do'konda bo'lmasa, quyidagi tugmani bosib uning Ism va telefonini kiritib qo'yishingiz mumkin."
    )
    
    kb = get_add_customer_menu_kb(bot_info.username, shop['id'])
    photo_file = BufferedInputFile(qr_bio.getvalue(), filename=f"shop_{shop['id']}_qr.png")
    await message.answer_photo(photo=photo_file, caption=caption, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "manual_add_cust")
async def start_manual_customer_add(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.add_customer_name)
    await call.message.answer(
        "Mijozning <b>Ism va Familiyasini</b> kiriting:\n<i>(Masalan: Rustam Aliyev)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_kb()
    )
    await call.answer()

@router.message(AdminStates.add_customer_name)
async def process_customer_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Iltimos, haqiqiy ism kiriting:")
        return
    await state.update_data(full_name=name)
    await state.set_state(AdminStates.add_customer_phone)
    await message.answer(
        f"Mijoz: <b>{name}</b>\n\nEndi mijozning telefon raqamini kiriting (yoki o'tkazib yuborish uchun '-' yozing):",
        parse_mode="HTML"
    )

@router.message(AdminStates.add_customer_phone)
async def process_customer_phone(message: Message, state: FSMContext, bot: Bot):
    phone_raw = message.text.strip()
    phone = phone_raw if phone_raw != "-" else None
    
    data = await state.get_data()
    shop = await db.get_shop_by_admin(message.from_user.id)
    
    cust_id = await db.add_manual_customer(shop['id'], data['full_name'], phone)
    await state.clear()
    
    bot_info = await bot.get_me()
    is_sa = message.from_user.id in config.SUPER_ADMIN_IDS
    
    await message.answer(
        f"✅ Yangi mijoz muvaffaqiyatli qo'shildi:\n👤 <b>{data['full_name']}</b>\n📞 {phone or 'Kiritilmadi'}",
        parse_mode="HTML",
        reply_markup=get_admin_main_kb(is_sa)
    )
    
    # Taklif yuborish tugmalarini ham chiqarib beramiz
    kb = get_customer_actions_kb(cust_id, bot_info.username, shop['id'], phone)
    await message.answer(
        f"💡 <b>{data['full_name']}</b> ga bot havolasini yuborish yoki qarz yozish uchun:",
        reply_markup=kb,
        parse_mode="HTML"
    )

# ==================== QARZ YOZISH (SUMMA + IZOH) ====================

@router.callback_query(F.data.startswith("debt_"))
async def start_add_debt(call: CallbackQuery, state: FSMContext):
    customer_id = int(call.data.split("_")[1])
    customer = await db.get_customer(customer_id)
    if not customer:
        await call.answer("Mijoz topilmadi!", show_alert=True)
        return
    
    await state.set_state(AdminStates.add_debt_amount)
    await state.update_data(customer_id=customer_id, customer_name=customer['full_name'])
    
    await call.message.answer(
        f"➕ <b>{customer['full_name']}</b> ga qarz / nasiya summasini kiriting (faqat raqam, masalan: 50000 yoki 1500000):",
        parse_mode="HTML",
        reply_markup=get_cancel_kb()
    )
    await call.answer()

@router.message(AdminStates.add_debt_amount)
async def process_debt_amount(message: Message, state: FSMContext):
    text = message.text.replace(" ", "").replace(",", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Iltimos, to'g'ri musbat summa kiriting (masalan: 100000):")
        return
    
    await state.update_data(debt_amount=amount)
    await state.set_state(AdminStates.add_debt_desc)
    await message.answer(
        f"Summa: <b>{format_money(amount)}</b>\n\n"
        f"📝 <b>Olingan tovar yoki xizmat izohini yozing:</b>\n"
        f"<i>(Masalan: Ko'ylak, Zapchast, Sement, Yog'-shakar, 2 ta kastyum va h.k.)</i>\n\n"
        f"Yoki o'tkazib yuborish uchun <code>-</code> yozing:",
        parse_mode="HTML"
    )

@router.message(AdminStates.add_debt_desc)
async def process_debt_description(message: Message, state: FSMContext, bot: Bot):
    desc_raw = message.text.strip()
    desc = desc_raw if desc_raw != "-" else None
    
    data = await state.get_data()
    shop = await db.get_shop_by_admin(message.from_user.id)
    
    updated_customer = await db.add_transaction(
        shop_id=shop['id'],
        customer_id=data['customer_id'],
        amount=data['debt_amount'],
        tx_type='debt',
        description=desc
    )
    
    await state.clear()
    is_sa = message.from_user.id in config.SUPER_ADMIN_IDS
    
    msg_text = (
        f"✅ <b>Qarz / Nasiya muvaffaqiyatli yozildi!</b>\n\n"
        f"👤 Mijoz: <b>{updated_customer['full_name']}</b>\n"
        f"➕ Qo'shilgan summa: <b>{format_money(data['debt_amount'])}</b>\n"
        f"📦 Tovar / Izoh: <i>{desc or 'Kiritilmadi'}</i>\n"
        f"💰 Jami qarz/nasiya balansi: <b>{format_money(updated_customer['balance'])}</b>"
    )
    await message.answer(msg_text, parse_mode="HTML", reply_markup=get_admin_main_kb(is_sa))
    
    # Agar mijoz telegram orqali ulangan bo'lsa, unga bildirishnoma yuboramiz
    if updated_customer['telegram_id']:
        try:
            client_notify = (
                f"📌 <b>{shop['name']}</b> do'konidan xabar:\n\n"
                f"Sizning hisobingizga yangi qarz / nasiya yozildi: <b>+{format_money(data['debt_amount'])}</b>\n"
                f"📦 Tovar / Izoh: <i>{desc or 'Kiritilmadi'}</i>\n"
                f"💰 Sizning jami qarz/nasiya balansingiz: <b>{format_money(updated_customer['balance'])}</b>\n\n"
                f"💬 <a href='tg://user?id={shop['admin_id']}'>Do'konchi bilan bog'lanish</a>"
            )
            await bot.send_message(chat_id=updated_customer['telegram_id'], text=client_notify, parse_mode="HTML")
        except Exception:
            pass

# ==================== TO'LOV QABUL QILISH ====================

@router.callback_query(F.data.startswith("pay_"))
async def start_add_payment(call: CallbackQuery, state: FSMContext):
    customer_id = int(call.data.split("_")[1])
    customer = await db.get_customer(customer_id)
    if not customer:
        await call.answer("Mijoz topilmadi!", show_alert=True)
        return
    
    await state.set_state(AdminStates.add_payment_amount)
    await state.update_data(customer_id=customer_id)
    
    await call.message.answer(
        f"➖ <b>{customer['full_name']}</b> qancha to'lov qildi? (Summani kiriting, masalan: 50000):\n"
        f"Hozirgi umumiy qarzi: <b>{format_money(customer['balance'])}</b>",
        parse_mode="HTML",
        reply_markup=get_cancel_kb()
    )
    await call.answer()

@router.message(AdminStates.add_payment_amount)
async def process_payment_amount(message: Message, state: FSMContext, bot: Bot):
    text = message.text.replace(" ", "").replace(",", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Iltimos, to'g'ri musbat to'lov summasini kiriting:")
        return
    
    data = await state.get_data()
    shop = await db.get_shop_by_admin(message.from_user.id)
    
    updated_customer = await db.add_transaction(
        shop_id=shop['id'],
        customer_id=data['customer_id'],
        amount=amount,
        tx_type='payment',
        description="Qarz to'lovi"
    )
    
    await state.clear()
    is_sa = message.from_user.id in config.SUPER_ADMIN_IDS
    
    msg_text = (
        f"✅ <b>To'lov qabul qilindi!</b>\n\n"
        f"👤 Mijoz: <b>{updated_customer['full_name']}</b>\n"
        f"➖ Qabul qilingan to'lov: <b>{format_money(amount)}</b>\n"
        f"💰 Qolgan qarz balansi: <b>{format_money(updated_customer['balance'])}</b>"
    )
    await message.answer(msg_text, parse_mode="HTML", reply_markup=get_admin_main_kb(is_sa))
    
    # Mijozga telegram orqali to'lov xabarini yuborish
    if updated_customer['telegram_id']:
        try:
            client_notify = (
                f"✅ <b>{shop['name']}</b> do'konidan xabar:\n\n"
                f"Sizning <b>{format_money(amount)}</b> to'lovingiz qabul qilindi.\n"
                f"💰 Qolgan qarz balansingiz: <b>{format_money(updated_customer['balance'])}</b>\n"
                f"Rahmat!\n\n"
                f"💬 <a href='tg://user?id={shop['admin_id']}'>Do'konchi bilan Telegramda bog'lanish</a>"
            )
            await bot.send_message(chat_id=updated_customer['telegram_id'], text=client_notify, parse_mode="HTML")
        except Exception:
            pass

# ==================== QIDIRUV ====================

@router.message(F.text == "🔍 Qidirish")
async def search_customer_start(message: Message, state: FSMContext):
    shop = await db.get_shop_by_admin(message.from_user.id)
    if not shop:
        return
    await state.set_state(AdminStates.search_customer)
    await message.answer("Qidirilayotgan mijozning <b>ism yoki telefon raqamini</b> yozing:", parse_mode="HTML", reply_markup=get_cancel_kb())

@router.message(AdminStates.search_customer)
async def process_search_customer(message: Message, state: FSMContext):
    query = message.text.strip()
    shop = await db.get_shop_by_admin(message.from_user.id)
    customers = await db.search_customers(shop['id'], query)
    
    await state.clear()
    is_sa = message.from_user.id in config.SUPER_ADMIN_IDS
    
    if not customers:
        await message.answer(f"🔍 '{query}' bo'yicha hech qanday mijoz topilmadi.", reply_markup=get_admin_main_kb(is_sa))
        return
    
    kb = get_customers_list_kb(customers, page=0)
    await message.answer(f"🔍 '{query}' bo'yicha topilgan mijozlar:", reply_markup=kb, reply_markup_after=get_admin_main_kb(is_sa))
