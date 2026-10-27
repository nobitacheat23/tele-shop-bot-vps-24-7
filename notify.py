"""Thông báo dùng chung (admin / user) cho bot + webserver."""
import logging

import services as S
import ui
from config import ADMIN_IDS
from ui import btn, esc, kb
from texts import t

log = logging.getLogger(__name__)


async def notify_admins(bot, text: str, markup=None, **kw):
    for aid in ADMIN_IDS:
        try:
            await ui.send(bot, aid, text, markup, **kw)
        except Exception as e:  # noqa
            log.warning("notify admin %s failed: %s", aid, e)


async def notify_user(bot, uid: int, text: str, markup=None, **kw) -> bool:
    try:
        await ui.send(bot, uid, text, markup, **kw)
        return True
    except Exception as e:  # noqa
        log.info("notify user %s failed: %s", uid, e)
        return False


def ticket_kb(tid: int):
    return kb([
        [btn("✅ Đổi Acc Mới", f"wr_ok:{tid}", style="success")],
        [btn("💸 Hoàn Tiền Ví", f"wr_ref:{tid}", style="primary")],
        [btn("❌ Từ Chối", f"wr_no:{tid}", style="danger")],
    ])


def crypto_kb(dep_id: int):
    return kb([[btn("✅ Duyệt", f"cr_ok:{dep_id}", style="success"),
                btn("❌ Từ chối", f"cr_no:{dep_id}", style="danger")]])


def service_order_kb(order_id: str):
    return kb([[btn("📤 Gửi nội dung cho khách", f"od_send:{order_id}")],
               [btn("💸 Hoàn tiền đơn", f"od_ref:{order_id}", style="danger")]])


async def deposit_success(bot, uid: int, amount: int, method: str, balance: int):
    u = await S.get_user(uid)
    lang = u["language"] if u else "vi"
    await notify_user(bot, uid, t(lang, "deposit_ok", amount=S.fmt_money(amount), method=method,
                                  balance=S.fmt_money(balance)))
    name = f"@{u['username']}" if u and u["username"] else esc(u["full_name"] if u else "")
    await notify_admins(bot, f"💰 <b>NẠP TIỀN</b>\n👤 {name} (<code>{uid}</code>)\n💵 +{S.fmt_money(amount)}"
                             f"\n🔖 {method}\n👛 Số dư: {S.fmt_money(balance)}")


MEGAPHONE_ICON_ID = "5469903029144657419"   # 📣 3D Orange Megaphone (RestrictedEmoji)
GREEN_PLUS_ICON_ID = "5226945370684140473"  # ➕ 3D Green Plus (RestrictedEmoji)
CHART_ICON_ID = "5431577498364158238"       # 📊 3D Green Bar Chart with Coin (RestrictedEmoji)
MONEY_ICON_ID = "5472030678633684592"       # 💸 3D Green Money Bill (RestrictedEmoji)
BUY_CART_ICON_ID = "5431499171045581032"    # 🛒 3D Shopping Cart on Button (RestrictedEmoji)


def format_new_stock_message(p: dict, added_qty: int) -> tuple[str, object]:
    """Định dạng tin nhắn '📣 Thông báo có hàng mới' với đầy đủ 3D Custom Emoji Premium & nút [🛒 Mua ngay]."""
    icon, emoji = ui.item_icon(p)
    brand_icon = ui.ce(icon, emoji or "📦")
    mega_icon = ui.ce(MEGAPHONE_ICON_ID, "📣")
    add_icon = ui.ce(GREEN_PLUS_ICON_ID, "➕")
    stock_icon = ui.ce(CHART_ICON_ID, "📊")
    price_icon = ui.ce(MONEY_ICON_ID, "💸")

    stock_val = "∞" if p.get("is_infinite_stock") else str(p.get("stock", 0))
    price_int = int(p.get("price") or 0)
    price_dots = f"{price_int:,}".replace(",", ".")
    usdt = price_int / 25500.0
    text = (
        f"{mega_icon} Thông báo có hàng mới\n\n"
        f"{brand_icon} {esc(p['name'])}\n"
        f"{add_icon} Thêm: {added_qty}\n"
        f"{stock_icon} Tồn Kho: {stock_val}\n"
        f"{price_icon} Giá: {price_dots}<u>đ</u> (~{usdt:.2f} USDT)"
    )
    markup = kb([[btn("Mua ngay", f"p:{p['id']}", icon=BUY_CART_ICON_ID, emoji="🛒", style="success")]])
    return text, markup


async def broadcast_new_stock(bot, product_id: int, added_qty: int) -> tuple[int, int]:
    """Gửi thông báo có hàng mới của sản phẩm tới toàn bộ người dùng trong Database."""
    import asyncio
    import db

    p = await S.get_product(product_id)
    if not p:
        return 0, 0
    text, markup = format_new_stock_message(p, max(1, added_qty))
    users = await db.fetchall("SELECT user_id FROM users WHERE is_banned=0")
    ok = fail = 0
    for u in users:
        sent = await notify_user(bot, u["user_id"], text, markup)
        if sent:
            ok += 1
        else:
            fail += 1
        await asyncio.sleep(0.04)
    return ok, fail
