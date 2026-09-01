from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db
from keyboards.superadmin_kb import (
    get_superadmin_main_kb, get_shops_list_kb, get_shop_manage_kb
)
from keyboards.admin_kb import get_cancel_kb, get_admin_main_kb, format_money, get_contact_kb
import config

router = Router()

class SuperAdminStates(StatesGroup):
    add_shop_name = State()
    add_shop_admin_id = State()
    add_shop_phone = State()
    change_shop_admin_id = State()
    search_shop_query = State()

from aiogram.filters import StateFilter

@router.message(StateFilter('*'), F.text.in_(["❌ Bekor qilish", "/cancel"]))
async def superadmin_cancel(message: Message, state: FSMContext):
    await state.clear()
    if is_super_admin(message.from_user.id):
        await message.answer("Amal bekor qilindi.", reply_markup=get_superadmin_main_kb())
    else:
        await message.answer("Amal bekor qilindi.")

def is_super_admin(user_id: int) -> bool:
    return bool(config.SUPER_ADMIN_IDS and user_id in config.SUPER_ADMIN_IDS)

@router.message(F.text == "👑 Super Admin Paneli")
@router.message(F.text == "/superadmin")
async def superadmin_panel(message: Message):
    if not is_super_admin(message.from_user.id):
        return
    await message.answer("👑 <b>Super Admin Boshqaruv Paneli</b>\nBu yerdan yangi do'konlar ochishingiz, qidirishingiz va ularni boshqarishingiz mumkin.", reply_markup=get_superadmin_main_kb(), parse_mode="HTML")

# ==================== TEZKOR QIDIRISH VA TIKLASH ====================

@router.message(F.text == "🔍 Qidirish va Tiklash")
async def start_superadmin_search(message: Message, state: FSMContext):
    if not is_super_admin(message.from_user.id):
        return
    await state.set_state(SuperAdminStates.search_shop_query)
    text = (
        "🔍 <b>Do'kon yoki Mijozni qidirish va Tiklash:</b>\n\n"
        "Qidirilayotgan do'konning <b>Telefon raqami</b>, <b>Nomi</b> yoki <b>Telegram ID</b> sini kiriting:\n\n"
        "<i>(Masalan: <code>901234567</code> yoki <code>Baraka Market</code> yoki <code>123456789</code>)</i>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_cancel_kb())

@router.message(SuperAdminStates.search_shop_query)
async def process_superadmin_search(message: Message, state: FSMContext):
    if not is_super_admin(message.from_user.id):
        return
    q = message.text.strip()
    shops = await db.search_shops(q)
    await state.clear()
    
    if not shops:
        await message.answer(
            f"❌ «<b>{q}</b>» bo'yicha hech qanday do'kon topilmadi.\n\n"
            "Iltimos, telefon raqami yoki nomini to'g'ri kiritib qaytadan urinib ko'ring.",
            parse_mode="HTML",
            reply_markup=get_superadmin_main_kb()
        )
        return
        
    text = f"🔍 «<b>{q}</b>» bo'yicha <b>{len(shops)} ta</b> do'kon topildi:\n\n<i>Boshqarish va Tiklash uchun do'konni tanlang:</i>"
    kb = get_shops_list_kb(shops, filter_type="all")
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(F.text == "🔙 Asosiy menyu")
async def back_to_main_panel(message: Message):
    shop = await db.get_shop_by_admin(message.from_user.id)
    if shop:
        is_sa = message.from_user.id in config.SUPER_ADMIN_IDS
        await message.answer("Do'konchi paneliga qaytildi.", reply_markup=get_admin_main_kb(is_sa))
    else:
        await message.answer("Bosh sahifa.")

@router.message(F.text == "🏪 Barcha do'konlar")
async def list_shops(message: Message):
    if not is_super_admin(message.from_user.id):
        return
    shops = await db.get_detailed_shops_analysis()
    if not shops:
        await message.answer("Hozircha tizimda do'konlar mavjud emas.")
        return
    
    active_count = sum(1 for s in shops if s.get('customers_count', 0) > 0)
    passive_count = sum(1 for s in shops if s.get('customers_count', 0) == 0)
    
    text = (
        f"🏪 <b>Barcha Do'konlar Tahlili:</b>\n"
        f"• Jami do'konlar: <b>{len(shops)} ta</b>\n"
        f"• 🟢 Faol (Mijozli): <b>{active_count} ta</b>\n"
        f"• 🔴 Passiv (0 mijoz): <b>{passive_count} ta</b>\n\n"
        f"<i>Boshqarish uchun do'konni tanlang:</i>"
    )
    kb = get_shops_list_kb(shops, filter_type="all")
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("sa_filter_"))
async def filter_shops_cb(call: CallbackQuery):
    if not is_super_admin(call.from_user.id):
        return
    filter_type = call.data.replace("sa_filter_", "")
    shops = await db.get_detailed_shops_analysis()
    
    if filter_type == "active":
        filtered = [s for s in shops if s.get('customers_count', 0) > 0]
        title = "🟢 <b>Faol Do'konlar (Mijozlar ulangan):</b>"
    elif filter_type == "passive":
        filtered = [s for s in shops if s.get('customers_count', 0) == 0]
        title = "🔴 <b>Passiv Do'konlar (0 ta mijoz):</b>"
    elif filter_type == "expiring":
        filtered = [s for s in shops if (s.get('days_left') is not None and s.get('days_left') <= 7)]
        title = "⏳ <b>Obunasi 7 kundan kam qolgan do'konlar:</b>"
    else:
        filtered = shops
        title = "📋 <b>Barcha Do'konlar:</b>"
        
    text = f"{title}\nTopildi: <b>{len(filtered)} ta</b>\n\n<i>Boshqarish uchun do'konni tanlang:</i>"
    kb = get_shops_list_kb(filtered, filter_type=filter_type)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await call.answer()

@router.callback_query(F.data == "sa_back_shops")
async def back_to_shops_list(call: CallbackQuery):
    if not is_super_admin(call.from_user.id):
        return
    shops = await db.get_detailed_shops_analysis()
    active_count = sum(1 for s in shops if s.get('customers_count', 0) > 0)
    passive_count = sum(1 for s in shops if s.get('customers_count', 0) == 0)
    
    text = (
        f"🏪 <b>Barcha Do'konlar Tahlili:</b>\n"
        f"• Jami do'konlar: <b>{len(shops)} ta</b>\n"
        f"• 🟢 Faol (Mijozli): <b>{active_count} ta</b>\n"
        f"• 🔴 Passiv (0 mijoz): <b>{passive_count} ta</b>\n\n"
        f"<i>Boshqarish uchun do'konni tanlang:</i>"
    )
    kb = get_shops_list_kb(shops, filter_type="all")
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data.startswith("sa_shop_"))
async def manage_shop_detail(call: CallbackQuery):
    if not is_super_admin(call.from_user.id):
        return
    shop_id = int(call.data.split("_")[2])
    shop = await db.get_shop_by_id(shop_id)
    if not shop:
        await call.answer("Do'kon topilmadi!", show_alert=True)
        return
    
    stats = await db.get_shop_statistics(shop_id)
    is_valid, days_left, exp_date = await db.check_shop_subscription(shop_id)
    status_text = "🟢 Faol" if shop['is_active'] else "🔴 Bloklangan"
    exp_str = str(exp_date)[:10] if exp_date else "Noma'lum"
    
    text = (
        f"🏪 <b>Do'kon:</b> {shop['name']}\n"
        f"🆔 ID: {shop['id']}\n"
        f"👤 <b>Admin Telegram ID:</b> <code>{shop['admin_id']}</code>\n"
        f"📞 <b>Telefon:</b> <code>{shop['phone'] or 'Kiritilmagan'}</code>\n"
        f"⚡ <b>Holat:</b> {status_text}\n"
        f"⏳ <b>Obuna:</b> {days_left} kun qoldi (gacha: <code>{exp_str}</code>)\n\n"
        f"📊 <b>Statistika:</b>\n"
        f"• 👥 Ulangan mijozlar: <b>{stats['total_customers']} ta</b>\n"
        f"• 💰 Jami nasiya qarzlari: <b>{format_money(stats['total_debt'])}</b>\n"
    )
    await call.message.edit_text(text, reply_markup=get_shop_manage_kb(shop_id, shop['is_active']), parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data.startswith("sa_toggle_"))
async def toggle_shop_active(call: CallbackQuery):
    if not is_super_admin(call.from_user.id):
        return
    shop_id = int(call.data.split("_")[2])
    await db.toggle_shop_status(shop_id)
    shop = await db.get_shop_by_id(shop_id)
    await call.answer("Do'kon holati o'zgartirildi!")
    
    stats = await db.get_shop_statistics(shop_id)
    status_text = "🟢 Faol" if shop['is_active'] else "🔴 Bloklangan"
    text = (
        f"🏪 <b>Do'kon:</b> {shop['name']}\n"
        f"🆔 ID: {shop['id']}\n"
        f"👤 <b>Admin Telegram ID:</b> <code>{shop['admin_id']}</code>\n"
        f"⚡ <b>Holat:</b> {status_text}\n\n"
        f"📊 <b>Statistika:</b>\n"
        f"• Mijozlar: {stats['total_customers']} ta\n"
        f"• Jami nasiya: {format_money(stats['total_debt'])}\n"
    )
    await call.message.edit_text(text, reply_markup=get_shop_manage_kb(shop_id, shop['is_active']), parse_mode="HTML")

@router.callback_query(F.data.startswith("sa_chadmin_"))
async def change_admin_start(call: CallbackQuery, state: FSMContext):
    if not is_super_admin(call.from_user.id):
        return
    shop_id = int(call.data.split("_")[2])
    shop = await db.get_shop_by_id(shop_id)
    if not shop:
        await call.answer("Do'kon topilmadi!", show_alert=True)
        return
        
    await state.set_state(SuperAdminStates.change_shop_admin_id)
    await state.update_data(shop_id=shop_id)
    await call.message.answer(
        f"🔄 <b>{shop['name']}</b> do'koni uchun yangi admin <b>Telegram ID raqamini</b> kiriting:\n\n"
        f"<i>Hozirgi Admin ID:</i> <code>{shop['admin_id']}</code>",
        parse_mode="HTML",
        reply_markup=get_cancel_kb()
    )
    await call.answer()

@router.message(SuperAdminStates.change_shop_admin_id)
async def process_change_shop_admin_id(message: Message, state: FSMContext, bot: Bot):
    raw_text = message.text.strip().replace(" ", "").replace("@", "")
    try:
        new_admin_id = int(raw_text)
    except ValueError:
        await message.answer("⚠️ Iltimos, faqat raqamdan iborat Telegram ID kiriting:")
        return
        
    data = await state.get_data()
    shop_id = data['shop_id']
    shop = await db.get_shop_by_id(shop_id)
    
    await db.transfer_shop_ownership(shop_id, new_admin_id, "Do'kon egasi")
    await state.clear()
    
    await message.answer(
        f"✅ <b>Admin muvaffaqiyatli o'zgartirildi!</b>\n\n"
        f"🏪 Do'kon: <b>{shop['name']}</b>\n"
        f"🆔 Yangi Admin Telegram ID: <code>{new_admin_id}</code>\n\n"
        f"Do'konchi endi yangi profilidan <code>/start</code> ni bossa do'kon to'liq ochiladi.",
        parse_mode="HTML",
        reply_markup=get_superadmin_main_kb()
    )
    
    # Yangi adminga tabrik xabari yuborishga urinish
    try:
        is_valid, days_left, _ = await db.check_shop_subscription(shop_id)
        notify_msg = (
            f"🎉 <b>Assalomu alaykum!</b>\n\n"
            f"Super Admin tomonidan sizga <b>{shop['name']}</b> do'koni boshqaruvi biriktirildi.\n"
            f"Boshlash uchun <code>/start</code> ni bosing."
        )
        await bot.send_message(chat_id=new_admin_id, text=notify_msg, parse_mode="HTML")
    except Exception:
        pass

@router.callback_query(F.data.startswith("sa_del_"))
async def delete_shop_action(call: CallbackQuery):
    if not is_super_admin(call.from_user.id):
        return
    shop_id = int(call.data.split("_")[2])
    await db.delete_shop(shop_id)
    await call.answer("Do'kon o'chirildi!", show_alert=True)
    
    shops = await db.list_all_shops()
    if shops:
        await call.message.edit_text("🏪 <b>Mavjud do'konlar:</b>", reply_markup=get_shops_list_kb(shops), parse_mode="HTML")
    else:
        await call.message.edit_text("Do'konlar qolmadi.")

@router.callback_query(F.data == "sa_back_shops")
async def back_to_shops_list(call: CallbackQuery):
    if not is_super_admin(call.from_user.id):
        return
    shops = await db.list_all_shops()
    if shops:
        await call.message.edit_text("🏪 <b>Mavjud do'konlar:</b>", reply_markup=get_shops_list_kb(shops), parse_mode="HTML")
    await call.answer()

# ==================== YANGI DO'KON / ADMIN QO'SHISH ====================

@router.message(F.text == "➕ Yangi do'kon qo'shish")
async def start_add_shop(message: Message, state: FSMContext):
    if not is_super_admin(message.from_user.id):
        return
    await state.set_state(SuperAdminStates.add_shop_name)
    await message.answer("Yangi do'kon nomini kiriting:\n<i>(Masalan: Omad Oziq-ovqat)</i>", parse_mode="HTML", reply_markup=get_cancel_kb())

@router.message(SuperAdminStates.add_shop_name)
async def process_new_shop_name(message: Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(shop_name=name)
    await state.set_state(SuperAdminStates.add_shop_admin_id)
    
    my_id = message.from_user.id
    text = (
        f"Do'kon nomi: <b>{name}</b>\n\n"
        f"Endi do'kon egasining (Admin) <b>Telegram ID raqamini</b> kiriting.\n\n"
        f"💡 <i>Sizning Telegram ID raqamingiz:</i> <code>{my_id}</code>\n"
        f"(Agar do'konni o'zingizga ochayotgan bo'lsangiz, yuqoridagi <code>{my_id}</code> raqamini yuboring).\n\n"
        f"ℹ️ Boshqa odamning ID sini bilish uchun: unga @userinfobot ga /start bosishini ayting."
    )
    await message.answer(text, parse_mode="HTML")

@router.message(SuperAdminStates.add_shop_admin_id)
async def process_new_shop_admin_id(message: Message, state: FSMContext):
    raw_text = message.text.strip().replace(" ", "").replace("@", "")
    try:
        admin_id = int(raw_text)
    except ValueError:
        await message.answer(
            "⚠️ <b>Xatolik!</b> Telegram ID faqat raqamlardan iborat bo'ladi (Masalan: <code>123456789</code>).\n\n"
            f"Sizning ID raqamingiz: <code>{message.from_user.id}</code>\n"
            "Iltimos, faqat raqam kiriting:",
            parse_mode="HTML"
        )
        return
    
    # Ushbu admin allaqachon boshqa do'konga ega emasligini tekshirish
    existing = await db.get_shop_by_admin(admin_id)
    if existing:
        await message.answer(f"⚠️ Ushbu Telegram ID allaqachon <b>'{existing['name']}'</b> do'koniga biriktirilgan! Boshqa ID kiriting:")
        return
    
    await state.update_data(admin_id=admin_id)
    await state.set_state(SuperAdminStates.add_shop_phone)
    await message.answer(
        f"Admin Telegram ID: <code>{admin_id}</code>\n\nDo'kon telefon raqamini kiriting (yoki pastdagi tugmani bosing):",
        parse_mode="HTML",
        reply_markup=get_contact_kb()
    )

@router.message(SuperAdminStates.add_shop_phone)
async def process_new_shop_phone(message: Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
    else:
        phone_raw = message.text.strip() if message.text else ""
        phone = phone_raw if phone_raw != "-" else None
    
    data = await state.get_data()
    try:
        shop_id = await db.create_shop(data['shop_name'], data['admin_id'], phone, days=30)
        await state.clear()
        
        await message.answer(
            f"🎉 <b>Yangi do'kon muvaffaqiyatli yaratildi!</b>\n\n"
            f"🏪 Do'kon: <b>{data['shop_name']}</b>\n"
            f"🆔 ID: {shop_id}\n"
            f"👤 Admin Telegram ID: <code>{data['admin_id']}</code>\n"
            f"📞 Telefon: {phone or 'Kiritilmagan'}\n"
            f"⏳ Obuna muddati: <b>30 kun (Faol)</b>\n\n"
            f"Endi do'konchi botga kirib <code>/start</code> ni bossa, unga do'konchi paneli ochiladi.",
            parse_mode="HTML",
            reply_markup=get_superadmin_main_kb()
        )
    except Exception as e:
        await message.answer(f"⚠️ Xatolik yuz berdi: {e}\nIltimos, qaytadan urinib ko'ring yoki /cancel bosing.")

from utils.excel import generate_shop_excel, generate_full_platform_excel
from aiogram.types import BufferedInputFile

@router.callback_query(F.data.startswith("sa_excel_"))
async def export_single_shop_excel(call: CallbackQuery):
    if not is_super_admin(call.from_user.id):
        return
    shop_id = int(call.data.split("_")[2])
    shop = await db.get_shop_by_id(shop_id)
    if not shop:
        await call.answer("Do'kon topilmadi!", show_alert=True)
        return
        
    await call.answer("Excel hisobot tayyorlanmoqda...")
    bio = await generate_shop_excel(shop_id)
    filename = f"qarz_{shop['name'].replace(' ', '_')}_{shop_id}.xlsx"
    doc = BufferedInputFile(bio.getvalue(), filename=filename)
    
    caption = (
        f"📊 <b>{shop['name']} — To'liq Excel Hisoboti</b>\n\n"
        f"Ushbu faylda do'konning barcha qarzdor mijozlari, ularning telefonlari va barcha amalga oshirilgan savdolar tarixi to'liq jamlangan."
    )
    await call.message.answer_document(document=doc, caption=caption, parse_mode="HTML")

@router.message(F.text == "📥 Barcha bazani Excelda yuklash")
async def export_all_platform_excel(message: Message):
    if not is_super_admin(message.from_user.id):
        return
    await message.answer("⏳ Barcha do'konlar va mijozlar ma'lumotlari jamlanmoqda, kuting...")
    
    bio = await generate_full_platform_excel()
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"Qarz_Daftari_Backup_{date_str}.xlsx"
    doc = BufferedInputFile(bio.getvalue(), filename=filename)
    
    caption = (
        f"🛡 <b>Qarz Daftari Platformasi — To'liq Zaxira Fayli (Backup)</b>\n\n"
        f"📅 Sana: <code>{date_str}</code>\n"
        f"Barcha do'konlar, ularning egalari, qarzdor mijozlar va hisob-kitoblar ushbu faylda xavfsiz saqlangan."
    )
    await message.answer_document(document=doc, caption=caption, parse_mode="HTML")

@router.message(F.text == "📊 Platforma statistikasi")
async def show_platform_stats(message: Message):
    if not is_super_admin(message.from_user.id):
        return
    shops = await db.get_detailed_shops_analysis()
    
    total_shops = len(shops)
    active_shops = [s for s in shops if s.get('customers_count', 0) > 0]
    passive_shops = [s for s in shops if s.get('customers_count', 0) == 0]
    
    total_customers_all = sum(s.get('customers_count', 0) for s in shops)
    total_debt_all = sum(s.get('total_debt', 0.0) for s in shops)
    
    # TOP-5 Aktiv do'konlar
    top_active_text = ""
    for idx, s in enumerate(active_shops[:5], 1):
        top_active_text += f"{idx}. 🏪 <b>{s['name']}</b> — 👥 {s['customers_count']} mijoz | 💰 {format_money(s['total_debt'])}\n"
    if not top_active_text:
        top_active_text = "<i>(Hozircha mijozli faol do'konlar yo'q)</i>\n"
        
    # Passiv do'konlar ro'yxati (telefonlari bilan aloqa qilish uchun)
    passive_text = ""
    for idx, s in enumerate(passive_shops[:5], 1):
        phone = s['phone'] or "Tel yo'q"
        passive_text += f"{idx}. 🏪 <b>{s['name']}</b> — 📞 <code>{phone}</code>\n"
    if not passive_text:
        passive_text = "<i>(Barcha do'konlar faol!)</i>\n"
        
    text = (
        f"📊 <b>Qarz Daftari Platformasi Umumiy Statistikasi:</b>\n"
        f"────────────────────\n"
        f"🏪 <b>Do'konlar holati:</b>\n"
        f"• Jami ochilgan do'konlar: <b>{total_shops} ta</b>\n"
        f"• 🟢 <b>Faol (Mijozli) do'konlar:</b> <b>{len(active_shops)} ta</b>\n"
        f"• 🔴 <b>Passiv (0 mijoz) do'konlar:</b> <b>{len(passive_shops)} ta</b>\n\n"
        f"👥 <b>Umumiy foydalanuvchilar:</b>\n"
        f"• Platformadagi jami mijozlar: <b>{total_customers_all} nafar</b>\n"
        f"• Do'konlarning jami nasiya balansi: <b>{format_money(total_debt_all)}</b>\n\n"
        f"🏆 <b>ENG FAOL DO'KONLAR (TOP):</b>\n"
        f"{top_active_text}\n"
        f"⚠️ <b>ALOQAGA CHIQISH KERAK (PASSIVLAR):</b>\n"
        f"{passive_text}\n"
        f"💡 <i>Passiv do'konchilarga telefon qilib, QR kodni osishni va qarz yozishni o'rgating!</i>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_superadmin_main_kb())
