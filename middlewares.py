from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

import config
from config import is_admin
import services as S
from texts import t
import ui


class UserMiddleware(BaseMiddleware):
    """Tự tạo/cập nhật user, inject `user` vào handler, chặn user bị ban, kiểm tra chế độ bảo trì."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = getattr(event, "from_user", None)
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)
        if isinstance(event, Message) and event.chat.type != "private":
            return None  # shop chỉ hoạt động trong chat riêng

        user = await S.upsert_user(tg_user)
        admin_flag = is_admin(tg_user.id, tg_user.username)

        # 1. Chặn user bị ban
        if user["is_banned"] and not admin_flag:
            msg = t(user["language"], "banned")
            if isinstance(event, CallbackQuery):
                await event.answer(msg, show_alert=True)
            elif isinstance(event, Message):
                await event.answer(msg)
            return None

        # 2. Kiểm tra chế độ bảo trì hệ thống (Admin bỏ qua bảo trì)
        if await S.is_maintenance() and not admin_flag:
            reason = await S.get_maintenance_reason()
            support_user = config.SUPPORT_USERNAME
            maintenance_text = (
                "🛠 <b>HỆ THỐNG ĐANG BẢO TRÌ NÂNG CẤP</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"• {reason}\n\n"
                "⏳ <i>Hệ thống sẽ sớm hoạt động trở lại. Quý khách cần hỗ trợ gấp vui lòng liên hệ Admin CSKH:</i>"
            )
            rows = []
            if support_user:
                rows.append([ui.btn("💬 Hỗ trợ CSKH 24/7", url=f"https://t.me/{support_user}")])
            markup = ui.kb(rows) if rows else None

            if isinstance(event, CallbackQuery):
                await event.answer("🛠 Shop đang bảo trì nâng cấp, vui lòng quay lại sau!", show_alert=True)
                try:
                    await event.message.edit_text(maintenance_text, reply_markup=markup, parse_mode="HTML")
                except Exception:
                    pass
            elif isinstance(event, Message):
                await event.answer(maintenance_text, reply_markup=markup, parse_mode="HTML")
            return None

        data["user"] = user
        data["lang"] = user["language"]
        return await handler(event, data)
