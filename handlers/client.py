from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, CommandObject, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from keyboards.admin_kb import get_admin_main_kb, format_money, get_open_store_kb, get_cancel_kb
from keyboards.superadmin_kb import get_superadmin_main_kb
from keyboards.client_kb import get_client_main_kb
import config

router = Router()

class UserRegisterShop(StatesGroup):
    shop_name = State()
    shop_phone = State()

@router.message(StateFilter(UserRegisterShop), F.text.in_(["❌ Bekor qilish", "/cancel"]))
async def cancel_user_register_cb(message: Message, state: FSMContext):
    await state.clear()
    promo_text = (
        f"👋 Assalomu alaykum, <b>{message.from_user.full_name}</b>!\n\n"
        f"🎁 <b>Siz uchun 1 OY (30 KUN) MUTLAQO BEPUL sinov muddati taqdim etiladi!</b>\n\n"
        f"O'z do'koningizni ochish uchun pastdagi tugmani bosing 👇"
    )
    await message.answer(promo_text, parse_mode="HTML", reply_markup=get_open_store_kb())

@router.message(Command("cancel"))
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, bot: Bot, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user_full_name = message.from_user.full_name
    
    # 1. Super Admin tekshiruvi
    is_sa = (user_id in config.SUPER_ADMIN_IDS)
    
    # 2. Agar sherik (adminlik) taklif havolasi orqali kirayotgan bo'lsa (/start staff_TOKEN)
    args = command.args
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
                cust = await db.register_telegram_customer(
                    shop_id=shop_id,
                    telegram_id=user_id,
                    full_name=user_full_name,
                    phone=None
                )
                
                try:
                    admin_notify = (
                        f"🔔 <b>Yangi mijoz ulandi!</b>\n\n"
                        f"👤 Ism: <b>{user_full_name}</b>\n"
                        f"🆔 Telegram ID: <code>{user_id}</code>\n"
                        f"Mijoz endi do'koningiz qarz daftariga kiritildi."
                    )
                    await bot.send_message(chat_id=target_shop['admin_id'], text=admin_notify, parse_mode="HTML")
                except Exception:
                    pass
                
                welcome_text = (
                    f"Assalomu alaykum, <b>{user_full_name}</b>!\n\n"
                    f"🏪 Siz <b>{target_shop['name']}</b> do'koni tizimiga muvaffaqiyatli ulandingiz.\n"
                    f"💰 Sizning joriy qarz balansingiz: <b>{format_money(cust['balance'])}</b>\n\n"
                    f"Har gal qarzga xarid qilganingizda yoki to'lov qilganingizda bot sizga avtomatik hisobot yuborib turadi."
                )
                await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_client_main_kb())
                return
        except Exception:
            pass

    # 6. Oddiy mijoz (avval ulanib bo'lgan)
    cust_accounts = await db.get_customers_by_telegram_id(user_id)
    if cust_accounts:
        await message.answer(
            f"Assalomu alaykum, <b>{user_full_name}</b>!\nQarz daftariga xush kelibsiz.",
            reply_markup=get_client_main_kb()
        )
        return

    # 7. Yangi tashrif buyuruvchi (Do'kon ochish taklifi)
    promo_text = (
        f"👋 Assalomu alaykum, <b>{user_full_name}</b>!\n\n"
        f"📒 <b>Qarz Daftari Botiga xush kelibsiz!</b>\n\n"
        f"Bu bot mahalla oziq-ovqat va boshqa do'konlar uchun qarz va nasiyalarni avtomatlashtirish, "
        f"mijozlarga avtomatik hisobot yuborish va qarz aylanmasini nazorat qilish uchun mo'ljallangan.\n\n"
        f"🎁 <b>Siz uchun 1 OY (30 KUN) MUTLAQO BEPUL sinov muddati taqdim etiladi!</b>\n\n"
        f"O'z do'koningizni ochish uchun pastdagi tugmani bosing 👇"
    )
    await message.answer(promo_text, parse_mode="HTML", reply_markup=get_open_store_kb())

from keyboards.admin_kb import get_admin_main_kb, format_money, get_open_store_kb, get_cancel_kb, get_contact_kb, get_subscription_kb

# ==================== O'Z DO'KONINI OCHISH (TRIAL REGISTER) ====================

@router.callback_query(F.data == "start_open_my_store")
async def start_open_my_store_cb(call: CallbackQuery, state: FSMContext):
    existing = await db.get_shop_by_admin(call.from_user.id)
    if existing:
        await call.answer("Sizda allaqachon do'kon mavjud!", show_alert=True)
        return
        
    await state.set_state(UserRegisterShop.shop_name)
    await call.message.answer(
        "🏪 <b>Do'koningiz nomini kiriting:</b>\n<i>(Masalan: Omad Oziq-ovqat, Baraka Market)</i>",
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
        
        welcome_msg = (
            f"🎉 <b>Tabriklaymiz, {user_full_name}!</b>\n\n"
            f"🏪 <b>{data.get('shop_name', 'Do''kon')}</b> muvaffaqiyatli ochildi!\n"
            f"🎁 Sizga <b>30 KUNLIK BEPUL SINOV MUDDATI</b> berildi.\n\n"
            f"Endi do'kon QR kodini chiqarib osib qo'yishingiz, qarzlarni yozishingiz va to'lovlarni qabul qilishingiz mumkin."
        )
        is_sa = user_id in config.SUPER_ADMIN_IDS
        await message.answer(welcome_msg, parse_mode="HTML", reply_markup=get_admin_main_kb(is_sa, days_left=30))
        
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

# ==================== MIJOZ TUGMALARI ====================

@router.message(F.text.in_(["💳 Mening qarzlarim", "🔄 Yangilash"]))
async def show_my_debts(message: Message, bot: Bot):
    user_id = message.from_user.id
    accounts = await db.get_customers_by_telegram_id(user_id)
    
    if not accounts:
        await message.answer("Siz hali hech qaysi do'kon tizimiga ulanmagansiz. Do'kon QR kodini skaner qiling.")
        return
    
    text = "💳 <b>Sizning qarzlaringiz:</b>\n\n"
    total_all = 0.0
    for acc in accounts:
        text += f"🏪 <b>Do'kon:</b> {acc['shop_name']}\n"
        text += f"💰 <b>Qarzingiz:</b> {format_money(acc['balance'])}\n"
        if acc['shop_phone']:
            text += f"📞 <b>Telefon:</b> {acc['shop_phone']}\n"
        
        shop = await db.get_shop_by_id(acc['shop_id'])
        if shop:
            text += f"💬 <b>Telegram aloqa:</b> <a href='tg://user?id={shop['admin_id']}'>Do'konchiga yozish</a>\n"
            
        text += "────────────────────\n"
        total_all += acc['balance']
        
    text += f"\n📊 <b>Jami umumiy qarzingiz: {format_money(total_all)}</b>"
    await message.answer(text, parse_mode="HTML", reply_markup=get_client_main_kb())

@router.message(F.text == "📜 Xaridlar tarixi")
async def show_my_history(message: Message):
    user_id = message.from_user.id
    accounts = await db.get_customers_by_telegram_id(user_id)
    
    if not accounts:
        await message.answer("Siz hali hech qaysi do'konga ulanmagansiz.")
        return
    
    text = "📜 <b>Oxirgi amallar tarixi:</b>\n\n"
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
                text += f"{icon} {format_money(t['amount'])}{desc}\n📅 <i>{date_str}</i>\n"
        text += "────────────────────\n"
        
    await message.answer(text, parse_mode="HTML", reply_markup=get_client_main_kb())
