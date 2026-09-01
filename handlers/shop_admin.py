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

USER_LEDGER_MODES: dict = {}

def get_user_ledger_mode(user_id: int) -> str:
    return USER_LEDGER_MODES.get(user_id, 'receivable')

def set_user_ledger_mode(user_id: int, mode: str):
    USER_LEDGER_MODES[user_id] = mode

@router.message(StateFilter('*'), F.text.in_(["❌ Bekor qilish", "/cancel"]))
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    shop = await db.get_shop_by_admin(message.from_user.id)
    if shop:
        is_valid, days_left, _ = await db.check_shop_subscription(shop['id'])
        is_sa = message.from_user.id in config.SUPER_ADMIN_IDS
        mode = get_user_ledger_mode(message.from_user.id)
        await message.answer("Amal bekor qilindi.", reply_markup=get_admin_main_kb(is_sa, days_left=days_left, ledger_type=mode))
    else:
        await message.answer("Amal bekor qilindi.")

# ==================== IKKI TOMONLAMA REJIMNI ALMASHTIRISH (SWITCH LEDGER TABS) ====================

@router.message(StateFilter('*'), F.text.func(lambda t: t and ("berishim kerak" in t.lower() or "olishim kerak" in t.lower() or "menga qarzlar" in t.lower() or "mening qarzlarim" in t.lower())))
async def switch_ledger_mode(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    shop = await db.get_shop_by_admin(user_id)
    if not shop:
        return
        
    is_valid, days_left, _ = await db.check_shop_subscription(shop['id'])
    is_sa = user_id in config.SUPER_ADMIN_IDS
    current_mode = get_user_ledger_mode(user_id)
    text_lower = message.text.lower()
    
    # Qaysi tab bosilganini aniqlaymiz
    if "berishim kerak" in text_lower or "mening qarzlarim" in text_lower:
        target_mode = 'payable'
    else:
        target_mode = 'receivable'
        
    set_user_ledger_mode(user_id, target_mode)
    
    if target_mode == 'payable':
        text = (
            f"🔴 <b>«MENING QARZLARIM (Men berishim kerak bo'lgan pullar)» rejimi faol! ✅</b>\n\n"
            f"Bu bo'limda siz o'zingiz boshqalardan olgan qarzlaringiz va haqdorlaringiz (qarz beruvchilar) ro'yxatini yuritishingiz mumkin.\n\n"
            f"👇 Quyidagi menyudan kerakli amalni tanlang:"
        )
    else:
        text = (
            f"🟢 <b>«MENGA QARZLAR (Menga qaytarishi kerak bo'lgan pullar)» rejimi faol! ✅</b>\n\n"
            f"Bu bo'limda siz boshqalarga bergan qarzlaringiz va qarzdorlar ro'yxatini boshqarasiz.\n\n"
            f"👇 Quyidagi menyudan kerakli amalni tanlang:"
        )
        
    await message.answer(text, parse_mode="HTML", reply_markup=get_admin_main_kb(is_sa, days_left=days_left, ledger_type=target_mode))

# ==================== SHERIKLAR (ADMINLAR) BOSHQARUVI ====================

@router.message(StateFilter('*'), F.text.func(lambda t: t and any(k in t.lower() for k in ["sherik", "adminlar"])))
async def show_staff_menu(message: Message, state: FSMContext):
    await state.clear()
    shop = await db.get_shop_by_admin(message.from_user.id)
    if not shop:
        return
    
    admins = await db.list_shop_admins(shop['id'])
    staff_count = sum(1 for a in admins if a['role'] == 'staff')
    can_add = staff_count < 5 # Maksimal 5 ta qo'shimcha sherik
    
    kb = get_staff_list_kb(admins, can_add=can_add)
    text = (
        f"👥 <b>«{shop['name']}» — Boshqaruvchilar (Sheriklar / Yordamchilar)</b>\n\n"
        f"Bu yerda siz daftarni birgalikda boshqarish, qarz yozish va to'lovlarni qabul qilish uchun "
        f"<b>5 tagacha qo'shimcha sherik (yordamchi, xodim yoki qarindosh)</b> qo'shishingiz mumkin.\n\n"
        f"Mavjud boshqaruvchilar:"
    )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "add_new_staff")
async def start_add_staff(call: CallbackQuery, bot: Bot):
    shop_row = await db.get_shop_by_admin(call.from_user.id)
    if not shop_row:
        await call.answer()
        return
    
    shop = dict(shop_row)
    # Faqat asosiy ega sherik qo'sha oladi
    if shop.get('admin_role') == 'staff':
        await call.answer("⚠️ Faqat asosiy hisob egasi yangi sherik qo'sha oladi!", show_alert=True)
        return
        
    admins = await db.list_shop_admins(shop['id'])
    staff_count = sum(1 for a in admins if a['role'] == 'staff')
    if staff_count >= 5:
        await call.answer("⚠️ Siz allaqachon maksimal (5 ta) sherik qo'shgansiz!", show_alert=True)
        return
        
    token = await db.create_staff_invite(shop['id'])
    bot_info = await bot.get_me()
    invite_url = f"https://t.me/{bot_info.username}?start=staff_{token}"
    
    from urllib.parse import quote
    shop_name = shop['name']
    invite_text = f"Assalomu alaykum! «{shop_name}» qarz daftari boshqaruviga ulanish uchun ushbu taklif havolasini bosing:"
    share_url = f"https://t.me/share/url?url={quote(invite_url)}&text={quote(invite_text)}"
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Sherik/Yordamchiga yuborish", url=share_url)],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_staff_list")]
    ])
    
    text = (
        f"🔗 <b>Yangi sherik / yordamchi uchun taklif havolasi tayyor!</b>\n\n"
        f"Ushbu havolani sherigingiz yoki yordamchingizga yuboring. U havolani bosishi bilan avtomatik boshqaruvga qo'shiladi va qarz daftarini birgalikda yuritishingiz mumkin:\n\n"
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
    await call.message.edit_text("👥 <b>Boshqaruvchilar (Sheriklar / Yordamchilar):</b>", reply_markup=kb, parse_mode="HTML")
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
        await call.answer("⚠️ Faqat asosiy hisob egasi sherikni o'chira oladi!", show_alert=True)
        return
        
    await db.delete_shop_staff(staff_id, shop['id'])
    await call.answer("Sherik o'chirildi!", show_alert=True)
    
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

@router.message(StateFilter('*'), F.text.func(lambda t: t and any(k in t.lower() for k in ["daftar nomi", "do'kon nomi", "nomi"])))
async def edit_shop_name_start(message: Message, state: FSMContext):
    await state.clear()
    shop = await db.get_shop_by_admin(message.from_user.id)
    if not shop:
        return
    await state.set_state(AdminStates.change_shop_name)
    await message.answer(
        f"Hozirgi nom: <b>{shop['name']}</b>\n\nYangi nomni kiriting:\n<i>(Masalan: Shaxsiy Qarz Daftari, Baraka Market, Usta Jamshid)</i>",
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
            f"✅ Nom muvaffaqiyatli o'zgartirildi: <b>{new_name}</b>",
            parse_mode="HTML",
            reply_markup=get_admin_main_kb(is_sa, days_left=days_left)
        )
    await state.clear()

from keyboards.admin_kb import get_subscription_kb

@router.message(StateFilter('*'), F.text.func(lambda t: t and "obuna" in t.lower()))
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

@router.message(StateFilter('*'), F.text.func(lambda t: t and "znachok" in t.lower()))
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

@router.message(StateFilter('*'), F.text.func(lambda t: t and any(k in t.lower() for k in ["excel", "hisobot"])))
async def send_shop_excel_report(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    shop = await db.get_shop_by_admin(user_id)
    if not shop:
        return
        
    mode = get_user_ledger_mode(user_id)
    is_payable = (mode == 'payable')
    report_target = "Mening qarzlarim (Haqdorlar)" if is_payable else "Menga qarzlar (Qarzdorlar)"
    await message.answer(f"⏳ <i>«{report_target}» bo'yicha Excel hisoboti tayyorlanmoqda...</i>", parse_mode="HTML")
    
    try:
        from utils.excel import generate_shop_excel
        from aiogram.types import BufferedInputFile
        from datetime import datetime
        
        bio = await generate_shop_excel(shop['id'], ledger_type=mode)
        date_str = datetime.now().strftime("%Y-%m-%d")
        file_prefix = "Mening_qarzlarim_Haqdorlar" if is_payable else "Menga_qarzlar_Qarzdorlar"
        filename = f"{file_prefix}_{date_str}.xlsx"
        doc = BufferedInputFile(bio.getvalue(), filename=filename)
        
        sheet1_name = "Haqdorlar va Qarzlar" if is_payable else "Qarzdorlar va Qarzlar"
        sheet1_desc = "Siz qarz olgan barcha haqdorlar va to'lashingiz kerak bo'lgan qarzlar" if is_payable else "Barcha qarzdorlaringiz va ularning qarz qoldiqlari"
        
        caption = (
            f"📊 <b>«{shop['name']}» — {report_target} Excel hisoboti</b>\n\n"
            f"📅 Sana: <code>{date_str}</code>\n"
            f"📑 <b>Varaqlar:</b>\n"
            f"1️⃣ <b>{sheet1_name}:</b> {sheet1_desc}\n"
            f"2️⃣ <b>Amallar Tarixi:</b> Barcha amallar va to'lovlar tarixi\n\n"
            f"<i>(Kompyuter yoki telefonda Excel dasturida ochib ko'rishingiz mumkin)</i>"
        )
        await message.answer_document(document=doc, caption=caption, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"⚠️ Hisobot tayyorlashda xatolik: {e}")

@router.message(StateFilter('*'), F.text.func(lambda t: t and any(k in t.lower() for k in ["qr", "ulanish"])))
async def send_shop_qr_code(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    shop = await db.get_shop_by_admin(message.from_user.id)
    if not shop:
        from keyboards.admin_kb import get_open_store_kb
        await message.answer(
            "⚠️ Sizda hali faol qarz daftari ochilmagan.\n"
            "Daftaringizni ochish uchun quyidagi tugmani tanlang 👇",
            reply_markup=get_open_store_kb()
        )
        return
    
    bot_info = await bot.get_me()
    from urllib.parse import quote
    shop_link = f"https://t.me/{bot_info.username}?start=shop_{shop['id']}"
    share_url = f"https://t.me/share/url?url={quote(shop_link)}&text={quote('Assalomu alaykum! «' + shop['name'] + '» dagi qarz va hisob-kitoblarimizni kuzatib borish uchun ushbu botga kiring:')}"
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    share_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Qarzdorlarga Telegramdan yuborish", url=share_url)],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_main")]
        ]
    )
    
    caption = (
        f"📒 <b>«{shop['name']}»</b> — Maxsus Ulanish QR Kodi\n\n"
        f"📌 Ushbu QR kodni qarzdorlaringizga berishingiz yoki chop etib qo'yishingiz mumkin.\n"
        f"Ular telefon kamerasida skaner qilib botga ulanishadi va o'z qarzlarini ko'rib borishadi.\n\n"
        f"🔗 <b>To'g'ridan-to'g'ri havola:</b>\n<code>{shop_link}</code>"
    )
    
    sent = False
    # 1-usul: Mahalliy generator
    try:
        qr_bio = generate_shop_qr(bot_info.username, shop['id'])
        photo_file = BufferedInputFile(qr_bio.getvalue(), filename=f"shop_{shop['id']}.png")
        await message.answer_photo(photo=photo_file, caption=caption, reply_markup=share_kb, parse_mode="HTML")
        sent = True
    except Exception as e:
        pass
        
    # 2-usul: Onlayn ultra tezkor QR server
    if not sent:
        try:
            qr_online_url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={quote(shop_link)}"
            await message.answer_photo(photo=qr_online_url, caption=caption, reply_markup=share_kb, parse_mode="HTML")
            sent = True
        except Exception:
            pass
            
    # 3-usul: Matn va tugma
    if not sent:
        await message.answer(caption, reply_markup=share_kb, parse_mode="HTML")

def build_stats_message(shop_name: str, stats: dict) -> str:
    period_names = {
        'today': '📅 Bugungi hisobot',
        'week': '🗓 Oxirgi 7 kunlik hisobot',
        'month': '📆 Oxirgi 30 kunlik hisobot',
        'all': '📊 Barcha vaqt bo‘yicha umumiy hisobot'
    }
    period_title = period_names.get(stats['period'], '📊 Hisobot')
    ledger_type = stats.get('ledger_type', 'receivable')
    is_payable = (ledger_type == 'payable')
    
    top_text = ""
    if stats['top_debtors']:
        top_title = "🏆 <b>Eng katta haqdorlar (TOP):</b>\n" if is_payable else "🏆 <b>Eng katta qarzdorlar (TOP):</b>\n"
        top_text = f"\n{top_title}"
        for i, d in enumerate(stats['top_debtors'], 1):
            d_bal_uzs = d.get('balance', 0.0) or 0.0
            d_bal_usd = d.get('balance_usd', 0.0) or 0.0
            if d_bal_uzs > 0 and d_bal_usd > 0:
                d_str = f"{format_money(d_bal_uzs, 'UZS')} | {format_money(d_bal_usd, 'USD')}"
            elif d_bal_usd > 0:
                d_str = format_money(d_bal_usd, 'USD')
            else:
                d_str = format_money(d_bal_uzs, 'UZS')
            top_text += f"{i}. 👤 {d['full_name']} — <b>{d_str}</b>\n"
    else:
        empty_msg = "(Hozircha hech kimga qarz mavjud emas)" if is_payable else "(Hozircha hech kimda faol qarz yo'q)"
        top_text = f"\n<i>{empty_msg}</i>\n"

    tot_uzs = stats.get('total_debt', 0.0) or 0.0
    tot_usd = stats.get('total_debt_usd', 0.0) or 0.0
    if tot_uzs > 0 and tot_usd > 0:
        tot_summary = f"{format_money(tot_uzs, 'UZS')} | {format_money(tot_usd, 'USD')}"
    elif tot_usd > 0:
        tot_summary = format_money(tot_usd, 'USD')
    else:
        tot_summary = format_money(tot_uzs, 'UZS')

    if is_payable:
        header = f"🔴 <b>{shop_name} — Mening qarzlarim (Berishim kerak) statistikasi</b>"
        active_label = "🔴 <b>Berishim kerak bo'lgan jami qarz:</b>"
        tx_debt_label = "➕ Olingan yangi qarz"
        tx_pay_label = "➖ Qaytarilgan to'lov"
        person_group = "Haqdorlar (Qarz beruvchilar)"
        active_person_label = "Hali to'lanmagan haqdorlar"
    else:
        header = f"🟢 <b>{shop_name} — Menga qarzlar (Olishim kerak) statistikasi</b>"
        active_label = "🟢 <b>Olishim kerak bo'lgan jami qarz:</b>"
        tx_debt_label = "➕ Berilgan yangi qarz"
        tx_pay_label = "➖ Undirilgan to'lov"
        person_group = "Mijozlar / Qarzdorlar"
        active_person_label = "Qarzda turganlar"

    return (
        f"{header}\n"
        f"<b>{period_title}</b>\n"
        f"────────────────────\n"
        f"{active_label} <b>{tot_summary}</b>\n\n"
        f"📈 <b>Tanlangan davr bo'yicha:</b>\n"
        f"• {tx_debt_label}: <b>+{format_money(stats['period_debt'])}</b>\n"
        f"• {tx_pay_label}: <b>-{format_money(stats['period_payment'])}</b>\n"
        f"• 🔄 Operatsiyalar soni: <b>{stats['total_tx_count']} ta</b>\n\n"
        f"👥 <b>{person_group} holati:</b>\n"
        f"• Jami: <b>{stats['total_customers']} nafar</b>\n"
        f"• ⚠️ {active_person_label}: <b>{stats['indebted_customers']} nafar</b>\n"
        f"• ✅ Qarzi uzilganlar: <b>{stats['clear_customers']} nafar</b>\n"
        f"{top_text}\n"
        f"👇 <i>Boshqa davrni ko'rish uchun quyidagi tugmalarni bosing:</i>"
    )

@router.message(StateFilter('*'), F.text.func(lambda t: t and "statistika" in t.lower()))
async def show_shop_statistics(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    shop = await db.get_shop_by_admin(user_id)
    if not shop:
        return
    
    mode = get_user_ledger_mode(user_id)
    stats = await db.get_detailed_shop_statistics(shop['id'], period='all', ledger_type=mode)
    text = build_stats_message(shop['name'], stats)
    kb = get_stats_period_kb(current_period='all')
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("stat_"))
async def switch_stats_period(call: CallbackQuery):
    period = call.data.replace("stat_", "")
    user_id = call.from_user.id
    shop = await db.get_shop_by_admin(user_id)
    if not shop:
        await call.answer()
        return
        
    mode = get_user_ledger_mode(user_id)
    stats = await db.get_detailed_shop_statistics(shop['id'], period=period, ledger_type=mode)
    text = build_stats_message(shop['name'], stats)
    kb = get_stats_period_kb(current_period=period)
    
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await call.answer()

# ==================== MIJOZLAR / HAQDORLAR RO'YXATI VA FILTR ====================

@router.message(StateFilter('*'), F.text.func(lambda t: t and any(k in t.lower() for k in ["ro'yxat", "qarzdorlar", "haqdorlar"]) and not any(k in t.lower() for k in ["yangi", "qo'shish", "qarz olish"])))
async def list_customers_cmd(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    shop = await db.get_shop_by_admin(user_id)
    if not shop:
        from keyboards.admin_kb import get_open_store_kb
        await message.answer(
            "⚠️ Sizda hali faol qarz daftari ochilmagan.\n"
            "Daftaringizni ochish uchun quyidagi tugmani tanlang 👇",
            reply_markup=get_open_store_kb()
        )
        return
    
    mode = get_user_ledger_mode(user_id)
    customers = await db.list_shop_customers(shop['id'], sort_by_debt=True, ledger_type=mode)
    
    if not customers:
        if mode == 'payable':
            await message.answer("Sizda hali qarz beruvchilar (haqdorlar) mavjud emas.\n'➕ Yangi qarz olish (Haqdor)' tugmasi orqali qo'shishingiz mumkin.")
        else:
            await message.answer("Sizda hali qarzdorlar mavjud emas.\n'➕ Yangi qo'shish' tugmasi orqali qo'shishingiz yoki QR kodni berishingiz mumkin.")
        return
    
    kb = get_customers_list_kb(customers, page=0)
    title = "📋 <b>Haqdorlar (Qarz beruvchilar) ro'yxati</b>:" if mode == 'payable' else "📋 <b>Qarzdorlar ro'yxati</b> (Eng katta qarz egalari tepada):"
    await message.answer(f"{title}\nKerakli shaxsni tanlang:", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("page_"))
async def paginate_customers(call: CallbackQuery):
    page = int(call.data.split("_")[1])
    user_id = call.from_user.id
    shop = await db.get_shop_by_admin(user_id)
    if not shop:
        await call.answer()
        return
    
    mode = get_user_ledger_mode(user_id)
    customers = await db.list_shop_customers(shop['id'], sort_by_debt=True, ledger_type=mode)
    kb = get_customers_list_kb(customers, page=page)
    await call.message.edit_reply_markup(reply_markup=kb)
    await call.answer()

@router.callback_query(F.data == "back_to_list")
async def back_to_customers_list(call: CallbackQuery):
    user_id = call.from_user.id
    shop = await db.get_shop_by_admin(user_id)
    if not shop:
        await call.answer()
        return
    
    mode = get_user_ledger_mode(user_id)
    customers = await db.list_shop_customers(shop['id'], sort_by_debt=True, ledger_type=mode)
    kb = get_customers_list_kb(customers, page=0)
    title = "📋 <b>Haqdorlar ro'yxati:</b>" if mode == 'payable' else "📋 <b>Qarzdorlar ro'yxati:</b>"
    await call.message.edit_text(title, reply_markup=kb, parse_mode="HTML")
    await call.answer()

# ==================== MIJOZNI KO'RISH ====================

from keyboards.admin_kb import get_due_date_select_kb

@router.callback_query(F.data.startswith("view_cust_"))
async def view_customer_detail(call: CallbackQuery, bot: Bot):
    try:
        customer_id = int(call.data.split("_")[2])
        customer = await db.get_customer(customer_id)
        if not customer:
            await call.answer("Mijoz topilmadi!", show_alert=True)
            return
        
        import html
        bot_info = await bot.get_me()
        status_tg = "✅ Telegram ulangan" if customer.get('telegram_id') else "❌ Telegram hali ulanmagan"
        phone_text = str(customer['phone']) if customer.get('phone') else "Kiritilmagan"
        due_str = str(customer['due_date'])[:10] if customer.get('due_date') else None
        
        ledger_type = customer.get('ledger_type', 'receivable')
        person_label = "Haqdor (Qarz beruvchi)" if ledger_type == 'payable' else "Mijoz / Qarzdor"
        due_label = "Qaytarish muddati" if ledger_type == 'payable' else "To'lov muddati"
        due_display = f"📅 <b>{due_label}:</b> <code>{due_str}</code> gacha\n" if due_str else ""
        
        safe_name = html.escape(str(customer.get('full_name', 'Mijoz')))
        safe_phone = html.escape(phone_text)
        
        bal_uzs = customer.get('balance', 0.0) or 0.0
        bal_usd = customer.get('balance_usd', 0.0) or 0.0
        
        if bal_uzs > 0 and bal_usd > 0:
            balance_display = f"💰 <b>So'm qarzi:</b> <b>{format_money(bal_uzs, 'UZS')}</b>\n💵 <b>Dollar qarzi:</b> <b>{format_money(bal_usd, 'USD')}</b>"
        elif bal_usd > 0:
            balance_display = f"💵 <b>Joriy qarz balansi:</b> <b>{format_money(bal_usd, 'USD')}</b>"
        else:
            balance_display = f"💰 <b>Joriy qarz balansi:</b> <b>{format_money(bal_uzs, 'UZS')}</b>"
            
        text = (
            f"👤 <b>{person_label}:</b> {safe_name}\n"
            f"📞 <b>Telefon:</b> <code>{safe_phone}</code>\n"
            f"📱 <b>Holat:</b> {status_tg}\n"
            f"{due_display}"
            f"{balance_display}\n\n"
            f"Quyidagi amallardan birini tanlang:"
        )
        kb = get_customer_actions_kb(
            customer_id=customer_id, 
            bot_username=bot_info.username, 
            shop_id=customer['shop_id'], 
            phone=customer.get('phone'),
            telegram_id=customer.get('telegram_id'),
            due_date_str=due_str,
            ledger_type=ledger_type
        )
        try:
            await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
        await call.answer()
    except Exception as e:
        logger.error(f"view_customer_detail xatosi: {e}")
        await call.answer(f"⚠️ Xatolik: {e}", show_alert=True)

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
    shop_name = shop['name'] if shop else "Qarz beruvchi"
    
    if not customer['telegram_id']:
        await call.answer("⚠️ Qarzdor hali botga ulanmagan! Pastdagi '📲 SMS shabloni' orqali yuborishingiz mumkin.", show_alert=True)
        return
        
    # Madaniyatli va rasmiy eslatma matni
    reminder_msg = (
        f"🔔 <b>Hurmatli {customer['full_name']}!</b>\n\n"
        f"<b>«{shop_name}»</b> dagi qarz va nasiya hisobingiz bo'yicha joriy qoldiq: <b>{format_money(customer['balance'])}</b>.\n\n"
        f"💳 <i>Imkoningiz bo'lganda to'lovni amalga oshirishingizni so'raymiz. Rahmat!</i>\n\n"
        f"💬 <a href='tg://user?id={shop['admin_id']}'>Qarz beruvchi bilan bog'lanish</a>"
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
        await call.answer("Qarzdor topilmadi!", show_alert=True)
        return
        
    text = (
        f"📅 <b>{customer['full_name']}</b> uchun to'lov muddatini tanlang:\n\n"
        f"<i>(Belgilangan muddat kelganda bot qarzdorga avtomatik eslatma yuboradi)</i>"
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
        await call.answer("Qarzdor topilmadi!", show_alert=True)
        return
        
    shop = await db.get_shop_by_id(customer['shop_id'])
    shop_name = shop['name'] if shop else "Qarz beruvchi"
    phone = customer['phone'] or ""
    
    bal_u = customer.get('balance', 0.0) or 0.0
    bal_d = customer.get('balance_usd', 0.0) or 0.0
    if bal_u > 0 and bal_d > 0:
        cust_bal_text = f"{format_money(bal_u, 'UZS')} va {format_money(bal_d, 'USD')}"
    elif bal_d > 0:
        cust_bal_text = format_money(bal_d, 'USD')
    else:
        cust_bal_text = format_money(bal_u, 'UZS')
        
    sms_text = (
        f"Assalomu alaykum, {customer['full_name']}! "
        f"'{shop_name}' dagi qarz/nasiya hisobingiz: {cust_bal_text}. "
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
        f"📲 <b>Qarzdor uchun tayyor SMS shabloni:</b>\n\n"
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
            curr = t.get('currency', 'UZS') or 'UZS'
            text += f"{icon} {format_money(t['amount'], curr)}{desc}\n📅 <i>{date_str}</i>\n───────────────\n"
            
    bal_u = customer.get('balance', 0.0) or 0.0
    bal_d = customer.get('balance_usd', 0.0) or 0.0
    if bal_u > 0 and bal_d > 0:
        total_bal_str = f"{format_money(bal_u, 'UZS')} | {format_money(bal_d, 'USD')}"
    elif bal_d > 0:
        total_bal_str = format_money(bal_d, 'USD')
    else:
        total_bal_str = format_money(bal_u, 'UZS')
        
    text += f"\n💰 <b>Jami qoldiq qarz: {total_bal_str}</b>"
    
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

# ==================== YANGI QARZDOR QO'SHISH ====================

@router.message(StateFilter('*'), F.text.func(lambda t: t and any(k in t.lower() for k in ["yangi qo'shish", "yangi qarz", "yangi", "qo'shish", "qarz olish"])))
async def add_customer_start(message: Message, state: FSMContext):
    mode = get_user_ledger_mode(message.from_user.id)
    await state.set_state(AdminStates.add_customer_name)
    await state.update_data(ledger_type=mode)
    
    if mode == 'payable':
        prompt_name = "👤 <b>Yangi haqdorning (Qarz beruvchi shaxs yoki do'kon) Ismini kiriting:</b>\n<i>(Masalan: Akmal aka, Rayhon Market, Jamshid)</i>"
    else:
        prompt_name = "👤 <b>Yangi qarzdorning Ism va Familiyasini kiriting:</b>\n<i>(Masalan: Jamshid Karimov yoki Rustam)</i>"
        
    await message.answer(prompt_name, parse_mode="HTML", reply_markup=get_cancel_kb())

@router.callback_query(F.data == "manual_add_cust")
async def start_manual_customer_add(call: CallbackQuery, state: FSMContext):
    mode = get_user_ledger_mode(call.from_user.id)
    await state.set_state(AdminStates.add_customer_name)
    await state.update_data(ledger_type=mode)
    
    if mode == 'payable':
        prompt_name = "👤 <b>Yangi haqdorning (Qarz beruvchi shaxs yoki do'kon) Ismini kiriting:</b>\n<i>(Masalan: Akmal aka, Rayhon Market, Jamshid)</i>"
    else:
        prompt_name = "👤 <b>Yangi qarzdorning Ism va Familiyasini kiriting:</b>\n<i>(Masalan: Jamshid Karimov yoki Rustam)</i>"
        
    await call.message.answer(prompt_name, parse_mode="HTML", reply_markup=get_cancel_kb())
    await call.answer()

@router.message(AdminStates.add_customer_name)
async def process_customer_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Iltimos, haqiqiy ism kiriting:")
        return
        
    data = await state.get_data()
    mode = data.get('ledger_type') or get_user_ledger_mode(message.from_user.id)
    await state.update_data(full_name=name, ledger_type=mode)
    await state.set_state(AdminStates.add_customer_phone)
    
    person_role = "Haqdor (Qarz beruvchi)" if mode == 'payable' else "Qarzdor"
    from keyboards.admin_kb import get_phone_input_kb
    await message.answer(
        f"👤 {person_role}: <b>{name}</b>\n\n"
        f"📞 Endi uning <b>telefon raqamini</b> yozing:\n"
        f"<i>(Masalan: +998 90 123 45 67 yoki 901234567)</i>\n\n"
        f"💡 <i>Agar telefon raqami hozir bo'lmasa, pastdagi <b>«⏩ Raqamsiz davom etish»</b> tugmasini bosing:</i>",
        parse_mode="HTML",
        reply_markup=get_phone_input_kb()
    )

@router.message(AdminStates.add_customer_phone)
async def process_customer_phone(message: Message, state: FSMContext, bot: Bot):
    try:
        if message.contact:
            phone = message.contact.phone_number
            if not phone.startswith("+"):
                phone = "+" + phone
        else:
            phone_raw = message.text.strip() if message.text else ""
            if phone_raw in ["-", "⏩ Raqamsiz davom etish", "Raqamsiz davom etish", "raqamsiz"]:
                phone = None
            else:
                phone = phone_raw
        
        data = await state.get_data()
        full_name = data.get('full_name', 'Mijoz')
        mode = data.get('ledger_type') or get_user_ledger_mode(message.from_user.id)
        
        shop = await db.get_shop_by_admin(message.from_user.id)
        if not shop:
            await message.answer("⚠️ Daftaringiz topilmadi. Iltimos /start ni bosing.")
            await state.clear()
            return
            
        cust_id = await db.add_customer(shop['id'], full_name, phone, ledger_type=mode)
        await state.clear()
        
        bot_info = await bot.get_me()
        is_sa = message.from_user.id in config.SUPER_ADMIN_IDS
        is_valid, days_left, _ = await db.check_shop_subscription(shop['id'])
        
        import html
        safe_name = html.escape(full_name)
        safe_phone = html.escape(phone) if phone else "Kiritilmadi"
        
        if mode == 'payable':
            success_title = "🎉 <b>Yangi haqdor muvaffaqiyatli qo'shildi!</b>"
            action_prompt = f"👇 <b>{safe_name}</b> dan yangi qarz olish yoki amalni tanlang:"
        else:
            success_title = "🎉 <b>Yangi qarzdor muvaffaqiyatli qo'shildi!</b>"
            action_prompt = f"👇 <b>{safe_name}</b> ga qarz yozish yoki amalni tanlang:"
            
        await message.answer(
            f"{success_title}\n\n"
            f"👤 Ismi: <b>{safe_name}</b>\n"
            f"📞 Telefoni: <code>{safe_phone}</code>\n"
            f"💰 Joriy qarzi: <b>0 so'm</b>",
            parse_mode="HTML",
            reply_markup=get_admin_main_kb(is_sa, days_left=days_left, ledger_type=mode)
        )
        
        kb = get_customer_actions_kb(cust_id, bot_info.username, shop['id'], phone, ledger_type=mode)
        await message.answer(
            action_prompt,
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"⚠️ Xatolik yuz berdi: {e}")
        await state.clear()

# ==================== QARZ YOZISH (SUMMA + IZOH) ====================

from keyboards.admin_kb import get_currency_select_kb

@router.callback_query(F.data.startswith("debt_"))
async def start_add_debt(call: CallbackQuery, state: FSMContext):
    customer_id = int(call.data.split("_")[1])
    customer = await db.get_customer(customer_id)
    if not customer:
        await call.answer("Mijoz topilmadi!", show_alert=True)
        return
    
    await state.clear()
    await call.message.edit_text(
        f"➕ <b>{customer['full_name']}</b> ga qarz yozish uchun <b>valyutani tanlang</b>:",
        reply_markup=get_currency_select_kb("debt", customer_id),
        parse_mode="HTML"
    )
    await call.answer()

@router.callback_query(F.data.startswith("curr_debt_"))
async def process_debt_currency_choice(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    customer_id = int(parts[2])
    currency = parts[3] # 'UZS' or 'USD'
    
    customer = await db.get_customer(customer_id)
    if not customer:
        await call.answer("Mijoz topilmadi!", show_alert=True)
        return
        
    curr_label = "🇺🇸 AQSH Dollari ($)" if currency == 'USD' else "🇺🇿 O'zbek So'mi"
    example_val = "150 yoki 20.5" if currency == 'USD' else "50000 yoki 1500000"
    
    await state.set_state(AdminStates.add_debt_amount)
    await state.update_data(customer_id=customer_id, customer_name=customer['full_name'], currency=currency)
    
    await call.message.answer(
        f"➕ <b>{customer['full_name']}</b> ga qarz summasini kiriting ({curr_label}):\n"
        f"<i>(Masalan: {example_val})</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_kb()
    )
    await call.answer()

@router.message(AdminStates.add_debt_amount)
async def process_debt_amount(message: Message, state: FSMContext):
    text = message.text.replace(" ", "").replace(",", ".").replace("$", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Iltimos, to'g'ri musbat summa kiriting (masalan: 100 yoki 100000):")
        return
    
    data = await state.get_data()
    currency = data.get('currency', 'UZS')
    
    await state.update_data(debt_amount=amount)
    await state.set_state(AdminStates.add_debt_desc)
    from keyboards.admin_kb import get_desc_input_kb
    await message.answer(
        f"Summa: <b>{format_money(amount, currency)}</b>\n\n"
        f"📝 <b>Qarz sababi, tovar yoki xizmat izohini yozing:</b>\n"
        f"<i>(Masalan: Kiyim, Zapchast, Sement, Remont, Ijara, Do'stona qarz)</i>\n\n"
        f"💡 <i>Agar izoh kerak bo'lmasa, pastdagi <b>«⏩ Izohsiz saqlash»</b> tugmasini bosing:</i>",
        parse_mode="HTML",
        reply_markup=get_desc_input_kb()
    )

@router.message(AdminStates.add_debt_desc)
async def process_debt_description(message: Message, state: FSMContext, bot: Bot):
    desc_raw = message.text.strip()
    if desc_raw in ["-", "⏩ Izohsiz saqlash", "Izohsiz saqlash", "izohsiz"]:
        desc = None
    else:
        desc = desc_raw
    
    data = await state.get_data()
    currency = data.get('currency', 'UZS')
    shop = await db.get_shop_by_admin(message.from_user.id)
    
    updated_customer = await db.add_transaction(
        shop_id=shop['id'],
        customer_id=data['customer_id'],
        amount=data['debt_amount'],
        tx_type='debt',
        description=desc,
        currency=currency
    )
    
    await state.clear()
    is_sa = message.from_user.id in config.SUPER_ADMIN_IDS
    bot_info = await bot.get_me()
    
    import html
    from urllib.parse import quote
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    safe_name = html.escape(str(updated_customer['full_name']))
    
    bal_uzs = updated_customer.get('balance', 0.0) or 0.0
    bal_usd = updated_customer.get('balance_usd', 0.0) or 0.0
    if bal_uzs > 0 and bal_usd > 0:
        balance_summary = f"{format_money(bal_uzs, 'UZS')} | {format_money(bal_usd, 'USD')}"
    elif bal_usd > 0:
        balance_summary = format_money(bal_usd, 'USD')
    else:
        balance_summary = format_money(bal_uzs, 'UZS')
    
    ledger_type = updated_customer.get('ledger_type', 'receivable')
    is_payable = (ledger_type == 'payable')
    is_valid, days_left, _ = await db.check_shop_subscription(shop['id'])
    
    if is_payable:
        msg_text = (
            f"✅ <b>Qarz muvaffaqiyatli qayd etildi!</b>\n\n"
            f"👤 Haqdor (Qarz beruvchi): <b>{safe_name}</b>\n"
            f"➕ Olingan qarz summasi: <b>{format_money(data['debt_amount'], currency)}</b>\n"
            f"📝 Izoh / Sabab: <i>{html.escape(desc) if desc else 'Kiritilmadi'}</i>\n"
            f"💰 Sizning unga jami qarz balansingiz: <b>{balance_summary}</b>"
        )
    else:
        msg_text = (
            f"✅ <b>Qarz / Nasiya muvaffaqiyatli yozildi!</b>\n\n"
            f"👤 Qarzdor/Mijoz: <b>{safe_name}</b>\n"
            f"➕ Qo'shilgan summa: <b>{format_money(data['debt_amount'], currency)}</b>\n"
            f"📝 Izoh / Sabab: <i>{html.escape(desc) if desc else 'Kiritilmadi'}</i>\n"
            f"💰 Jami qarz balansi: <b>{balance_summary}</b>"
        )
    
    # Agar mijoz hali botga ulanmagan bo'lsa, Telegram orqali yuborish tugmasini chiqaramiz
    notify_kb = None
    if not updated_customer.get('telegram_id'):
        cust_link = f"https://t.me/{bot_info.username}?start=c_{updated_customer['id']}"
        if is_payable:
            share_text = (
                f"Assalomu alaykum, {updated_customer['full_name']}!\n\n"
                f"«{shop['name']}» dan hisob-kitob:\n"
                f"Men sizdan yangi qarz oldim: +{format_money(data['debt_amount'], currency)}\n"
                f"📝 Izoh: {desc or 'Qarz'}\n"
                f"💰 Sizga berishim kerak bo'lgan jami qarzim: {balance_summary}\n\n"
                f"Hisob-kitobni bot orqali kuzatib borish uchun ushbu havolani bosing:\n{cust_link}"
            )
            share_btn_text = "📤 Haqdorga hisobotni yuborish"
        else:
            share_text = (
                f"Assalomu alaykum, {updated_customer['full_name']}!\n\n"
                f"«{shop['name']}» da sizning hisobingizga yangi qarz/nasiya yozildi: +{format_money(data['debt_amount'], currency)}\n"
                f"📝 Izoh: {desc or 'Xarid'}\n"
                f"💰 Jami qarzingiz: {balance_summary}\n\n"
                f"Hisob-kitobni bot orqali kuzatib borish uchun ushbu havolani bosing:\n{cust_link}"
            )
            share_btn_text = "📤 Qarzdorga Telegramdan hisobni yuborish"
            
        share_url = f"https://t.me/share/url?url={quote(cust_link)}&text={quote(share_text)}"
        notify_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=share_btn_text, url=share_url)],
                [InlineKeyboardButton(text="👤 Sahifasini ochish", callback_data=f"view_cust_{updated_customer['id']}")]
            ]
        )
    else:
        # Allaqachon ulangan bo'lsa avtomatik xabar ketadi
        try:
            if is_payable:
                client_notify = (
                    f"📌 <b>«{shop['name']}»</b> hisobingizdan xabar:\n\n"
                    f"Sizdan yangi qarz olindi: <b>+{format_money(data['debt_amount'], currency)}</b>\n"
                    f"📝 Izoh / Sabab: <i>{html.escape(desc) if desc else 'Kiritilmadi'}</i>\n"
                    f"💰 Sizga qaytarilishi kerak bo'lgan jami balans: <b>{balance_summary}</b>\n\n"
                    f"💬 <a href='tg://user?id={shop['admin_id']}'>Bog'lanish</a>"
                )
            else:
                client_notify = (
                    f"📌 <b>«{shop['name']}»</b> hisobingizdan xabar:\n\n"
                    f"Sizning hisobingizga yangi qarz / nasiya yozildi: <b>+{format_money(data['debt_amount'], currency)}</b>\n"
                    f"📝 Izoh / Sabab: <i>{html.escape(desc) if desc else 'Kiritilmadi'}</i>\n"
                    f"💰 Sizning jami balansingiz: <b>{balance_summary}</b>\n\n"
                    f"💬 <a href='tg://user?id={shop['admin_id']}'>Bog'lanish</a>"
                )
            await bot.send_message(chat_id=updated_customer['telegram_id'], text=client_notify, parse_mode="HTML")
        except Exception:
            pass

    await message.answer(msg_text, parse_mode="HTML", reply_markup=notify_kb or get_admin_main_kb(is_sa, days_left=days_left, ledger_type=ledger_type))
    if notify_kb:
        await message.answer("Boshqaruv menyusi:", reply_markup=get_admin_main_kb(is_sa, days_left=days_left, ledger_type=ledger_type))

# ==================== TO'LOV QABUL QILISH / TO'LOV QILISH ====================

@router.callback_query(F.data.startswith("pay_"))
async def start_add_payment(call: CallbackQuery, state: FSMContext):
    customer_id = int(call.data.split("_")[1])
    customer = await db.get_customer(customer_id)
    if not customer:
        await call.answer("Mijoz topilmadi!", show_alert=True)
        return
    
    await state.clear()
    ledger_type = customer.get('ledger_type', 'receivable')
    prompt_text = f"➖ <b>{customer['full_name']}</b> ga qarzni to'lash uchun <b>valyutani tanlang</b>:" if ledger_type == 'payable' else f"➖ <b>{customer['full_name']}</b> dan to'lov qabul qilish uchun <b>valyutani tanlang</b>:"
    
    await call.message.edit_text(
        prompt_text,
        reply_markup=get_currency_select_kb("pay", customer_id),
        parse_mode="HTML"
    )
    await call.answer()

@router.callback_query(F.data.startswith("curr_pay_"))
async def process_pay_currency_choice(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    customer_id = int(parts[2])
    currency = parts[3] # 'UZS' or 'USD'
    
    customer = await db.get_customer(customer_id)
    if not customer:
        await call.answer("Mijoz topilmadi!", show_alert=True)
        return
        
    curr_label = "🇺🇸 AQSH Dollari ($)" if currency == 'USD' else "🇺🇿 O'zbek So'mi"
    curr_balance = customer.get('balance_usd', 0.0) if currency == 'USD' else customer.get('balance', 0.0)
    example_val = "100 yoki 50.5" if currency == 'USD' else "50000 yoki 1500000"
    
    ledger_type = customer.get('ledger_type', 'receivable')
    prompt_q = f"➖ <b>{customer['full_name']}</b> ga qancha to'lov qildingiz? ({curr_label}):" if ledger_type == 'payable' else f"➖ <b>{customer['full_name']}</b> qancha to'lov qildi? ({curr_label}):"
    
    await state.set_state(AdminStates.add_payment_amount)
    await state.update_data(customer_id=customer_id, currency=currency)
    
    await call.message.answer(
        f"{prompt_q}\n"
        f"<i>(Masalan: {example_val})</i>\n"
        f"Hozirgi umumiy qarz: <b>{format_money(curr_balance, currency)}</b>",
        parse_mode="HTML",
        reply_markup=get_cancel_kb()
    )
    await call.answer()

@router.message(AdminStates.add_payment_amount)
async def process_payment_amount(message: Message, state: FSMContext, bot: Bot):
    text = message.text.replace(" ", "").replace(",", ".").replace("$", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Iltimos, to'g'ri musbat to'lov summasini kiriting (masalan: 50 yoki 50000):")
        return
    
    data = await state.get_data()
    currency = data.get('currency', 'UZS')
    shop = await db.get_shop_by_admin(message.from_user.id)
    
    updated_customer = await db.add_transaction(
        shop_id=shop['id'],
        customer_id=data['customer_id'],
        amount=amount,
        tx_type='payment',
        description="Qarz to'lovi",
        currency=currency
    )
    
    await state.clear()
    is_sa = message.from_user.id in config.SUPER_ADMIN_IDS
    is_valid, days_left, _ = await db.check_shop_subscription(shop['id'])
    bot_info = await bot.get_me()
    
    import html
    from urllib.parse import quote
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    safe_name = html.escape(str(updated_customer['full_name']))
    
    bal_uzs = updated_customer.get('balance', 0.0) or 0.0
    bal_usd = updated_customer.get('balance_usd', 0.0) or 0.0
    if bal_uzs > 0 and bal_usd > 0:
        balance_summary = f"{format_money(bal_uzs, 'UZS')} | {format_money(bal_usd, 'USD')}"
    elif bal_usd > 0:
        balance_summary = format_money(bal_usd, 'USD')
    else:
        balance_summary = format_money(bal_uzs, 'UZS')
    
    ledger_type = updated_customer.get('ledger_type', 'receivable')
    is_payable = (ledger_type == 'payable')
    
    if is_payable:
        msg_text = (
            f"✅ <b>To'lov qayd etildi!</b>\n\n"
            f"👤 Haqdor: <b>{safe_name}</b>\n"
            f"➖ Qaytarilgan to'lov: <b>{format_money(amount, currency)}</b>\n"
            f"💰 Sizning unga qolgan qarz balansingiz: <b>{balance_summary}</b>"
        )
    else:
        msg_text = (
            f"✅ <b>To'lov qabul qilindi!</b>\n\n"
            f"👤 Mijoz: <b>{safe_name}</b>\n"
            f"➖ Qabul qilingan to'lov: <b>{format_money(amount, currency)}</b>\n"
            f"💰 Qolgan qarz balansi: <b>{balance_summary}</b>"
        )
    
    # Agar mijoz hali ulanmagan bo'lsa, Telegramdan to'lov chekini jo'natish tugmasi
    notify_kb = None
    if not updated_customer.get('telegram_id'):
        cust_link = f"https://t.me/{bot_info.username}?start=c_{updated_customer['id']}"
        if is_payable:
            share_text = (
                f"Assalomu alaykum, {updated_customer['full_name']}!\n\n"
                f"«{shop['name']}» dan hisob-kitob:\n"
                f"Sizga {format_money(amount, currency)} to'lov qaytarildi.\n"
                f"💰 Qolgan qarz balansi: {balance_summary}\n"
                f"Rahmat!\n\n"
                f"Hisobingizni botda kuzatib borish uchun:\n{cust_link}"
            )
            share_btn_text = "📤 Haqdorga to'lov chekini yuborish"
        else:
            share_text = (
                f"Assalomu alaykum, {updated_customer['full_name']}!\n\n"
                f"«{shop['name']}» da sizning {format_money(amount, currency)} to'lovingiz qabul qilindi.\n"
                f"💰 Qolgan qarz balansingiz: {balance_summary}\n"
                f"Rahmat!\n\n"
                f"Hisobingizni botda kuzatib borish uchun:\n{cust_link}"
            )
            share_btn_text = "📤 Qarzdorga Telegramdan to'lov chekini yuborish"
            
        share_url = f"https://t.me/share/url?url={quote(cust_link)}&text={quote(share_text)}"
        notify_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=share_btn_text, url=share_url)],
                [InlineKeyboardButton(text="👤 Sahifasini ochish", callback_data=f"view_cust_{updated_customer['id']}")]
            ]
        )
    else:
        try:
            if is_payable:
                client_notify = (
                    f"✅ <b>«{shop['name']}»</b> hisobingizdan xabar:\n\n"
                    f"Sizga <b>{format_money(amount, currency)}</b> qarz qaytarildi.\n"
                    f"💰 Qolgan qarz balansi: <b>{balance_summary}</b>\n"
                    f"Rahmat!\n\n"
                    f"💬 <a href='tg://user?id={shop['admin_id']}'>Bog'lanish</a>"
                )
            else:
                client_notify = (
                    f"✅ <b>«{shop['name']}»</b> hisobingizdan xabar:\n\n"
                    f"Sizning <b>{format_money(amount, currency)}</b> to'lovingiz qabul qilindi.\n"
                    f"💰 Qolgan qarz balansingiz: <b>{balance_summary}</b>\n"
                    f"Rahmat!\n\n"
                    f"💬 <a href='tg://user?id={shop['admin_id']}'>Qarz beruvchi bilan bog'lanish</a>"
                )
            await bot.send_message(chat_id=updated_customer['telegram_id'], text=client_notify, parse_mode="HTML")
        except Exception:
            pass
            
    await message.answer(msg_text, parse_mode="HTML", reply_markup=notify_kb or get_admin_main_kb(is_sa, days_left=days_left, ledger_type=ledger_type))
    if notify_kb:
        await message.answer("Boshqaruv menyusi:", reply_markup=get_admin_main_kb(is_sa, days_left=days_left, ledger_type=ledger_type))

# ==================== QIDIRUV ====================

@router.message(StateFilter('*'), F.text.func(lambda t: t and "qidir" in t.lower()))
async def search_customer_start(message: Message, state: FSMContext):
    shop = await db.get_shop_by_admin(message.from_user.id)
    if not shop:
        return
    mode = get_user_ledger_mode(message.from_user.id)
    person_type = "haqdorning" if mode == 'payable' else "qarzdorning"
    await state.set_state(AdminStates.search_customer)
    await message.answer(f"Qidirilayotgan {person_type} <b>ism yoki telefon raqamini</b> yozing:", parse_mode="HTML", reply_markup=get_cancel_kb())

@router.message(AdminStates.search_customer)
async def process_search_customer(message: Message, state: FSMContext):
    query = message.text.strip()
    user_id = message.from_user.id
    shop = await db.get_shop_by_admin(user_id)
    mode = get_user_ledger_mode(user_id)
    customers = await db.search_customers(shop['id'], query, ledger_type=mode)
    
    await state.clear()
    is_sa = user_id in config.SUPER_ADMIN_IDS
    is_valid, days_left, _ = await db.check_shop_subscription(shop['id'])
    
    if not customers:
        await message.answer(f"🔍 '{query}' bo'yicha hech kim topilmadi.", reply_markup=get_admin_main_kb(is_sa, days_left=days_left, ledger_type=mode))
        return
    
    kb = get_customers_list_kb(customers, page=0)
    await message.answer(f"🔍 '{query}' bo'yicha topilgan natijalar:", reply_markup=kb, parse_mode="HTML")
    await message.answer("Boshqaruv menyusi:", reply_markup=get_admin_main_kb(is_sa, days_left=days_left, ledger_type=mode))
