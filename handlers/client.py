from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, CommandObject, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from keyboards.admin_kb import (
    get_admin_main_kb, format_money, get_open_store_kb, 
    get_cancel_kb, get_contact_kb, get_subscription_kb, get_recovery_contact_kb
)
from keyboards.superadmin_kb import get_superadmin_main_kb
from keyboards.client_kb import get_client_main_kb
import config

router = Router()

class UserRegisterShop(StatesGroup):
    shop_name = State()
    shop_phone = State()

class UserRecoverShop(StatesGroup):
    phone = State()

class CustomerRegisterState(StatesGroup):
    waiting_for_phone = State()

@router.message(StateFilter(UserRegisterShop, UserRecoverShop, CustomerRegisterState), F.text.in_(["❌ Bekor qilish", "/cancel"]))
async def cancel_user_register_cb(message: Message, state: FSMContext):
    await state.clear()
    promo_text = (
        f"👋 Assalomu alaykum, <b>{message.from_user.full_name}</b>!\n\n"
        f"🎁 <b>Siz uchun 1 OY (30 KUN) MUTLAQO BEPUL sinov muddati taqdim etiladi!</b>\n\n"
        f"O'z do'koningizni ochish yoki mavjud do'konni yangi profilga tiklash uchun tanlang 👇"
    )
    await message.answer(promo_text, parse_mode="HTML", reply_markup=get_open_store_kb())

# ==================== DO'KONNI TIKLASH (RECOVERY) ====================

@router.callback_query(F.data == "start_recover_my_store")
async def start_recover_my_store_cb(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserRecoverShop.phone)
    text = (
        "🔐 <b>Do'konni yangi profilga tiklash</b>\n\n"
        "Agar telefoningiz yo'qolgan yoki yangi Telegram ochgan bo'lsangiz:\n"
        "Avval ro'yxatdan o'tgan telefon raqamingizni pastdagi <b>«📱 Telefon raqamni yuborish (Tiklash)»</b> tugmasi orqali yuboring (yoki qo'lda yozing):"
    )
    await call.message.answer(text, parse_mode="HTML", reply_markup=get_recovery_contact_kb())
    await call.answer()

@router.message(UserRecoverShop.phone)
async def process_user_recover_phone(message: Message, state: FSMContext, bot: Bot):
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
    else:
        phone = message.text.strip() if message.text else ""
        
    shop = await db.get_shop_by_phone(phone)
    if not shop:
        await message.answer(
            f"⚠️ <b>Do'kon topilmadi!</b>\n\n"
            f"<code>{phone}</code> telefon raqamiga biriktirilgan do'kon topilmadi.\n"
            f"Iltimos, to'g'ri raqam kiriting yoki Super Adminga murojaat qiling:\n"
            f"📞 @{config.ADMIN_USERNAME}",
            parse_mode="HTML"
        )
        return
        
    user_id = message.from_user.id
    user_full_name = message.from_user.full_name
    
    await db.transfer_shop_ownership(shop['id'], user_id, user_full_name)
    await state.clear()
    
    is_valid, days_left, _ = await db.check_shop_subscription(shop['id'])
    is_sa = user_id in config.SUPER_ADMIN_IDS
    
    success_text = (
        f"🎉 <b>Do'koningiz muvaffaqiyatli tiklandi!</b>\n\n"
        f"🏪 <b>{shop['name']}</b> do'koni barcha mijozlari va qarz daftari bilan ushbu yangi Telegram profilingizga biriktirildi.\n"
        f"⏳ Obuna muddati: <b>{days_left} kun qoldi</b>.\n\n"
        f"Xavfsizlik uchun eski hisobingizdan adminlik huquqi avtomatik olib tashlandi."
    )
    await message.answer(success_text, parse_mode="HTML", reply_markup=get_admin_main_kb(is_sa, days_left=days_left))
    
    for sa_id in config.SUPER_ADMIN_IDS:
        try:
            sa_notify = (
                f"🛡 <b>Xavfsizlik: Do'kon yangi hisobga tiklandi!</b>\n\n"
                f"🏪 Do'kon: <b>{shop['name']}</b> (ID: {shop['id']})\n"
                f"👤 Yangi Admin: <b>{user_full_name}</b>\n"
                f"🆔 Yangi Telegram ID: <code>{user_id}</code>\n"
                f"📞 Tel: <code>{phone}</code>"
            )
            await bot.send_message(chat_id=sa_id, text=sa_notify, parse_mode="HTML")
        except Exception:
            pass

# ==================== ASOSIY START HANDLER ====================

@router.message(Command("cancel"))
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, bot: Bot, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user_full_name = message.from_user.full_name
    
    # 1. Super Admin tekshiruvi
    is_sa = (user_id in config.SUPER_ADMIN_IDS)
    
    # 2. Agar reklama QR kodi orqali yangi do'kon ochishga kirayotgan bo'lsa (/start new_shop yoki promo)
    args = command.args
    if args in ["new_shop", "promo", "flyer"]:
        existing = await db.get_shop_by_admin(user_id)
        if existing:
            is_valid, days_left, _ = await db.check_shop_subscription(existing['id'])
            await message.answer(
                f"Assalomu alaykum, <b>{user_full_name}</b>!\n"
                f"Sizda allaqachon <b>{existing['name']}</b> do'koni mavjud.\n"
                f"⏳ Obuna muddati: <b>{days_left} kun</b>.",
                parse_mode="HTML",
                reply_markup=get_admin_main_kb(is_sa, days_left=days_left)
            )
            return
        
        # Yangi do'kon ochish savolini to'g'ridan-to'g'ri boshlash
        await state.set_state(UserRegisterShop.shop_name)
        promo_start = (
            f"👋 Assalomu alaykum, <b>{user_full_name}</b>!\n\n"
            f"📒 <b>Qarz va Nasiya Daftari Botiga xush kelibsiz!</b>\n"
            f"<i>(Oziq-ovqat, Kiyim-kechak, Zapchast, Qurilish mollari va boshqa barcha do'konlar uchun)</i>\n\n"
            f"🎁 Sizga <b>1 OY (30 KUN) MUTLAQO BEPUL</b> sinov muddati taqdim etiladi.\n\n"
            f"🏪 <b>1-qadam: Do'koningiz nomini kiriting:</b>\n"
            f"<i>(Masalan: Baraka Market, Rayhon Kiyimlar, Avto Zapchast, Stroy Material)</i>"
        )
        await message.answer(promo_start, parse_mode="HTML", reply_markup=get_cancel_kb())
        return

    # 3. Agar sherik (adminlik) taklif havolasi orqali kirayotgan bo'lsa (/start staff_TOKEN)
    if args and args.startswith("staff_"):
        token = args.replace("staff_", "")
        shop, msg = await db.use_staff_invite(token, user_id, user_full_name)
        if shop:
            try:
                owner_notify = (
                    f"🎉 <b>Yangi sherik qo'shildi!</b>\n\n"
                    f"👤 Ism: <b>{user_full_name}</b>\n"
                    f"🆔 Telegram ID: <code>{user_id}</code>\n"
                    f"Muvaffaqiyatli do'kon administratoriga aylandi."
                )
                await bot.send_message(chat_id=shop['admin_id'], text=owner_notify, parse_mode="HTML")
            except Exception:
                pass
                
            is_valid, days_left, _ = await db.check_shop_subscription(shop['id'])
            welcome_staff = (
                f"🎉 <b>Tabriklaymiz, {user_full_name}!</b>\n\n"
                f"Siz <b>{shop['name']}</b> do'koni administratorlar safiga qo'shildingiz.\n"
                f"Endi siz ham mijozlar qarzlarini yozishingiz, to'lovlarni qabul qilishingiz va yangi mijozlar qo'shishingiz mumkin."
            )
            await message.answer(welcome_staff, parse_mode="HTML", reply_markup=get_admin_main_kb(False, days_left=days_left))
            return
        else:
            await message.answer(f"⚠️ {msg}")
            return

    # 3. Do'konchi (Admin yoki Sherik) tekshiruvi
    shop = await db.get_shop_by_admin(user_id)
    if shop:
        is_valid, days_left, expires_at = await db.check_shop_subscription(shop['id'])
        if not is_valid:
            text_expired = (
                f"⚠️ <b>{shop['name']} — Obuna muddati tugadi!</b>\n\n"
                f"Sizning 30 kunlik sinov muddatingiz yakunlandi.\n"
                f"Botdan foydalanishni davom ettirish va qarzlarni boshqarish uchun obuna to'lovini amalga oshiring.\n\n"
                f"💳 <b>To'lov uchun karta:</b> <code>{config.CARD_NUMBER}</code>\n"
                f"👤 <b>Qabul qiluvchi:</b> {config.CARD_HOLDER}\n\n"
                f"📌 <i>To'lov qilgach, chekni quyidagi tugma orqali adminga yuboring!</i>"
            )
            await message.answer(text_expired, parse_mode="HTML", reply_markup=get_subscription_kb())
            return
        
        await message.answer(
            f"Assalomu alaykum, <b>{user_full_name}</b>!\n"
            f"🏪 Do'kon: <b>{shop['name']}</b> boshqaruv paneliga xush kelibsiz.\n"
            f"⏳ <i>Obuna muddati: yana {days_left} kun faol.</i>",
            parse_mode="HTML",
            reply_markup=get_admin_main_kb(is_sa, days_left=days_left)
        )
        return
        
    # Agar do'konchi bo'lmasa, lekin super admin bo'lsa
    if is_sa and not command.args:
        await message.answer(
            f"Assalomu alaykum, <b>{user_full_name}</b> (Super Admin)!\n"
            f"Siz tizim boshqaruvchisiz.",
            parse_mode="HTML",
            reply_markup=get_superadmin_main_kb()
        )
        return

    # 4. Agar maxsus mijoz taklif havolasi orqali kirayotgan bo'lsa (/start c_CUSTOMERID)
    if args and args.startswith("c_"):
        try:
            cust_id = int(args.replace("c_", ""))
            cust = await db.link_customer_telegram(cust_id, user_id, user_full_name)
            if cust:
                shop = await db.get_shop_by_id(cust['shop_id'])
                shop_name = shop['name'] if shop else "Do'kon"
                
                if shop:
                    try:
                        admin_notify = (
                            f"🔔 <b>Mijoz hisobi ulandi!</b>\n\n"
                            f"👤 Mijoz: <b>{cust['full_name']}</b>\n"
                            f"🆔 Telegram ID: <code>{user_id}</code>\n"
                            f"💰 Mavjud qarzi: <b>{format_money(cust['balance'])}</b>\n"
                            f"Mijoz shaxsiy havolasi orqali botga muvaffaqiyatli bog'landi."
                        )
                        await bot.send_message(chat_id=shop['admin_id'], text=admin_notify, parse_mode="HTML")
                    except Exception:
                        pass
                
                welcome_text = (
                    f"Assalomu alaykum, <b>{cust['full_name']}</b>!\n\n"
                    f"🏪 Siz <b>{shop_name}</b> do'koni qarz daftari tizimiga muvaffaqiyatli ulandingiz.\n"
                    f"💰 Sizning joriy qarz balansingiz: <b>{format_money(cust['balance'])}</b>\n\n"
                    f"Endi har gal xarid yoki to'lov qilganingizda hisobotlar avtomatik yuboriladi."
                )
                await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_client_main_kb())
                return
        except Exception:
            pass

    # 5. Agar umumiy QR kod orqali kirayotgan bo'lsa (/start shop_ID)
    if args and args.startswith("shop_"):
        try:
            shop_id = int(args.replace("shop_", ""))
            target_shop = await db.get_shop_by_id(shop_id)
            if target_shop and target_shop['is_active']:
                # Agar o'z do'koni QR kodini skaner qilgan bo'lsa
                own_shop = await db.get_shop_by_admin(user_id)
                if own_shop and own_shop['id'] == shop_id:
                    await message.answer(
                        f"🏪 <b>Bu sizning o'zingizning «{own_shop['name']}» do'koningiz QR kodi!</b>\n\n"
                        f"Ushbu QR kodni peshtaxtaga yoki devorga osib qo'ying — xaridorlaringiz skaner qilib mijoz bo'lib ulanishadi.",
                        parse_mode="HTML"
                    )
                    return
                
                # Agar o'zining boshqa do'koni bor bo'lsa (Do'konchi bo'lsa) -> Tasdiqlash oynasi
                if own_shop:
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✅ Ha, xaridor bo'lib ulanish", callback_data=f"confirm_join_{shop_id}")],
                        [InlineKeyboardButton(text="🔙 O'z do'konimga qaytish", callback_data="back_to_my_shop")]
                    ])
                    text_confirm = (
                        f"🔔 <b>{user_full_name}, diqqat!</b>\n\n"
                        f"Siz <b>«{target_shop['name']}»</b> do'konining QR kodini skaner qildingiz.\n\n"
                        f"Siz ushbu do'konga <b>Xaridor (Mijoz)</b> sifatida ulanmoqchimisiz?\n\n"
                        f"💡 <i>Xavotir olmang, o'zingizning «{own_shop['name']}» do'koningiz to'liq saqlanadi va istalgan paytda o'z do'koningiz boshqaruviga qayta olasiz.</i>"
                    )
                    await message.answer(text_confirm, parse_mode="HTML", reply_markup=confirm_kb)
                    return

                # Allaqachon ulangan oddiy xaridor bo'lsa
                existing_cust = await db.get_customers_by_telegram_id(user_id)
                shop_cust = next((c for c in existing_cust if c['shop_id'] == shop_id), None)
                if shop_cust and shop_cust['phone']:
                    welcome_text = (
                        f"👤 <b>SHAXSIY HISOBINGIZ (Xaridor rejimi)</b>\n"
                        f"────────────────────\n"
                        f"🏪 Siz <b>«{target_shop['name']}»</b> do'koni tizimiga ulangansiz.\n"
                        f"💰 Sizning joriy qarz/nasiya balansingiz: <b>{format_money(shop_cust['balance'])}</b>"
                    )
                    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_client_main_kb(has_own_shop=False))
                    return
                
                # Telefon raqam so'rash
                await state.set_state(CustomerRegisterState.waiting_for_phone)
                await state.update_data(shop_id=shop_id, shop_name=target_shop['name'])
                prompt_phone = (
                    f"👋 Assalomu alaykum, <b>{user_full_name}</b>!\n\n"
                    f"🏪 Siz <b>«{target_shop['name']}»</b> do'koni Qarz va Nasiya tizimiga ulanmoqdasiz.\n\n"
                    f"📱 Do'konga ulanish va hisob-kitoblaringizni kuzatib borish uchun pastdagi <b>«📱 Telefon raqamni ulashish»</b> tugmasini bosing:"
                )
                await message.answer(prompt_phone, parse_mode="HTML", reply_markup=get_contact_kb())
                return
        except Exception:
            pass

# ==================== MIJOZ TELEFON RAQAMINI QABUL QILISH ====================

# ==================== MIJOZ TASDIQLASH VA QABUL QILISH ====================

@router.callback_query(F.data.startswith("confirm_join_"))
async def confirm_join_customer_cb(call: CallbackQuery, state: FSMContext):
    shop_id = int(call.data.split("_")[2])
    target_shop = await db.get_shop_by_id(shop_id)
    if not target_shop:
        await call.answer("Do'kon topilmadi!", show_alert=True)
        return
        
    await state.set_state(CustomerRegisterState.waiting_for_phone)
    await state.update_data(shop_id=shop_id, shop_name=target_shop['name'])
    prompt_phone = (
        f"📱 <b>«{target_shop['name']}»</b> do'koni hisob-kitoblaringizni bog'lash uchun:\n\n"
        f"Pastdagi <b>«📱 Telefon raqamni ulashish»</b> tugmasini bosing:"
    )
    await call.message.answer(prompt_phone, parse_mode="HTML", reply_markup=get_contact_kb())
    await call.answer()

@router.callback_query(F.data == "back_to_my_shop")
async def back_to_my_shop_cb(call: CallbackQuery):
    user_id = call.from_user.id
    shop = await db.get_shop_by_admin(user_id)
    if shop:
        is_valid, days_left, _ = await db.check_shop_subscription(shop['id'])
        is_sa = user_id in config.SUPER_ADMIN_IDS
        text = (
            f"🏪 <b>SIZNING DO'KONINGIZ: «{shop['name']}»</b>\n"
            f"👑 <i>(Siz hozir o'z do'koningiz boshqaruvidasiz)</i>\n"
            f"────────────────────\n"
            f"⏳ Obuna muddati: <b>{days_left} kun qoldi</b>."
        )
        await call.message.answer(text, parse_mode="HTML", reply_markup=get_admin_main_kb(is_sa, days_left=days_left))
    await call.answer()

@router.message(CustomerRegisterState.waiting_for_phone)
async def process_customer_qr_phone(message: Message, state: FSMContext, bot: Bot):
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
    else:
        phone_raw = message.text.strip() if message.text else ""
        phone = phone_raw if phone_raw != "-" else None
        
    data = await state.get_data()
    shop_id = data.get('shop_id')
    user_id = message.from_user.id
    user_full_name = message.from_user.full_name
    
    target_shop = await db.get_shop_by_id(shop_id)
    shop_name = target_shop['name'] if target_shop else "Do'kon"
    
    cust = await db.register_telegram_customer(
        shop_id=shop_id,
        telegram_id=user_id,
        full_name=user_full_name,
        phone=phone
    )
    await state.clear()
    
    # Do'konchiga bildirishnoma
    if target_shop:
        try:
            admin_notify = (
                f"🔔 <b>Yangi mijoz ulandi!</b>\n\n"
                f"👤 Ism: <b>{user_full_name}</b>\n"
                f"📞 Tel: <code>{phone or 'Kiritilmadi'}</code>\n"
                f"🆔 Telegram ID: <code>{user_id}</code>\n\n"
                f"Mijoz endi do'koningiz qarz/nasiya daftariga kiritildi."
            )
            await bot.send_message(chat_id=target_shop['admin_id'], text=admin_notify, parse_mode="HTML")
        except Exception:
            pass
            
    own_shop = await db.get_shop_by_admin(user_id)
    has_own_shop = bool(own_shop)
    
    welcome_text = (
        f"👤 <b>SHAXSIY HISOBINGIZ (Xaridor rejimi)</b>\n"
        f"────────────────────\n"
        f"🎉 <b>Tabriklaymiz, {user_full_name}!</b>\n\n"
        f"🏪 Siz <b>«{shop_name}»</b> do'koni tizimiga muvaffaqiyatli ulandingiz.\n"
        f"📞 Telefoningiz: <code>{phone or 'Kiritilmadi'}</code>\n"
        f"💰 Sizning joriy qarz/nasiya balansingiz: <b>{format_money(cust['balance'])}</b>\n\n"
        f"Har gal xarid qilganingizda bot sizga avtomatik hisobot yuborib turadi."
    )
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_client_main_kb(has_own_shop=has_own_shop))

    # 6. Oddiy mijoz (avval ulanib bo'lgan)
    cust_accounts = await db.get_customers_by_telegram_id(user_id)
    if cust_accounts:
        await message.answer(
            f"Assalomu alaykum, <b>{user_full_name}</b>!\nQarz daftariga xush kelibsiz.",
            reply_markup=get_client_main_kb()
        )
        return

    # 7. Yangi tashrif buyuruvchi (Do'kon ochish / Tiklash taklifi)
    promo_text = (
        f"👋 Assalomu alaykum, <b>{user_full_name}</b>!\n\n"
        f"📒 <b>Do'konlar uchun Qarz va Nasiya Daftari Botiga xush kelibsiz!</b>\n\n"
        f"Ushbu bot <b>Oziq-ovqat, Kiyim-kechak, Avto ehtiyot qismlar, Qurilish mollari, Kosmetika</b> va boshqa barcha turdagi savdo do'konlari uchun mo'ljallangan.\n\n"
        f"✨ <b>Asosiy imkoniyatlar:</b>\n"
        f"• Har qanday tovar uchun qarz va nasiyalarni 3 soniyada yozish\n"
        f"• Xaridorlarga avtomatik Telegram hisobot borishi\n"
        f"• Kassirlar va sotuvchilarni sherik qilib ulash\n"
        f"• Qarzlarni 1 tiyinigacha aniq nazorat qilish\n\n"
        f"🎁 <b>Siz uchun 1 OY (30 KUN) MUTLAQO BEPUL sinov muddati taqdim etiladi!</b>\n\n"
        f"O'z do'koningizni ochish yoki mavjud do'konni yangi profilga tiklash uchun tanlang 👇"
    )
    await message.answer(promo_text, parse_mode="HTML", reply_markup=get_open_store_kb())

# ==================== O'Z DO'KONINI OCHISH (TRIAL REGISTER) ====================

@router.callback_query(F.data == "start_open_my_store")
async def start_open_my_store_cb(call: CallbackQuery, state: FSMContext):
    existing = await db.get_shop_by_admin(call.from_user.id)
    if existing:
        await call.answer("Sizda allaqachon do'kon mavjud!", show_alert=True)
        return
        
    await state.set_state(UserRegisterShop.shop_name)
    await call.message.answer(
        "🏪 <b>Do'koningiz nomini kiriting:</b>\n<i>(Masalan: Baraka Market, Rayhon Butik, Avto Zapchast, Stroy Material)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_kb()
    )
    await call.answer()

@router.message(UserRegisterShop.shop_name)
async def process_user_shop_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Iltimos, do'kon nomini to'g'ri kiriting:")
        return
    await state.update_data(shop_name=name)
    await state.set_state(UserRegisterShop.shop_phone)
    await message.answer(
        f"Do'kon nomi: <b>{name}</b>\n\nPastdagi <b>«📱 Telefon raqamni ulashish»</b> tugmasini bosing yoki raqamingizni yozing:",
        parse_mode="HTML",
        reply_markup=get_contact_kb()
    )

@router.message(UserRegisterShop.shop_phone)
async def process_user_shop_phone(message: Message, state: FSMContext, bot: Bot):
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
    else:
        phone_raw = message.text.strip() if message.text else ""
        phone = phone_raw if phone_raw != "-" else None
    
    data = await state.get_data()
    user_id = message.from_user.id
    user_full_name = message.from_user.full_name
    
    try:
        shop_id = await db.create_shop(data.get('shop_name', 'Yangi do\'kon'), user_id, phone, days=30)
        await state.clear()
        
        shop_name = data.get('shop_name', 'Do\'kon')
        welcome_msg = (
            f"🎉 <b>Tabriklaymiz, {user_full_name}!</b>\n\n"
            f"🏪 <b>{shop_name}</b> do'koningiz muvaffaqiyatli ochildi!\n"
            f"🎁 Sizga <b>30 KUNLIK BEPUL SINOV MUDDATI</b> berildi.\n\n"
            f"Boshqaruv menyusi quyida ochildi 👇"
        )
        is_sa = user_id in config.SUPER_ADMIN_IDS
        await message.answer(welcome_msg, parse_mode="HTML", reply_markup=get_admin_main_kb(is_sa, days_left=30))
        
        # Mijozlar uchun maxsus QR kodni rasm qilib chiqarib berish
        from utils.qr import generate_shop_qr
        from aiogram.types import BufferedInputFile
        bot_info = await bot.get_me()
        qr_bio = generate_shop_qr(bot_info.username, shop_id)
        
        qr_caption = (
            f"📲 <b>{shop_name} — Mijozlaringiz uchun maxsus QR Kod!</b>\n\n"
            f"📌 <b>Buni chop etib peshtaxtaga yoki devorga osib qo'ying:</b>\n"
            f"Xaridorlaringiz bu kodni telefon kamerasida skaner qilsa, "
            f"to'g'ridan-to'g'ri sizning do'koningiz <b>Mijozi</b> bo'lib ulanadi va o'z qarzlarini ko'rib boradi!\n\n"
            f"🔗 To'g'ridan-to'g'ri havola: https://t.me/{bot_info.username}?start=shop_{shop_id}"
        )
        photo_file = BufferedInputFile(qr_bio.getvalue(), filename=f"shop_{shop_id}_qr.png")
        await message.answer_photo(photo=photo_file, caption=qr_caption, parse_mode="HTML")
        
        for sa_id in config.SUPER_ADMIN_IDS:
            try:
                sa_notify = (
                    f"🔔 <b>Yangi do'kon ochildi (Trial)!</b>\n\n"
                    f"🏪 Do'kon: <b>{data.get('shop_name', '')}</b> (ID: {shop_id})\n"
                    f"👤 Egasi: <b>{user_full_name}</b>\n"
                    f"🆔 Telegram ID: <code>{user_id}</code>\n"
                    f"📞 Tel: {phone or 'Kiritilmadi'}\n"
                    f"⏳ Muddat: 30 kun berildi."
                )
                await bot.send_message(chat_id=sa_id, text=sa_notify, parse_mode="HTML")
            except Exception:
                pass
    except Exception as e:
        await message.answer(f"⚠️ Do'kon ochishda xatolik yuz berdi: {e}\nIltimos, /start bosib qaytadan urinib ko'ring.")

# ==================== MIJOZ TUGMALARI VA REJIM ALMASHTIRISH ====================

@router.message(F.text.in_(["💳 Qayerda qancha qarzim bor?", "💳 Mening qarz va nasiyalarim", "💳 Mening qarzlarim", "🔄 Yangilash", "👤 Shaxsiy qarzlarim (Xaridor rejimi)"]))
async def show_my_debts(message: Message, bot: Bot):
    user_id = message.from_user.id
    accounts = await db.get_customers_by_telegram_id(user_id)
    own_shop = await db.get_shop_by_admin(user_id)
    has_own_shop = bool(own_shop)
    
    if not accounts:
        msg = (
            f"👤 <b>SHAXSIY HISOBINGIZ (Xaridor rejimi)</b>\n"
            f"────────────────────\n"
            f"Sizda hozircha hech qaysi do'konda qarz yoki nasiya mavjud emas.\n\n"
            f"<i>(Boshqa do'konlardan nasiyaga tovar olganingizda, do'kondagi QR kodni skaner qilsangiz hisobotlar shu yerda chiqadi).</i>"
        )
        await message.answer(msg, parse_mode="HTML", reply_markup=get_client_main_kb(has_own_shop=has_own_shop))
        return
    
    text = (
        f"👤 <b>SHAXSIY HISOBINGIZ (Xaridor rejimi)</b>\n"
        f"🛒 <i>(Boshqa do'konlardan olgan qarz va nasiyalaringiz)</i>\n"
        f"────────────────────\n\n"
    )
    total_all = 0.0
    for acc in accounts:
        text += f"🏪 <b>Do'kon:</b> {acc['shop_name']}\n"
        text += f"💰 <b>Qarzingiz / Nasiya:</b> {format_money(acc['balance'])}\n"
        if acc['shop_phone']:
            text += f"📞 <b>Telefon:</b> <code>{acc['shop_phone']}</code>\n"
        
        shop = await db.get_shop_by_id(acc['shop_id'])
        if shop:
            text += f"💬 <b>Telegram aloqa:</b> <a href='tg://user?id={shop['admin_id']}'>Do'konchiga yozish</a>\n"
            
        text += "────────────────────\n"
        total_all += acc['balance']
        
    text += f"\n📊 <b>Jami umumiy qarzingiz: {format_money(total_all)}</b>"
    await message.answer(text, parse_mode="HTML", reply_markup=get_client_main_kb(has_own_shop=has_own_shop))

@router.message(F.text == "🏪 Mening do'konim (Do'konchi rejimi)")
async def return_to_my_store(message: Message, bot: Bot):
    user_id = message.from_user.id
    shop = await db.get_shop_by_admin(user_id)
    if not shop:
        await message.answer("Sizda hali o'z do'koningiz yo'q. Ochish uchun /start bosing.")
        return
        
    is_valid, days_left, _ = await db.check_shop_subscription(shop['id'])
    is_sa = user_id in config.SUPER_ADMIN_IDS
    text = (
        f"🏪 <b>SIZNING DO'KONINGIZ: «{shop['name']}»</b>\n"
        f"👑 <i>(Siz hozir o'z do'koningiz boshqaruvidasiz)</i>\n"
        f"────────────────────\n"
        f"⏳ Obuna muddati: <b>{days_left} kun qoldi</b>.\n\n"
        f"Do'kon boshqaruvi menyusi quyida 👇"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_admin_main_kb(is_sa, days_left=days_left))

@router.message(F.text == "📲 Ekranga znachok qilish")
async def show_client_homescreen_guide(message: Message):
    text = (
        "📲 <b>Botni telefon ekraniga Znachok (Ilova) qilish qo'llanmasi:</b>\n\n"
        "Buni 1 marta qilib qo'ysangiz, Telegram ichidan qidirib o'tirmaysiz — telefoningiz ish stolida xuddi ilovadek turadi!\n\n"
        "👉 <b>Qanday qilinadi (3 ta oddiy qadam):</b>\n"
        "1️⃣ Yuqoridagi <b>«Qarz daftari bot»</b> nomiga (profiliga) bosing.\n"
        "2️⃣ O'ng burchakdagi <b>3 ta nuqta (⋮)</b> ni bosing.\n"
        "3️⃣ <b>«Добавить на главный экран»</b> (yoki <i>«Add to Home screen» / «Asosiy ekranga qo'shish»</i>) ni bosing!\n\n"
        "🎉 <b>Tayyor!</b> Endi telefoningiz ekranidan 1 marta bosib to'g'ridan-to'g'ri qarz daftaringizni ko'rasiz."
    )
    await message.answer(text, parse_mode="HTML")

@router.message(F.text.in_(["📜 Xaridlar tarixi", "📜 Xaridlarim tarixi"]))
async def show_my_history(message: Message):
    user_id = message.from_user.id
    accounts = await db.get_customers_by_telegram_id(user_id)
    own_shop = await db.get_shop_by_admin(user_id)
    has_own_shop = bool(own_shop)
    
    if not accounts:
        await message.answer("Sizda hali xaridlar tarixi mavjud emas.", reply_markup=get_client_main_kb(has_own_shop=has_own_shop))
        return
    
    text = (
        f"📜 <b>SHAXSIY XARIDLARINGIZ TARIXI:</b>\n"
        f"────────────────────\n\n"
    )
    for acc in accounts:
        text += f"🏪 <b>{acc['shop_name']}</b> do'koni:\n"
        txs = await db.get_customer_transactions(acc['id'], limit=5)
        if not txs:
            text += "<i>Amallar yo'q</i>\n"
        else:
            for t in txs:
                icon = "🔴 Qarz:" if t['type'] == 'debt' else "🟢 To'lov:"
                desc = f" ({t['description']})" if t['description'] else ""
                date_str = str(t['created_at'])[:16]
                text += f"{icon} {format_money(t['amount'])}{desc}\n📅 <i>{date_str}</i>\n"
        text += "────────────────────\n"
        
    await message.answer(text, parse_mode="HTML", reply_markup=get_client_main_kb(has_own_shop=has_own_shop))
