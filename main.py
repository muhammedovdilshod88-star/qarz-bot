import asyncio
import logging
import os
import sys
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import config
import database as db
from handlers import superadmin, shop_admin, client

# Loglarni sozlash
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

async def handle_health_check(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    """Render Web Service uchun port ochuvchi yengil server"""
    port = int(os.environ.get("PORT", 10000))
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    app.router.add_get("/health", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health check server {port}-portda ishga tushdi.")

from datetime import datetime, timezone, timedelta
from utils.excel import generate_full_platform_excel
from aiogram.types import BufferedInputFile

# Toshkent vaqti mintaqasi (UTC+5)
TASHKENT_TZ = timezone(timedelta(hours=5))

async def daily_backup_scheduler(bot: Bot):
    """Har kuni kechasi soat 23:00 da (Toshkent vaqti) Super Adminga avtomatik to'liq Excel zaxira yuborish"""
    last_backup_date = None
    while True:
        try:
            now_tashkent = datetime.now(TASHKENT_TZ)
            today_str = now_tashkent.strftime("%Y-%m-%d")
            
            # Agar soat 23 bo'lsa va bugun hali yuborilmagan bo'lsa
            if now_tashkent.hour >= 23 and last_backup_date != today_str:
                bio = await generate_full_platform_excel()
                filename = f"Avto_Backup_{today_str}.xlsx"
                doc = BufferedInputFile(bio.getvalue(), filename=filename)
                
                for sa_id in config.SUPER_ADMIN_IDS:
                    try:
                        await bot.send_document(
                            chat_id=sa_id,
                            document=doc,
                            caption=f"🛡 <b>Avtomatik Kunlik Zaxira (Backup)</b>\n📅 Sana: <code>{today_str}</code> (23:00 Toshkent vaqti)\nBarcha do'konlar va qarz ma'lumotlari xavfsiz saqlangan.",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.error(f"Backup yuborishda xatolik: {e}")
                        
                last_backup_date = today_str
                logger.info(f"Kunlik zaxira muvaffaqiyatli yuborildi: {today_str}")

            # Har 1 daqiqada tekshirib turadi
            await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"Backup scheduler xatosi: {e}")
            await asyncio.sleep(60)

async def due_reminder_scheduler(bot: Bot):
    """Muddati yetib kelgan qarzdorlarga avtomatik muloyim eslatma jo'natish"""
    while True:
        try:
            # Har 12 soatda bir marta tekshirish (43200 soniya)
            await asyncio.sleep(43200)
            due_customers = await db.get_due_reminders()
            for c in due_customers:
                try:
                    due_date_str = str(c['due_date'])[:10]
                    text = (
                        f"⏰ <b>Hurmatli {c['full_name']}!</b>\n\n"
                        f"<b>«{c['shop_name']}»</b> do'konidagi kelishilgan to'lov muddati (<code>{due_date_str}</code>) yetib keldi.\n"
                        f"💰 Joriy qarz/nasiya balansingiz: <b>{c['balance']:,.0f} so'm</b>.\n\n"
                        f"💳 <i>Imkoningiz bo'lganda to'lovni amalga oshirishingizni so'raymiz. Xaridingiz uchun rahmat!</i>\n"
                        f"💬 <a href='tg://user?id={c['shop_admin_id']}'>Do'konchi bilan bog'lanish</a>"
                    )
                    await bot.send_message(chat_id=c['telegram_id'], text=text, parse_mode="HTML")
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Due reminder scheduler xatosi: {e}")
            await asyncio.sleep(60)

async def main():
    logger.info("Ma'lumotlar bazasi initsializatsiya qilinmoqda...")
    await db.init_db()

    # Render port tekshiruvi uchun web serverni yoqish
    await start_web_server()

    # Bot va Dispatcher yaratish
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Routerlarni ro'yxatdan o'tkazish
    dp.include_router(superadmin.router)
    dp.include_router(shop_admin.router)
    dp.include_router(client.router)

    # Avtomatik kunlik backup va eslatma vazifalarini fonda yoqish
    asyncio.create_task(daily_backup_scheduler(bot))
    asyncio.create_task(due_reminder_scheduler(bot))

    # Global xatoliklar ushlovchisi (Error Handler)
    @dp.error()
    async def global_error_handler(event, bot: Bot):
        logger.error(f"Global xatolik: {event.exception}")
        err_msg = (
            f"⚠️ <b>DIQQAT: Botda xatolik yuz berdi!</b>\n\n"
            f"❌ <b>Xatolik matni:</b>\n<code>{str(event.exception)[:400]}</code>\n\n"
            f"Tizim uzluksiz ishlashda davom etmoqda."
        )
        for sa_id in config.SUPER_ADMIN_IDS:
            try:
                await bot.send_message(chat_id=sa_id, text=err_msg, parse_mode="HTML")
            except Exception:
                pass

    bot_info = await bot.get_me()
    logger.info(f"Bot ishga tushdi: @{bot_info.username} (ID: {bot_info.id})")

    # Super Adminga bot ishga tushgani haqida signal yuborish
    for sa_id in config.SUPER_ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=sa_id,
                text=f"🟢 <b>Qarz va Nasiya Boti (@{bot_info.username}) serverda muvaffaqiyatli ishga tushdi va 24/7 faol!</b>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    # Cheksiz qayta ulanish zanjiri (Uzilib qolsa ham avtomatik qayta ulanadi)
    while True:
        try:
            logger.info("Polling boshlanmoqda...")
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot, handle_signals=False)
        except Exception as e:
            logger.error(f"Pollingda xatolik yuz berdi: {e}. 5 soniyadan so'ng qayta ulanmoqda...")
            err_poll_msg = f"🔴 <b>DIQQAT: Bot ulanishida uzilish yuz berdi!</b>\n<code>{str(e)[:300]}</code>\nQayta ulanmoqda..."
            for sa_id in config.SUPER_ADMIN_IDS:
                try:
                    await bot.send_message(chat_id=sa_id, text=err_poll_msg, parse_mode="HTML")
                except Exception:
                    pass
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
