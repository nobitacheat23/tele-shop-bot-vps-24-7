"""Tiện ích giao diện: dựng nút có icon Premium, gửi/sửa tin nhắn an toàn."""
import html
import logging
import re

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

import services as S
from config import BUTTON_STYLE, CUSTOM_EMOJI_IN_TEXT
from texts import MENU_ITEMS, t

log = logging.getLogger(__name__)
esc = html.escape

SOLDOUT = "❌"


# ---------------- buttons ----------------
def btn(text, cb=None, url=None, icon=None, emoji="", style="default") -> InlineKeyboardButton:
    """Nút inline. Nếu có `icon` (custom_emoji_id) -> hiển thị icon Premium, ngược lại dùng emoji thường."""
    if style == "default":
        style = BUTTON_STYLE
    label = text if icon or not emoji else f"{emoji} {text}"
    return InlineKeyboardButton(
        text=label[:120],
        callback_data=cb,
        url=url,
        icon_custom_emoji_id=icon or None,
        style=style or None,
    )


def kb(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r])


def ce(icon: str | None, fallback: str) -> str:
    """Custom emoji trong nội dung tin nhắn (HTML)."""
    if icon and CUSTOM_EMOJI_IN_TEXT:
        return f'<tg-emoji emoji-id="{icon}">{fallback or "⭐"}</tg-emoji>'
    return fallback


async def menu_icon(key: str):
    return await S.get_setting(f"icon_{key}")


async def soldout_icon():
    return await S.get_setting("icon_soldout")


def item_icon(item: dict):
    """(icon_id, emoji) của sản phẩm/danh mục, ưu tiên icon riêng rồi tới icon danh mục."""
    icon = item.get("custom_emoji_id") or item.get("cat_icon")
    emoji = item.get("emoji") or item.get("cat_emoji") or ""
    return icon, emoji


async def product_button(p: dict, user: dict, cb: str) -> InlineKeyboardButton:
    stock = "∞" if p["is_infinite_stock"] else str(p["stock"])
    text = f"{p['name']} | {S.fmt_k(S.unit_price(user, p))} | 📦 {stock}"
    if not S.in_stock(p):
        sicon = await soldout_icon()
        return btn(text, cb, icon=sicon, emoji=SOLDOUT)
    icon, emoji = item_icon(p)
    return btn(text, cb, icon=icon, emoji=emoji)


async def category_button(c: dict, cb: str) -> InlineKeyboardButton:
    if not c["is_active"] or (c.get("n_products", 0) > 0 and not c["avail"]):
        sicon = await soldout_icon()
        return btn(c["name"], cb, icon=sicon, emoji=SOLDOUT)
    return btn(c["name"], cb, icon=c.get("custom_emoji_id"), emoji=c.get("emoji") or "")


async def main_menu_kb(lang: str) -> InlineKeyboardMarkup:
    async def b(key):
        return btn(t(lang, f"m_{key}"), f"u:{key}", icon=await menu_icon(key), emoji=dict(MENU_ITEMS)[key])

    return kb([
        [await b("buy")],
        [await b("profile"), await b("history")],
        [await b("wallet"), await b("api")],
        [await b("support"), await b("warranty")],
        [await b("language")],
    ])


async def reply_menu_kb(lang: str) -> ReplyKeyboardMarkup:
    async def b(key):
        icon = await menu_icon(key)
        label = t(lang, f"m_{key}")
        return KeyboardButton(
            text=label if icon else f"{dict(MENU_ITEMS)[key]} {label}",
            icon_custom_emoji_id=icon or None,
            style=BUTTON_STYLE or None,
        )

    return ReplyKeyboardMarkup(
        keyboard=[
            [await b("buy")],
            [await b("profile"), await b("history"), await b("wallet")],
            [await b("api"), await b("support"), await b("warranty")],
            [await b("language")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=t(lang, "placeholder"),
    )


# ---------------- safe send / edit ----------------
_TG_EMOJI_RE = re.compile(r'<tg-emoji emoji-id="[^"]*">(.*?)</tg-emoji>', re.S)


def _strip_markup(markup):
    """Bỏ icon Premium khỏi nút (fallback khi Telegram từ chối icon)."""
    if isinstance(markup, InlineKeyboardMarkup):
        rows = []
        for row in markup.inline_keyboard:
            new = []
            for b in row:
                text = b.text
                if b.icon_custom_emoji_id:
                    text = f"⭐ {text}" if not text.startswith(SOLDOUT) else text
                new.append(b.model_copy(update={"icon_custom_emoji_id": None, "text": text}))
            rows.append(new)
        return InlineKeyboardMarkup(inline_keyboard=rows)
    if isinstance(markup, ReplyKeyboardMarkup):
        rows = [[b.model_copy(update={"icon_custom_emoji_id": None}) for b in r] for r in markup.keyboard]
        return markup.model_copy(update={"keyboard": rows})
    return markup


def _strip_text(text):
    return _TG_EMOJI_RE.sub(r"\1", text) if text else text


def _is_icon_error(e: Exception) -> bool:
    s = str(e).lower()
    return any(k in s for k in ("emoji", "icon", "button", "style", "entit", "document_invalid"))


async def answer(message: Message, text: str, markup=None, **kw):
    try:
        return await message.answer(text, reply_markup=markup, **kw)
    except TelegramBadRequest as e:
        if not _is_icon_error(e):
            raise
        log.warning("Fallback (no premium emoji): %s", e)
        return await message.answer(_strip_text(text), reply_markup=_strip_markup(markup), **kw)


async def send(bot, chat_id: int, text: str, markup=None, **kw):
    try:
        return await bot.send_message(chat_id, text, reply_markup=markup, **kw)
    except TelegramBadRequest as e:
        if not _is_icon_error(e):
            raise
        return await bot.send_message(chat_id, _strip_text(text), reply_markup=_strip_markup(markup), **kw)


async def edit(cb: CallbackQuery, text: str, markup=None, **kw):
    """Sửa tin nhắn hiện tại; nếu không sửa được (vd tin nhắn ảnh) thì gửi tin mới."""
    msg = cb.message
    try:
        if msg and msg.text is not None:
            return await msg.edit_text(text, reply_markup=markup, **kw)
    except TelegramBadRequest as e:
        s = str(e).lower()
        if "not modified" in s:
            return msg
        if _is_icon_error(e):
            try:
                return await msg.edit_text(_strip_text(text), reply_markup=_strip_markup(markup), **kw)
            except TelegramBadRequest as e2:
                if "not modified" in str(e2).lower():
                    return msg
        elif "can't be edited" not in s and "no text" not in s and "not found" not in s:
            raise
    return await answer(msg, text, markup, **kw)


def custom_emoji_ids(message: Message) -> list[str]:
    ents = (message.entities or []) + (message.caption_entities or [])
    return [e.custom_emoji_id for e in ents if e.type == "custom_emoji" and e.custom_emoji_id]
