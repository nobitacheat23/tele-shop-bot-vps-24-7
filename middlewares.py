from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

import services as S
from config import is_admin
from texts import t


class UserMiddleware(BaseMiddleware):
    """Tự tạo/cập nhật user, inject `user` vào handler, chặn user bị ban."""

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
        if user["is_banned"] and not is_admin(tg_user.id):
            msg = t(user["language"], "banned")
            if isinstance(event, CallbackQuery):
                await event.answer(msg, show_alert=True)
            elif isinstance(event, Message):
                await event.answer(msg)
            return None
        data["user"] = user
        data["lang"] = user["language"]
        return await handler(event, data)
