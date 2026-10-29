"""Entry point: khởi tạo DB, Web Server (Webhook + REST API) và Telegram Bot."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

import bank_auto
import db
from config import ADMIN_IDS, BOT_TOKEN, WEB_ENABLED
from handlers import admin as admin_handlers
from handlers import user as user_handlers
from middlewares import UserMiddleware
from webserver import start_webserver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("main")


async def setup_commands(bot: Bot):
    user_cmds = [
        BotCommand(command="start", description="🏠 Mở menu chính"),
        BotCommand(command="menu", description="📋 Hiển thị nhanh menu"),
        BotCommand(command="cancel", description="❌ Hủy thao tác đang nhập"),
    ]
    await bot.set_my_commands(user_cmds, scope=BotCommandScopeDefault())
    admin_cmds = user_cmds + [
        BotCommand(command="admin", description="🛠 Bảng điều khiển Admin"),
        BotCommand(command="baotri", description="🛠 Bật / Tắt chế độ bảo trì shop"),
        BotCommand(command="setmindeposit", description="💵 Cài đặt số tiền nạp tối thiểu"),
        BotCommand(command="icons", description="🎨 Gán icon Premium hàng loạt"),
    ]
    for aid in ADMIN_IDS:
        try:
            await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=aid))
        except Exception:
            pass


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Chưa cấu hình BOT_TOKEN trong file .env")

    await db.init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.outer_middleware(UserMiddleware())
    dp.callback_query.outer_middleware(UserMiddleware())

    # Thứ tự router: admin -> user -> công cụ lấy ID emoji của admin
    dp.include_router(admin_handlers.router)
    dp.include_router(user_handlers.router)
    dp.include_router(admin_handlers.emoji_router)

    web_runner = None
    if WEB_ENABLED:
        try:
            web_runner = await start_webserver(bot)
        except Exception as e:
            log.warning("Không mở được cổng Web (%s) — Bot vẫn chạy bình thường.", e)

    poller_task = bank_auto.start_bank_poller(bot)

    try:
        for attempt in range(10):
            try:
                me = await bot.get_me()
                log.info("Bot started: @%s (id=%s)", me.username, me.id)
                await setup_commands(bot)
                await bot.delete_webhook(drop_pending_updates=True)
                break
            except Exception as e:
                log.warning("Startup connect retry %s/10: %s", attempt + 1, e)
                await asyncio.sleep(2)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        poller_task.cancel()
        if web_runner:
            await web_runner.cleanup()
        await db.close_db()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
