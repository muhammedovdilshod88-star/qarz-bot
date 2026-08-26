from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.fsm.context import FSMContext
import database as db
from keyboards.admin_kb import get_admin_main_kb, format_money
from keyboards.superadmin_kb import get_superadmin_main_kb
from keyboards.client_kb import get_client_main_kb
import config

router = Router()

@router.message(Command("cancel"))
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, bot: Bot, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user_full_name = message.from_user.full_name
    
    # 1. Super Admin tekshiruvi (agar hali do'konlar bo'lmasa yoki ro'yxatda bo'lsa)
    is_sa = (user_id in config.SUPER_ADMIN_IDS) or (len(config.SUPER_ADMIN_IDS) == 0 and not await db.get_shop_by_admin(user_id) and not await db.list_all_shops())
    
    # 2. Agar sherik (adminlik) taklif havolasi orqali kirayotgan bo'lsa (/start staff_TOKEN)
    args = command.args
    if args and args.startswith("staff_"):
        token = args.replace("staff_", "")
        shop, msg = await db.use_staff_invite(token, user_id, user_full_name)
        if shop:
            # Asosiy do'kon egasiga xabar berish
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
                
            welcome_staff = (
                f"🎉 <b>Tabriklaymiz, {user_full_name}!</b>\n\n"
                f"Siz <b>{shop['name']}</b> do'koni administratorlar safiga qo'shildingiz.\n"
                f"Endi siz ham mijozlar qarzlarini yozishingiz, to'lovlarni qabul qilishingiz va yangi mijozlar qo'shishingiz mumkin."
            )
            await message.answer(welcome_staff, parse_mode="HTML", reply_markup=get_admin_main_kb(False))
            return
        else:
            await message.answer(f"⚠️ {msg}")
            return

    # 3. Do'konchi (Admin yoki Sherik) tekshiruvi
    shop = await db.get_shop_by_admin(user_id)
    if shop:
        if not shop['is_active']:
            await message.answer("⚠️ Sizning do'koningiz faolligi vaqtincha to'xtatilgan. Iltimos, admin bilan bog'laning.")
            return
        
        await message.answer(
            f"Assalomu alaykum, <b>{user_full_name}</b>!\n"
            f"🏪 Do'kon: <b>{shop['name']}</b> boshqaruv paneliga xush kelibsiz.",
            parse_mode="HTML",
            reply_markup=get_admin_main_kb(is_sa)
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

    # 3. Agar maxsus mijoz taklif havolasi orqali kirayotgan bo'lsa (/start c_CUSTOMERID)
    args = command.args
    if args and args.startswith("c_"):
        try:
            cust_id = int(args.replace("c_", ""))
            cust = await db.link_customer_telegram(cust_id, user_id, user_full_name)
            if cust:
                shop = await db.get_shop_by_id(cust['shop_id'])
                shop_name = shop['name'] if shop else "Do'kon"
                
                # Do'konchiga bildirishnoma
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

    # 4. Agar umumiy QR kod orqali kirayotgan bo'lsa (/start shop_ID)
    if args and args.startswith("shop_"):
        try:
            shop_id = int(args.replace("shop_", ""))
            target_shop = await db.get_shop_by_id(shop_id)
            if target_shop and target_shop['is_active']:
                # Mijozni ro'yxatdan o'tkazish yoki mavjudini olish
                cust = await db.register_telegram_customer(
                    shop_id=shop_id,
                    telegram_id=user_id,
                    full_name=user_full_name,
                    phone=None
                )
                
                # Do'konchiga xabar berish
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

    # 5. Oddiy mijoz (avval ulanib bo'lgan)
    cust_accounts = await db.get_customers_by_telegram_id(user_id)
    if cust_accounts:
        await message.answer(
            f"Assalomu alaykum, <b>{user_full_name}</b>!\nQarz daftariga xush kelibsiz.",
            reply_markup=get_client_main_kb()
        )
        return

    # Agar hech kim bo'lmasa
    await message.answer(
        "👋 Assalomu alaykum!\n\n"
        "Ushbu bot mahalla do'konlari uchun qarz daftari hisoblanadi.\n"
        "Do'koningizga ulanish uchun do'kondagi <b>QR kodni</b> skaner qiling yoki havolasidan kiring.",
        parse_mode="HTML"
    )

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
        
        # Do'konchining telegram profili havolasi
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
