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

class UserAuthStates(StatesGroup):
    waiting_for_global_phone = State()

@router.message(StateFilter(UserRegisterShop, UserRecoverShop, CustomerRegisterState, UserAuthStates), F.text.in_(["❌ Bekor qilish", "/cancel"]))
async def cancel_user_register_cb(message: Message, state: FSMContext):
    await state.clear()
    promo_text = (
        f"👋 Assalomu alaykum, <b>{message.from_user.full_name}</b>!\n\n"
        f"🎁 <b>Siz uchun 1 OY (30 KUN) MUTLAQO BEPUL sinov muddati taqdim etiladi!</b>\n\n"
        f"O'z daftaringizni ochish yoki mavjud daftarni yangi profilga tiklash uchun tanlang 👇"
    )
    await message.answer(promo_text, parse_mode="HTML", reply_markup=get_open_store_kb())

# ==================== DAFTARNI TIKLASH (RECOVERY) ====================

@router.callback_query(F.data == "start_recover_my_store")
async def start_recover_my_store_cb(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserRecoverShop.phone)
    text = (
        "🔐 <b>Daftarni yangi profilga tiklash</b>\n\n"
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
            "❌ <b>Bunday telefon raqamga tegishli faol daftar topilmadi!</b>\n\n"
            "Iltimos, to'g'ri telefon raqamni kiriting yoki yangi daftar oching.",
            parse_mode="HTML",
            reply_markup=get_open_store_kb()
        )
        await state.clear()
        return
        
    # Do'kon egasini yangi Telegram ID ga almashtiramiz
    user_id = message.from_user.id
    user_full_name = message.from_user.full_name
    await db.transfer_shop_ownership(shop['id'], user_id, phone)
    await state.clear()
    
    is_valid, days_left, _ = await db.check_shop_subscription(shop['id'])
    is_sa = user_id in config.SUPER_ADMIN_IDS
    
    text_success = (
        f"🎉 <b>Daftaringiz muvaffaqiyatli tiklandi!</b>\n\n"
        f"📒 <b>«{shop['name']}»</b> daftari yangi Telegram profilingizga ulandi.\n"
        f"Barcha mijozlar, qarzlar va hisobotlar saqlab qolindi.\n"
        f"⏳ Obuna muddati: <b>{days_left} kun qoldi</b>."
    )
    await message.answer(text_success, parse_mode="HTML", reply_markup=get_admin_main_kb(is_sa, days_left=days_left))
    
    for sa_id in config.SUPER_ADMIN_IDS:
        try:
            sa_notify = (
                f"🛡 <b>Xavfsizlik: Hisob yangi profilga tiklandi!</b>\n\n"
                f"📒 Daftar: <b>{shop['name']}</b> (ID: {shop['id']})\n"
                f"👤 Yangi Admin: <b>{user_full_name}</b>\n"
                f"🆔 Yangi Telegram ID: <code>{user_id}</code>\n"
                f"📞 Tel: <code>{phone}</code>"
            )
            await bot.send_message(chat_id=sa_id, text=sa_notify, parse_mode="HTML")
        except Exception:
            pass

# ==================== TELEFON RAQAMNI TASDIQLASH (AUTH GATE) ====================

@router.message(UserAuthStates.waiting_for_global_phone)
async def process_global_phone_auth(message: Message, state: FSMContext, bot: Bot):
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
    else:
        phone_raw = message.text.strip() if message.text else ""
        digits = "".join([c for c in phone_raw if c.isdigit()])
        if len(digits) < 7:
            await message.answer(
                "⚠️ Iltimos, pastdagi <b>«📱 Telefon raqamni yuborish»</b> tugmasini bosing yoki to'g'ri telefon raqamingizni kiriting:",
                parse_mode="HTML"
            )
            return
        phone = phone_raw if phone_raw.startswith("+") else f"+{phone_raw}"
        
    user_id = message.from_user.id
    user_full_name = message.from_user.full_name
    username = message.from_user.username
    
    # 1. Bazaga saqlash
    await db.save_user(user_id, user_full_name, username, phone)
    
    # 2. Avto-link (agar qarz beruvchilar ushbu telefon raqamga qarz yozgan bo'lsa)
    linked = await db.auto_link_customer_by_phone(user_id, phone, user_full_name)
    for c in linked:
        try:
            shop = await db.get_shop_by_id(c['shop_id'])
            if shop:
                await bot.send_message(
                    chat_id=shop['admin_id'],
                    text=f"🔔 <b>Qarzdor botga ulandi!</b>\n👤 Ism: <b>{user_full_name}</b>\n📞 Tel: <code>{phone}</code>",
                    parse_mode="HTML"
                )
        except Exception:
            pass
            
    # 3. Oldingi argumentlarni tekshirish (c_..., shop_..., new_shop va h.k.)
    data = await state.get_data()
    saved_args = data.get('start_args')
    await state.clear()
    
    await message.answer(
        f"✅ <b>Telefon raqamingiz muvaffaqiyatli tasdiqlandi:</b> <code>{phone}</code>\n",
        parse_mode="HTML"
    )
    
    dummy_cmd = CommandObject(prefix="/", command="start", args=saved_args)
    await cmd_start(message, dummy_cmd, bot, state)

# ==================== ASOSIY START HANDLER ====================

@router.message(Command("cancel"))
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, bot: Bot, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user_full_name = message.from_user.full_name
    
    # 0. MAJBURIY TELEFON RAQAM TEKSHIRUVI (Har qanday yangi odam uchun)
    db_user = await db.get_user(user_id)
    is_sa = (user_id in config.SUPER_ADMIN_IDS)
    args = command.args
    
    if not db_user or not db_user.get('phone'):
        # Agar hali telefon raqami saqlanmagan bo'lsa, majburiy so'raymiz
        await state.set_state(UserAuthStates.waiting_for_global_phone)
        if args:
            await state.update_data(start_args=args)
            
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        auth_kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        auth_msg = (
            f"👋 Assalomu alaykum, <b>{user_full_name}</b>!\n\n"
            f"📒 <b>Qarz va Nasiya Daftari</b> botiga xush kelibsiz.\n\n"
            f"🔐 Tizimdan to'liq foydalanish, hisob-kitoblarni xavfsiz yuritish va shaxsiy hisobingizni yo'qotmaslik uchun telefon raqamingizni tasdiqlang:\n\n"
            f"👇 <i>Pastdagi <b>«📱 Telefon raqamni yuborish»</b> tugmasini 1 marta bosing:</i>"
        )
        await message.answer(auth_msg, parse_mode="HTML", reply_markup=auth_kb)
        return

    # 1. Agar reklama QR kodi orqali yangi hisob ochishga kirayotgan bo'lsa (/start new_shop yoki promo)
    args = command.args
    if args in ["new_shop", "promo", "flyer"]:
        existing = await db.get_shop_by_admin(user_id)
        if existing:
            is_valid, days_left, _ = await db.check_shop_subscription(existing['id'])
            await message.answer(
                f"Assalomu alaykum, <b>{user_full_name}</b>!\n"
                f"Sizda allaqachon <b>«{existing['name']}»</b> daftari mavjud.\n"
                f"⏳ Obuna muddati: <b>{days_left} kun</b>.",
                parse_mode="HTML",
                reply_markup=get_admin_main_kb(is_sa, days_left=days_left)
            )
            return
        
        # Yangi daftar ochish
        await state.set_state(UserRegisterShop.shop_name)
        promo_start = (
            f"👋 Assalomu alaykum, <b>{user_full_name}</b>!\n\n"
            f"📒 <b>Qarz va Nasiya Daftari Botiga xush kelibsiz!</b>\n\n"
            f"🎁 Sizga <b>1 OY (30 KUN) MUTLAQO BEPUL</b> sinov muddati taqdim etiladi.\n\n"
            f"✍️ <b>Qarz / Nasiya beruvchi nomingizni (Daftar yoki Faoliyat nomi) yozing:</b>\n\n"
            f"💡 <i>Misollar: Shaxsiy qarzlar, Baraka Market, Mebel sexi, Avtoservis, Kvartira ijarasi</i>"
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
                    f"🎉 <b>Yangi sherik/yordamchi qo'shildi!</b>\n\n"
                    f"👤 Ism: <b>{user_full_name}</b>\n"
                    f"🆔 Telegram ID: <code>{user_id}</code>\n"
                    f"Muvaffaqiyatli boshqaruvchilar safiga qo'shildi."
                )
                await bot.send_message(chat_id=shop['admin_id'], text=owner_notify, parse_mode="HTML")
            except Exception:
                pass
                
            is_valid, days_left, _ = await db.check_shop_subscription(shop['id'])
            welcome_staff = (
                f"🎉 <b>Tabriklaymiz, {user_full_name}!</b>\n\n"
                f"Siz <b>«{shop['name']}»</b> boshqaruvchilari safiga qo'shildingiz.\n"
                f"Endi siz ham qarz yozishingiz, to'lovlarni qabul qilishingiz va qarzdorlar qo'shishingiz mumkin."
            )
            await message.answer(welcome_staff, parse_mode="HTML", reply_markup=get_admin_main_kb(False, days_left=days_left))
            return
        else:
            await message.answer(f"⚠️ {msg}")
            return

    # 3. Qarz / Nasiya beruvchi (Admin yoki Sherik) tekshiruvi
    shop = await db.get_shop_by_admin(user_id)
    if shop:
        is_valid, days_left, expires_at = await db.check_shop_subscription(shop['id'])
        if not is_valid:
            text_expired = (
                f"⚠️ <b>«{shop['name']}» — Obuna muddati tugadi!</b>\n\n"
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
            f"📒 <b>«{shop['name']}»</b> — Qarz va Nasiya daftari boshqaruviga xush kelibsiz.\n"
            f"⏳ <i>Obuna muddati: yana {days_left} kun faol.</i>",
            parse_mode="HTML",
            reply_markup=get_admin_main_kb(is_sa, days_left=days_left)
        )
        return
        
    # Agar boshqaruvchi bo'lmasa, lekin super admin bo'lsa
    if is_sa and not command.args:
        await message.answer(
            f"Assalomu alaykum, <b>{user_full_name}</b> (Super Admin)!\n"
            f"Siz tizim boshqaruvchisiz.",
            parse_mode="HTML",
            reply_markup=get_superadmin_main_kb()
        )
        return

    # 4. Agar maxsus qarzdor taklif havolasi orqali kirayotgan bo'lsa (/start c_CUSTOMERID)
    if args and args.startswith("c_"):
        try:
            cust_id = int(args.replace("c_", ""))
            cust = await db.link_customer_telegram(cust_id, user_id, user_full_name)
            if cust:
                shop = await db.get_shop_by_id(cust['shop_id'])
                shop_name = shop['name'] if shop else "Qarz beruvchi"
                
                bal_u = cust.get('balance', 0.0) or 0.0
                bal_d = cust.get('balance_usd', 0.0) or 0.0
                if bal_u > 0 and bal_d > 0:
                    cust_bal_str = f"{format_money(bal_u, 'UZS')} | {format_money(bal_d, 'USD')}"
                elif bal_d > 0:
                    cust_bal_str = format_money(bal_d, 'USD')
                else:
                    cust_bal_str = format_money(bal_u, 'UZS')
                
                if shop:
                    try:
                        admin_notify = (
                            f"🔔 <b>Qarzdor hisobi ulandi!</b>\n\n"
                            f"👤 Ism: <b>{cust['full_name']}</b>\n"
                            f"🆔 Telegram ID: <code>{user_id}</code>\n"
                            f"💰 Mavjud qarzi: <b>{cust_bal_str}</b>\n"
                            f"Qarzdor shaxsiy havolasi orqali botga muvaffaqiyatli bog'landi."
                        )
                        await bot.send_message(chat_id=shop['admin_id'], text=admin_notify, parse_mode="HTML")
                    except Exception:
                        pass
                
                welcome_text = (
                    f"Assalomu alaykum, <b>{cust['full_name']}</b>!\n\n"
                    f"📒 Siz <b>«{shop_name}»</b> qarz va nasiya hisobiga muvaffaqiyatli ulandingiz.\n"
                    f"💰 Sizning joriy qarz balansingiz: <b>{cust_bal_str}</b>\n\n"
                    f"Endi har gal xarid yoki to'lov amalga oshirilganda hisobotlar avtomatik yuboriladi."
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
                # Agar o'z QR kodini skaner qilgan bo'lsa
                own_shop = await db.get_shop_by_admin(user_id)
                if own_shop and own_shop['id'] == shop_id:
                    await message.answer(
                        f"📒 <b>Bu sizning o'zingizning «{own_shop['name']}» hisobingiz QR kodi!</b>\n\n"
                        f"Ushbu QR kodni qarzdorlaringizga berishingiz yoki osib qo'yishingiz mumkin.",
                        parse_mode="HTML"
                    )
                    return
                
                # Agar o'zining boshqa daftari bor bo'lsa -> Tasdiqlash oynasi
                if own_shop:
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✅ Ha, hisobga ulanish", callback_data=f"confirm_join_{shop_id}")],
                        [InlineKeyboardButton(text="🔙 O'z daftarimga qaytish", callback_data="back_to_my_shop")]
                    ])
                    text_confirm = (
                        f"🔔 <b>{user_full_name}, diqqat!</b>\n\n"
                        f"Siz <b>«{target_shop['name']}»</b> hisobining QR kodini skaner qildingiz.\n\n"
                        f"Siz ushbu hisobga <b>Qarz oluvchi (Mijoz)</b> sifatida ulanmoqchimisiz?\n\n"
                        f"💡 <i>Xavotir olmang, o'zingizning «{own_shop['name']}» daftaringiz to'liq saqlanadi va istalgan paytda o'z daftaringiz boshqaruviga qayta olasiz.</i>"
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
                        f"📒 Siz <b>«{target_shop['name']}»</b> hisobiga ulangansiz.\n"
                        f"💰 Sizning joriy qarz/nasiya balansingiz: <b>{format_money(shop_cust['balance'])}</b>"
                    )
                    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_client_main_kb(has_own_shop=False))
                    return
                
                # Telefon raqam so'rash
                await state.set_state(CustomerRegisterState.waiting_for_phone)
                await state.update_data(shop_id=shop_id, shop_name=target_shop['name'])
                prompt_phone = (
                    f"👋 Assalomu alaykum, <b>{user_full_name}</b>!\n\n"
                    f"📒 Siz <b>«{target_shop['name']}»</b> Qarz va Nasiya hisobiga ulanmoqdasiz.\n\n"
                    f"📱 Ulanish va hisob-kitoblaringizni kuzatib borish uchun pastdagi <b>«📱 Telefon raqamni ulashish»</b> tugmasini bosing:"
                )
                await message.answer(prompt_phone, parse_mode="HTML", reply_markup=get_contact_kb())
                return
        except Exception:
            pass

    # 6. Oddiy mijoz (avval ulanib bo'lgan)
    cust_accounts = await db.get_customers_by_telegram_id(user_id)
    if cust_accounts:
        await message.answer(
            f"Assalomu alaykum, <b>{user_full_name}</b>!\nQarz va Nasiya daftariga xush kelibsiz.",
            parse_mode="HTML",
            reply_markup=get_client_main_kb(has_own_shop=False)
        )
        return

    # 7. Yangi tashrif buyuruvchi (Daftar ochish / Tiklash taklifi)
    promo_text = (
        f"👋 Assalomu alaykum, <b>{user_full_name}</b>!\n\n"
        f"📒 <b>Qarz va Nasiya Daftari Botiga xush kelibsiz!</b>\n\n"
        f"Ushbu universal bot quyidagilar uchun mo'ljallangan:\n"
        f"🏪 <b>Barcha turdagi do'konlar</b> (Oziq-ovqat, Kiyim, Zapchast, Qurilish va h.k.)\n"
        f"🛠 <b>Ustalar va xizmatlar</b> (Avtoservis, Santexnik, Mebel, Xizmat ko'rsatish)\n"
        f"👤 <b>Shaxsiy qarz-beruvchilar</b> (Do'stlar, qarindoshlar, ijara, dilerlar)\n\n"
        f"✨ <b>Asosiy imkoniyatlar:</b>\n"
        f"• Qarz va nasiyalarni 3 soniyada kiritish\n"
        f"• Qarzdorga avtomatik Telegram eslatma yuborish\n"
        f"• SMS shablon va to'lov muddatlarini belgilash\n"
        f"• Birgalikda boshqarish uchun sotuvchi/shogirdlarni ulash\n"
        f"• Qarzlarni 1 tiyinigacha aniq nazorat qilish\n\n"
        f"🎁 <b>Siz uchun 1 OY (30 KUN) MUTLAQO BEPUL sinov muddati taqdim etiladi!</b>\n\n"
        f"O'z daftaringizni ochish yoki mavjud daftarni yangi profilga tiklash uchun tanlang 👇"
    )
    await message.answer(promo_text, parse_mode="HTML", reply_markup=get_open_store_kb())

# ==================== MIJOZ TASDIQLASH VA QABUL QILISH ====================

@router.callback_query(F.data.startswith("confirm_join_"))
async def confirm_join_customer_cb(call: CallbackQuery, state: FSMContext):
    shop_id = int(call.data.split("_")[2])
    target_shop = await db.get_shop_by_id(shop_id)
    if not target_shop:
        await call.answer("Hisob topilmadi!", show_alert=True)
        return
        
    await state.set_state(CustomerRegisterState.waiting_for_phone)
    await state.update_data(shop_id=shop_id, shop_name=target_shop['name'])
    prompt_phone = (
        f"📱 <b>«{target_shop['name']}»</b> hisob-kitoblarini bog'lash uchun:\n\n"
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
            f"📒 <b>SIZNING DAFTARINGIZ: «{shop['name']}»</b>\n"
            f"👑 <i>(Siz hozir o'z daftaringiz boshqaruvidasiz)</i>\n"
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
    shop_name = target_shop['name'] if target_shop else "Qarz beruvchi"
    
    cust = await db.register_telegram_customer(
        shop_id=shop_id,
        telegram_id=user_id,
        full_name=user_full_name,
        phone=phone
    )
    await state.clear()
    
    # Qarz beruvchiga bildirishnoma
    if target_shop:
        try:
            admin_notify = (
                f"🔔 <b>Yangi qarzdor/mijoz ulandi!</b>\n\n"
                f"👤 Ism: <b>{user_full_name}</b>\n"
                f"📞 Tel: <code>{phone or 'Kiritilmadi'}</code>\n"
                f"🆔 Telegram ID: <code>{user_id}</code>\n\n"
                f"Qarzdor endi qarz/nasiya daftaringizga kiritildi."
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
        f"📒 Siz <b>«{shop_name}»</b> hisobiga muvaffaqiyatli ulandingiz.\n"
        f"📞 Telefoningiz: <code>{phone or 'Kiritilmadi'}</code>\n"
        f"💰 Sizning joriy qarz/nasiya balansingiz: <b>{format_money(cust['balance'])}</b>\n\n"
        f"Har gal amal bajarilganda bot sizga avtomatik hisobot yuborib turadi."
    )
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_client_main_kb(has_own_shop=has_own_shop))

# ==================== O'Z DAFTARINI OCHISH (TRIAL REGISTER) ====================

@router.callback_query(F.data == "start_open_my_store")
async def start_open_my_store_cb(call: CallbackQuery, state: FSMContext):
    existing = await db.get_shop_by_admin(call.from_user.id)
    if existing:
        await call.answer("Sizda allaqachon daftar mavjud!", show_alert=True)
        return
        
    await state.set_state(UserRegisterShop.shop_name)
    prompt_text = (
        "✍️ <b>Qarz / Nasiya beruvchi nomingizni (Daftar yoki Faoliyat nomi) yozing:</b>\n\n"
        "💡 <i>Sohangizga qarab misollar:</i>\n"
        "1️⃣ 👤 <b>Shaxsiy qarzlar</b> <i>(Dilshodning Qarz Daftari, Shaxsiy qarzlarim)</i>\n"
        "2️⃣ 🛒 <b>Savdo va do'konlar</b> <i>(Baraka Market, Rayhon Kiyimlar, Avto Zapchast, Stroy Material)</i>\n"
        "3️⃣ 🏭 <b>Ishlab chiqarish va sexlar</b> <i>(Mebel sexi, Tikuvchilik sexi, Nonvoyxona, Qandolatchilik)</i>\n"
        "4️⃣ 🛠 <b>Ustaxonalar va xizmatlar</b> <i>(Avtoservis, Santexnik, Mebel ustasi, Remont)</i>\n"
        "5️⃣ 🏠 <b>Ijara va arenda</b> <i>(Kvartira ijarasi, Ofis, Mashina arendasi)</i>\n"
        "6️⃣ 📦 <b>Ulgurji savdo va dilerlar</b> <i>(Optom tovarlar, Yetkazib beruvchilar)</i>\n"
        "7️⃣ 🌾 <b>Qishloq xo'jaligi va fermerlik</b> <i>(Meva-sabzavot, Go'sht-sut mahsulotlari)</i>\n"
        "8️⃣ 🎓 <b>O'quv markazlar va repetitorlar</b> <i>(O'quv kursi, Xususiy repetitorlik)</i>\n"
        "9️⃣ 🚚 <b>Yuk tashish va transport</b> <i>(Logistika, Kuryerlik xizmati)</i>\n"
        "🔟 💼 <b>Frilanserlar va boshqa barcha sohalar</b>\n\n"
        "👇 <b>O'zingizga qulay nomni yozib yuboring:</b>"
    )
    await call.message.answer(prompt_text, parse_mode="HTML", reply_markup=get_cancel_kb())
    await call.answer()

@router.message(UserRegisterShop.shop_name)
async def process_user_shop_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Iltimos, haqiqiy nom kiriting:")
        return
    await state.update_data(shop_name=name)
    await state.set_state(UserRegisterShop.shop_phone)
    await message.answer(
        f"Daftar/Faoliyat nomi: <b>{name}</b>\n\nPastdagi <b>«📱 Telefon raqamni ulashish»</b> tugmasini bosing yoki raqamingizni yozing:",
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
        shop_id = await db.create_shop(data.get('shop_name', 'Yangi daftar'), user_id, phone, days=30)
        await state.clear()
        
        shop_name = data.get('shop_name', 'Daftar')
        welcome_msg = (
            f"🎉 <b>Tabriklaymiz, {user_full_name}!</b>\n\n"
            f"📒 <b>«{shop_name}»</b> daftaringiz muvaffaqiyatli ochildi!\n"
            f"🎁 Sizga <b>30 KUNLIK BEPUL SINOV MUDDATI</b> berildi.\n\n"
            f"Boshqaruv menyusi quyida ochildi 👇"
        )
        is_sa = user_id in config.SUPER_ADMIN_IDS
        await message.answer(welcome_msg, parse_mode="HTML", reply_markup=get_admin_main_kb(is_sa, days_left=30))
        
        # Qarzdorlar uchun maxsus QR kodni rasm qilib chiqarib berish
        from utils.qr import generate_shop_qr
        from aiogram.types import BufferedInputFile
        bot_info = await bot.get_me()
        qr_bio = generate_shop_qr(bot_info.username, shop_id)
        
        qr_caption = (
            f"📲 <b>«{shop_name}» — Ulanish uchun maxsus QR Kod!</b>\n\n"
            f"📌 <b>Buni qarzdorlaringizga berishingiz yoki osib qo'yishingiz mumkin:</b>\n"
            f"Odamlar bu kodni telefon kamerasida skaner qilsa, "
            f"to'g'ridan-to'g'ri sizning daftaringizga <b>Qarzdor</b> bo'lib ulanadi va o'z qarzlarini ko'rib boradi!\n\n"
            f"🔗 To'g'ridan-to'g'ri havola: https://t.me/{bot_info.username}?start=shop_{shop_id}"
        )
        photo_file = BufferedInputFile(qr_bio.getvalue(), filename=f"shop_{shop_id}_qr.png")
        await message.answer_photo(photo=photo_file, caption=qr_caption, parse_mode="HTML")
        
        for sa_id in config.SUPER_ADMIN_IDS:
            try:
                sa_notify = (
                    f"🔔 <b>Yangi daftar ochildi (Trial)!</b>\n\n"
                    f"📒 Daftar: <b>{data.get('shop_name', '')}</b> (ID: {shop_id})\n"
                    f"👤 Egasi: <b>{user_full_name}</b>\n"
                    f"🆔 Telegram ID: <code>{user_id}</code>\n"
                    f"📞 Tel: {phone or 'Kiritilmadi'}\n"
                    f"⏳ Muddat: 30 kun berildi."
                )
                await bot.send_message(chat_id=sa_id, text=sa_notify, parse_mode="HTML")
            except Exception:
                pass
    except Exception as e:
        await message.answer(f"⚠️ Daftar ochishda xatolik yuz berdi: {e}\nIltimos, /start bosib qaytadan urinib ko'ring.")

# ==================== MIJOZ TUGMALARI VA REJIM ALMASHTIRISH ====================

@router.message(F.text.in_(["💳 Qayerda qancha qarzim bor?", "💳 Mening qarz va nasiyalarim", "💳 Mening qarzlarim", "🔄 Yangilash", "👤 Shaxsiy qarzlarim (Xaridor rejimi)", "👤 Shaxsiy qarzlarim (Qarz oluvchi rejimi)"]))
async def show_my_debts(message: Message, bot: Bot):
    user_id = message.from_user.id
    accounts = await db.get_customers_by_telegram_id(user_id)
    own_shop = await db.get_shop_by_admin(user_id)
    has_own_shop = bool(own_shop)
    
    if not accounts:
        msg = (
            f"👤 <b>SHAXSIY HISOBINGIZ (Qarz oluvchi rejimi)</b>\n"
            f"────────────────────\n"
            f"Sizda hozircha hech qayerda qarz yoki nasiya mavjud emas.\n\n"
            f"<i>(Boshqalardan nasiyaga narsa/xizmat olganingizda, ularning QR kodini skaner qilsangiz hisobotlar shu yerda chiqadi).</i>"
        )
        await message.answer(msg, parse_mode="HTML", reply_markup=get_client_main_kb(has_own_shop=has_own_shop))
        return
    
    text = (
        f"👤 <b>SHAXSIY HISOBINGIZ (Qarz oluvchi rejimi)</b>\n"
        f"🛒 <i>(Boshqalardan olgan qarz va nasiyalaringiz)</i>\n"
        f"────────────────────\n\n"
    )
    total_uzs = 0.0
    total_usd = 0.0
    for acc in accounts:
        bal_u = acc.get('balance', 0.0) or 0.0
        bal_d = acc.get('balance_usd', 0.0) or 0.0
        total_uzs += bal_u
        total_usd += bal_d
        
        if bal_u > 0 and bal_d > 0:
            b_str = f"{format_money(bal_u, 'UZS')} | {format_money(bal_d, 'USD')}"
        elif bal_d > 0:
            b_str = format_money(bal_d, 'USD')
        else:
            b_str = format_money(bal_u, 'UZS')
            
        text += f"📒 <b>Qarz / Nasiya beruvchi:</b> {acc['shop_name']}\n"
        text += f"💰 <b>Qarzingiz / Nasiya:</b> <b>{b_str}</b>\n"
        if acc['shop_phone']:
            text += f"📞 <b>Telefon:</b> <code>{acc['shop_phone']}</code>\n"
        
        shop = await db.get_shop_by_id(acc['shop_id'])
        if shop:
            text += f"💬 <b>Telegram aloqa:</b> <a href='tg://user?id={shop['admin_id']}'>Qarz beruvchiga yozish</a>\n"
            
        text += "────────────────────\n"
        
    if total_uzs > 0 and total_usd > 0:
        total_summary = f"{format_money(total_uzs, 'UZS')} | {format_money(total_usd, 'USD')}"
    elif total_usd > 0:
        total_summary = format_money(total_usd, 'USD')
    else:
        total_summary = format_money(total_uzs, 'UZS')
        
    text += f"\n📊 <b>Jami umumiy qarzingiz: {total_summary}</b>"
    await message.answer(text, parse_mode="HTML", reply_markup=get_client_main_kb(has_own_shop=has_own_shop))

@router.message(F.text.in_(["📒 Mening daftarim (Qarz beruvchi rejimi)", "📒 Mening daftarim (Boshqaruv)", "🏪 Mening do'konim (Do'konchi rejimi)"]))
async def return_to_my_store(message: Message, bot: Bot):
    user_id = message.from_user.id
    shop = await db.get_shop_by_admin(user_id)
    if not shop:
        await message.answer("Sizda hali o'z daftaringiz yo'q. Ochish uchun /start bosing.")
        return
        
    is_valid, days_left, _ = await db.check_shop_subscription(shop['id'])
    is_sa = user_id in config.SUPER_ADMIN_IDS
    text = (
        f"📒 <b>SIZNING DAFTARINGIZ: «{shop['name']}»</b>\n"
        f"👑 <i>(Siz hozir o'z daftaringiz boshqaruvidasiz)</i>\n"
        f"────────────────────\n"
        f"⏳ Obuna muddati: <b>{days_left} kun qoldi</b>.\n\n"
        f"Boshqaruv menyusi quyida 👇"
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

@router.message(F.text.in_(["📥 Qarzlarimni Excelda yuklash", "📥 Shaxsiy qarzlarimni Excelda yuklash"]))
async def download_my_debts_excel(message: Message, bot: Bot):
    user_id = message.from_user.id
    user_full_name = message.from_user.full_name
    accounts = await db.get_customers_by_telegram_id(user_id)
    own_shop = await db.get_shop_by_admin(user_id)
    has_own_shop = bool(own_shop)
    
    if not accounts:
        await message.answer("Sizda hali qarzlar tarixi mavjud emas.", reply_markup=get_client_main_kb(has_own_shop=has_own_shop))
        return
        
    await message.answer("⏳ <i>Shaxsiy qarz va xaridlaringiz bo'yicha Excel hisobot tayyorlanmoqda...</i>", parse_mode="HTML")
    
    try:
        from utils.excel import generate_customer_excel
        from aiogram.types import BufferedInputFile
        from datetime import datetime
        
        bio = await generate_customer_excel(user_id, user_full_name)
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"Shaxsiy_Qarzlarim_{date_str}.xlsx"
        doc = BufferedInputFile(bio.getvalue(), filename=filename)
        
        caption = (
            f"📊 <b>Shaxsiy Qarz va Nasiyalar Hisoboti (.xlsx)</b>\n\n"
            f"👤 Foydalanuvchi: <b>{user_full_name}</b>\n"
            f"📅 Sana: <code>{date_str}</code>\n\n"
            f"<i>(Ushbu faylni Excel, Google Sheets yoki kompyuterda bemalol ochib ko'rishingiz mumkin)</i>"
        )
        await message.answer_document(document=doc, caption=caption, parse_mode="HTML", reply_markup=get_client_main_kb(has_own_shop=has_own_shop))
    except Exception as e:
        await message.answer(f"⚠️ Excel tayyorlashda xatolik: {e}")

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
        text += f"🏪 <b>{acc['shop_name']}</b>:\n"
        txs = await db.get_customer_transactions(acc['id'], limit=5)
        if not txs:
            text += "<i>Amallar yo'q</i>\n"
        else:
            for t in txs:
                icon = "🔴 Qarz:" if t['type'] == 'debt' else "🟢 To'lov:"
                desc = f" ({t['description']})" if t['description'] else ""
                date_str = str(t['created_at'])[:16]
                curr = t.get('currency', 'UZS') or 'UZS'
                text += f"{icon} {format_money(t['amount'], curr)}{desc}\n📅 <i>{date_str}</i>\n"
        text += "────────────────────\n"
        
    await message.answer(text, parse_mode="HTML", reply_markup=get_client_main_kb(has_own_shop=has_own_shop))
