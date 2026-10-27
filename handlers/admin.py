"""Admin Panel (/admin)."""
import asyncio
import logging
import re
import secrets
from urllib.parse import quote

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

import bank_auto
import db
import notify
import services as S
import ui
from config import PUBLIC_URL, is_admin
from texts import MENU_EMOJI, MENU_ITEMS, TEXTS, t
from ui import btn, esc, kb

log = logging.getLogger(__name__)
router = Router(name="admin")


class IsAdmin(Filter):
    async def __call__(self, event) -> bool:
        return bool(event.from_user) and is_admin(event.from_user.id)


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


class AdminSG(StatesGroup):
    input = State()


BACK = lambda cb="a:home": btn("« Quay lại", cb, style=None)  # noqa: E731
ICON_KEYS = [k for k, _ in MENU_ITEMS] + ["refresh", "soldout"]
ICON_LABELS = {**{k: TEXTS["vi"][f"m_{k}"] for k, _ in MENU_ITEMS},
               "refresh": "Cập nhật sản phẩm", "soldout": "Hết hàng (❌)"}
ICON_EMOJI = {**MENU_EMOJI, "refresh": "🧿", "soldout": "❌"}


async def ask(message: Message, state: FSMContext, action: str, prompt: str, **data):
    await state.set_state(AdminSG.input)
    await state.update_data(action=action, **data)
    await message.answer(prompt + "\n\n<i>Gõ /cancel để hủy.</i>")


def parse_icon(message: Message):
    """Trả về (ok, icon_id|None). Chấp nhận: gửi emoji Premium, hoặc ID số, hoặc 0 để xóa."""
    ids = ui.custom_emoji_ids(message)
    if ids:
        return True, ids[0]
    txt = (message.text or "").strip()
    if txt.isdigit() and len(txt) > 5:
        return True, txt
    if txt in ("0", "-", "xoa", "xóa", "none"):
        return True, None
    return False, None


def strip_custom_emoji(text: str, entities) -> str:
    b = text.encode("utf-16-le")
    for e in sorted([e for e in (entities or []) if e.type == "custom_emoji"], key=lambda e: e.offset, reverse=True):
        b = b[:e.offset * 2] + b[(e.offset + e.length) * 2:]
    return b.decode("utf-16-le", errors="ignore").strip()


def norm(s: str) -> str:
    return re.sub(r"[\W_]+", "", (s or "").upper())


# ======================================================================
# DASHBOARD
# ======================================================================
async def render_home():
    n_users = await db.fetchval("SELECT COUNT(*) FROM users", default=0)
    n_tk = await db.fetchval("SELECT COUNT(*) FROM tickets WHERE status='pending'", default=0)
    n_dep = await db.fetchval("SELECT COUNT(*) FROM deposits WHERE status='pending'", default=0)
    rev = await db.fetchval("SELECT SUM(total_price) FROM orders WHERE status!='refunded' "
                            "AND date(created_at)=date('now','localtime')", default=0)
    n_ord = await db.fetchval("SELECT COUNT(*) FROM orders WHERE date(created_at)=date('now','localtime')", default=0)
    cfg = await bank_auto.get_bank_config()
    bank_label = f"{cfg['bank_id']} - {cfg['account']}" if cfg["account"] else "Chưa cài"
    auto_label = "✅ BẬT" if (cfg["auto_approve"] or cfg["sepay_token"] or cfg["casso_key"] or cfg["web2m_url"]) else "⬜ TẮT"
    text = (f"🛠 <b>ADMIN DASHBOARD</b>\n\n👥 Tổng user: <b>{n_users}</b>\n"
            f"🧾 Đơn hôm nay: <b>{n_ord}</b>\n💰 Doanh thu hôm nay: <b>{S.fmt_money(rev)}</b>\n"
            f"🛡 Bảo hành chờ xử lý: <b>{n_tk}</b> | ⏳ Nạp chờ duyệt: <b>{n_dep}</b>\n"
            f"🏦 Bank: <code>{esc(bank_label)}</code> | ⚡ Auto duyệt: <b>{auto_label}</b>")
    return text, kb([
        [btn("🏦 Ngân hàng & Auto Bank", "a:bank")],
        [btn("👥 Người dùng", "a:users"), btn("📂 Sản phẩm & Kho", "a:cats")],
        [btn("🧾 Tra mã đơn", "a:order"), btn(f"🛡 Bảo hành ({n_tk})", "a:tickets")],
        [btn("📊 Thống kê", "st:1"), btn("📢 Broadcast", "a:bc")],
        [btn("🔌 API Users", "a:apiusers"), btn("🎨 Icon Premium", "a:icons")],
        [btn(f"💎 Nạp chờ duyệt ({n_dep})", "a:pdep")],
    ])


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    text, markup = await render_home()
    await ui.answer(message, text, markup)


@router.callback_query(F.data == "a:home")
async def cb_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await ui.edit(cb, *await render_home())
    await cb.answer()


@router.message(Command("cancel"), AdminSG.input)
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Đã hủy.", reply_markup=kb([[btn("🛠 Admin", "a:home")]]))


# ======================================================================
# USERS
# ======================================================================
async def render_user(uid: int):
    u = await S.get_user(uid)
    if not u:
        return None
    n_orders = await db.fetchval("SELECT COUNT(*) FROM orders WHERE user_id=?", (uid,), 0)
    text = (f"👤 <b>THÔNG TIN NGƯỜI DÙNG</b>\n\n🆔 ID: <code>{uid}</code>\n"
            f"👤 Username: {('@' + esc(u['username'])) if u['username'] else '-'}\n📛 Tên: {esc(u['full_name'] or '-')}\n"
            f"💰 Số dư: <b>{S.fmt_money(u['balance'])}</b>\n📥 Tổng nạp: {S.fmt_money(u['total_deposited'])}\n"
            f"📤 Tổng tiêu: {S.fmt_money(u['total_spent'])}\n🧾 Số đơn: {n_orders}\n"
            f"👑 Cấp bậc: <b>{'Đại lý / CTV' if u['role'] == 'reseller' else 'Thành viên'}</b> | Chiết khấu: <b>{u['discount_rate']:g}%</b>\n"
            f"🔑 API: {'✅ Đang có key' if u['api_key'] else '❌ Chưa có'} | ⏱ {u['api_rate_limit']} req/phút\n"
            f"🚦 Trạng thái: {'🚫 BỊ KHÓA' if u['is_banned'] else '✅ Hoạt động'}\n📅 Tham gia: {u['created_at']}")
    return text, kb([
        [btn("➕ Cộng tiền", f"au_add:{uid}", style="success"), btn("➖ Trừ tiền", f"au_sub:{uid}", style="danger")],
        [btn("👑 Hạ Thành viên" if u["role"] == "reseller" else "👑 Lên Đại lý", f"au_role:{uid}"),
         btn("💯 Đặt % chiết khấu", f"au_disc:{uid}")],
        [btn("🔓 Mở khóa" if u["is_banned"] else "🔒 Khóa (Ban)", f"au_ban:{uid}",
             style="success" if u["is_banned"] else "danger")],
        [btn("🔑 Thu hồi API Key", f"au_revoke:{uid}"), btn("⏱ Rate limit API", f"au_rate:{uid}")],
        [btn("🧾 Đơn hàng", f"au_orders:{uid}"), btn("💳 Giao dịch", f"au_tx:{uid}")],
        [BACK()],
    ])


@router.callback_query(F.data == "a:users")
async def cb_users(cb: CallbackQuery, state: FSMContext):
    await ask(cb.message, state, "search_user", "🔎 Gửi <b>Telegram ID</b> hoặc <b>@username</b> cần tra cứu:")
    await cb.answer()


@router.callback_query(F.data.startswith("au:"))
async def cb_user_card(cb: CallbackQuery):
    r = await render_user(int(cb.data[3:]))
    if r:
        await ui.edit(cb, *r)
    await cb.answer()


@router.callback_query(F.data.regexp(r"^au_(add|sub):"))
async def cb_user_adj(cb: CallbackQuery, state: FSMContext):
    act, uid = cb.data.split(":")
    sign = 1 if act == "au_add" else -1
    await ask(cb.message, state, "adj_amount", f"💵 Nhập số tiền muốn <b>{'CỘNG' if sign > 0 else 'TRỪ'}</b> "
                                               f"cho user <code>{uid}</code> (vd: 50000, 50k, 1.5tr):",
              uid=int(uid), sign=sign)
    await cb.answer()


@router.callback_query(F.data.startswith("au_role:"))
async def cb_user_role(cb: CallbackQuery, bot: Bot):
    uid = int(cb.data.split(":")[1])
    u = await S.get_user(uid)
    new_role = "member" if u["role"] == "reseller" else "reseller"
    await S.set_role(uid, new_role)
    u = await S.get_user(uid)
    if new_role == "reseller":
        await notify.notify_user(bot, uid, f"👑 Chúc mừng! Bạn đã được nâng cấp lên <b>Đại lý / CTV</b> "
                                           f"với chiết khấu <b>{u['discount_rate']:g}%</b> cho mọi sản phẩm.")
    await ui.edit(cb, *await render_user(uid))
    await cb.answer("✅ Đã cập nhật cấp bậc")


@router.callback_query(F.data.startswith("au_disc:"))
async def cb_user_disc(cb: CallbackQuery, state: FSMContext):
    uid = int(cb.data.split(":")[1])
    await ask(cb.message, state, "disc", f"💯 Nhập % chiết khấu cho user <code>{uid}</code> (0 - 100):", uid=uid)
    await cb.answer()


@router.callback_query(F.data.startswith("au_ban:"))
async def cb_user_ban(cb: CallbackQuery, bot: Bot):
    uid = int(cb.data.split(":")[1])
    if is_admin(uid):
        return await cb.answer("Không thể khóa Admin!", show_alert=True)
    u = await S.get_user(uid)
    new = 0 if u["is_banned"] else 1
    await db.execute("UPDATE users SET is_banned=? WHERE user_id=?", (new, uid))
    await ui.edit(cb, *await render_user(uid))
    await cb.answer("🔒 Đã khóa" if new else "🔓 Đã mở khóa")


@router.callback_query(F.data.startswith("au_revoke:"))
async def cb_user_revoke(cb: CallbackQuery):
    uid = int(cb.data.split(":")[1])
    await db.execute("UPDATE users SET api_key=NULL WHERE user_id=?", (uid,))
    await ui.edit(cb, *await render_user(uid))
    await cb.answer("✅ Đã thu hồi API Key")


@router.callback_query(F.data.startswith("au_rate:"))
async def cb_user_rate(cb: CallbackQuery, state: FSMContext):
    uid = int(cb.data.split(":")[1])
    await ask(cb.message, state, "rate", f"⏱ Nhập giới hạn request/phút cho user <code>{uid}</code>:", uid=uid)
    await cb.answer()


@router.callback_query(F.data.startswith("au_orders:"))
async def cb_user_orders(cb: CallbackQuery):
    uid = int(cb.data.split(":")[1])
    rows = await db.fetchall("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 20", (uid,))
    text = f"🧾 <b>20 ĐƠN GẦN NHẤT CỦA</b> <code>{uid}</code>\n\n" + ("\n".join(
        f"<code>{o['order_id']}</code> | {esc(o['product_name'][:30])} x{o['quantity']} | "
        f"{S.fmt_money(o['total_price'])} | {o['status']} | {o['created_at'][5:16]}" for o in rows) or "Chưa có đơn.")
    await ui.edit(cb, text, kb([[BACK(f"au:{uid}")]]))
    await cb.answer()


@router.callback_query(F.data.startswith("au_tx:"))
async def cb_user_tx(cb: CallbackQuery):
    uid = int(cb.data.split(":")[1])
    rows = await db.fetchall("SELECT * FROM transactions WHERE user_id=? ORDER BY trans_id DESC LIMIT 25", (uid,))
    text = f"💳 <b>25 GIAO DỊCH GẦN NHẤT CỦA</b> <code>{uid}</code>\n\n" + ("\n".join(
        f"{r['created_at'][5:16]} | <b>{'+' if r['amount'] > 0 else ''}{S.fmt_money(r['amount'])}</b> | "
        f"{r['type']} | {esc(r['description'][:40])}" for r in rows) or "Chưa có giao dịch.")
    await ui.edit(cb, text, kb([[BACK(f"au:{uid}")]]))
    await cb.answer()


@router.callback_query(F.data == "a:apiusers")
async def cb_api_users(cb: CallbackQuery):
    rows = await db.fetchall("SELECT * FROM users WHERE api_key IS NOT NULL ORDER BY total_spent DESC LIMIT 50")
    api_orders = await db.fetchval("SELECT COUNT(*) FROM orders WHERE source='api'", default=0)
    text = f"🔌 <b>USER ĐANG ĐẤU API</b> ({len(rows)})\n🧾 Tổng đơn qua API: {api_orders}\n\nBấm vào user để quản lý:"
    buttons = [[btn(f"{('@' + u['username']) if u['username'] else u['user_id']} | ⏱{u['api_rate_limit']}/p | "
                    f"{S.fmt_k(u['total_spent'])}", f"au:{u['user_id']}", style=None)] for u in rows]
    buttons.append([BACK()])
    await ui.edit(cb, text, kb(buttons))
    await cb.answer()


# ======================================================================
# CATEGORIES & PRODUCTS
# ======================================================================
async def render_cats():
    cats = await S.list_categories()
    rows, row = [], []
    for c in cats:
        row.append(btn(f"{'' if c['is_active'] else '⛔ '}{c['name']} ({c['n_products']})", f"ac:{c['id']}",
                       icon=c["custom_emoji_id"], emoji=c["emoji"], style=None if c["is_active"] else "danger"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([btn("➕ Thêm danh mục", "a:addcat", style="success")])
    rows.append([BACK()])
    return ("📂 <b>QUẢN LÝ DANH MỤC & SẢN PHẨM</b>\n\nChọn danh mục để sửa / thêm sản phẩm / nhập kho.\n"
            "💡 Gán icon Premium hàng loạt: lệnh /icons"), kb(rows)


async def render_cat(cid: int):
    c = await S.get_category(cid)
    if not c:
        return None
    prods = await S.list_products(cid, only_active=False)
    text = (f"📂 <b>DANH MỤC #{cid}</b>: {ui.ce(c['custom_emoji_id'], c['emoji'] or '📁')} <b>{esc(c['name'])}</b>\n\n"
            f"😀 Emoji thường: {c['emoji'] or '-'}\n💎 Icon Premium ID: <code>{c['custom_emoji_id'] or '-'}</code>\n"
            f"🔢 Vị trí: {c['position']}\n🚦 Trạng thái: {'✅ Hiển thị' if c['is_active'] else '⛔ Tạm ngưng'}\n"
            f"📦 Số sản phẩm: {len(prods)}")
    rows = []
    for p in prods:
        stock = "∞" if p["is_infinite_stock"] else p["stock"]
        rows.append([btn(f"{'' if p['is_active'] else '⛔ '}{p['name']} | {S.fmt_k(p['price'])} | 📦 {stock}",
                         f"ap:{p['id']}", style=None)])
    rows += [
        [btn("➕ Thêm sản phẩm", f"ac_addp:{cid}", style="success")],
        [btn("✏️ Đổi tên", f"ac_name:{cid}"), btn("💎 Icon Premium", f"ac_icon:{cid}")],
        [btn("😀 Emoji thường", f"ac_emoji:{cid}"), btn("🔢 Vị trí", f"ac_pos:{cid}")],
        [btn("⛔ Tạm ngưng" if c["is_active"] else "✅ Bật hiển thị", f"ac_toggle:{cid}"),
         btn("🗑 Xóa danh mục", f"ac_del:{cid}", style="danger")],
        [BACK("a:cats")],
    ]
    return text, kb(rows)


async def render_prod(pid: int):
    p = await S.get_product(pid)
    if not p:
        return None
    icon, emoji = ui.item_icon(p)
    stock = "∞ (vô hạn)" if p["is_infinite_stock"] else p["stock"]
    text = (f"📦 <b>SẢN PHẨM #{pid}</b>\n{ui.ce(icon, emoji or '📦')} <b>{esc(p['name'])}</b>\n\n"
            f"📂 Danh mục: {esc(p['cat_name'])}\n💰 Giá bán: <b>{S.fmt_money(p['price'])}</b>\n"
            f"💵 Giá vốn: {S.fmt_money(p['cost_price'])}\n📦 Tồn kho: <b>{stock}</b> | ✅ Đã bán: {p['sold']}\n"
            f"🛡 Bảo hành: {esc(p['warranty_info'] or '-')}\n📝 Mô tả: {esc(p['description'] or '-')}\n"
            f"💎 Icon Premium ID: <code>{p['custom_emoji_id'] or '(dùng icon danh mục)'}</code>\n"
            f"🚦 Trạng thái: {'✅ Đang bán' if p['is_active'] else '⛔ Tạm ẩn'}")
    return text, kb([
        [btn("📥 Nhập kho", f"ap_imp:{pid}", style="success"), btn("📣 Báo có hàng mới", f"ap_notif:{pid}", style="success"), btn("📤 Xuất kho", f"ap_exp:{pid}")],
        [btn("✏️ Tên", f"ap_name:{pid}"), btn("💰 Giá bán", f"ap_price:{pid}"), btn("💵 Giá vốn", f"ap_cost:{pid}")],
        [btn("💎 Icon Premium", f"ap_icon:{pid}"), btn("😀 Emoji", f"ap_emoji:{pid}")],
        [btn("🛡 Bảo hành", f"ap_warr:{pid}"), btn("📝 Mô tả", f"ap_desc:{pid}")],
        [btn(f"{'✅' if p['is_infinite_stock'] else '⬜'} Kho vô hạn ∞", f"ap_inf:{pid}"),
         btn("⛔ Ẩn" if p["is_active"] else "✅ Hiện", f"ap_toggle:{pid}")],
        [btn("🧹 Xóa kho tồn", f"ap_clr:{pid}", style="danger"), btn("🗑 Xóa SP", f"ap_del:{pid}", style="danger")],
        [BACK(f"ac:{p['category_id']}")],
    ])


@router.callback_query(F.data == "a:cats")
async def cb_cats(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await ui.edit(cb, *await render_cats())
    await cb.answer()


@router.callback_query(F.data == "a:addcat")
async def cb_addcat(cb: CallbackQuery, state: FSMContext):
    await ask(cb.message, state, "cat_add", "➕ Gửi <b>tên danh mục</b> mới.\n"
                                            "💡 Có thể gửi kèm emoji Premium ở đầu để gán icon luôn (vd: 💎 NETFLIX).")
    await cb.answer()


@router.callback_query(F.data.startswith("ac:"))
async def cb_cat(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    r = await render_cat(int(cb.data[3:]))
    if r:
        await ui.edit(cb, *r)
    await cb.answer()


CAT_PROMPTS = {
    "ac_name": ("cat_name", "✏️ Gửi tên mới cho danh mục:"),
    "ac_icon": ("cat_icon", "💎 Gửi <b>1 emoji Premium</b> (custom emoji) làm icon cho danh mục.\n"
                            "Hoặc gửi ID số. Gửi <code>0</code> để xóa icon."),
    "ac_emoji": ("cat_emoji", "😀 Gửi emoji thường (hiển thị khi chưa có icon Premium):"),
    "ac_pos": ("cat_pos", "🔢 Gửi số vị trí (số nhỏ hiển thị trước):"),
    "ac_addp": ("prod_add_name", "➕ Gửi <b>tên sản phẩm</b> mới:"),
}


@router.callback_query(F.data.regexp(r"^ac_(name|icon|emoji|pos|addp):"))
async def cb_cat_edit(cb: CallbackQuery, state: FSMContext):
    key, cid = cb.data.split(":")
    action, prompt = CAT_PROMPTS[key]
    await ask(cb.message, state, action, prompt, cid=int(cid))
    await cb.answer()


@router.callback_query(F.data.startswith("ac_toggle:"))
async def cb_cat_toggle(cb: CallbackQuery):
    cid = int(cb.data.split(":")[1])
    await db.execute("UPDATE categories SET is_active = 1 - is_active WHERE id=?", (cid,))
    await ui.edit(cb, *await render_cat(cid))
    await cb.answer("✅ Đã cập nhật")


@router.callback_query(F.data.startswith("ac_del:"))
async def cb_cat_del(cb: CallbackQuery):
    cid = int(cb.data.split(":")[1])
    await ui.edit(cb, "⚠️ Xóa danh mục sẽ xóa <b>toàn bộ sản phẩm và kho</b> bên trong. Chắc chắn?",
                  kb([[btn("🗑 Xóa vĩnh viễn", f"ac_del2:{cid}", style="danger"), BACK(f"ac:{cid}")]]))
    await cb.answer()


@router.callback_query(F.data.startswith("ac_del2:"))
async def cb_cat_del2(cb: CallbackQuery):
    cid = int(cb.data.split(":")[1])
    await db.execute("DELETE FROM categories WHERE id=?", (cid,))
    await ui.edit(cb, *await render_cats())
    await cb.answer("🗑 Đã xóa danh mục")


@router.callback_query(F.data.startswith("ap:"))
async def cb_prod(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    r = await render_prod(int(cb.data[3:]))
    if r:
        await ui.edit(cb, *r)
    await cb.answer()


PROD_PROMPTS = {
    "ap_name": ("prod_name", "✏️ Gửi tên mới cho sản phẩm:"),
    "ap_price": ("prod_price", "💰 Gửi giá bán mới (vd: 150000 hoặc 150k):"),
    "ap_cost": ("prod_cost", "💵 Gửi giá vốn (để tính lợi nhuận):"),
    "ap_icon": ("prod_icon", "💎 Gửi <b>1 emoji Premium</b> làm icon sản phẩm.\nHoặc gửi ID số. "
                             "Gửi <code>0</code> để dùng lại icon của danh mục."),
    "ap_emoji": ("prod_emoji", "😀 Gửi emoji thường cho sản phẩm (gửi 0 để xóa):"),
    "ap_warr": ("prod_warr", "🛡 Gửi thông tin bảo hành (vd: Bảo hành full 30 ngày):"),
    "ap_desc": ("prod_desc", "📝 Gửi mô tả sản phẩm (gửi 0 để xóa):"),
    "ap_imp": ("import", "📥 <b>NHẬP KHO & TỰ ĐỘNG THÔNG BÁO HÀNG MỚI</b>\n\nGửi danh sách tài khoản (mỗi dòng 1 acc, định dạng "
                         "<code>email|pass|2fa|token</code>) hoặc upload file <b>.txt</b>.\nBot tự lọc trùng lặp và bắn thông báo có hàng mới tới toàn bộ người dùng."),
    "ap_notif": ("prod_notif", "📣 Nhập số lượng <b>Thêm:</b> muốn hiển thị trên thông báo có hàng mới (vd: <code>25</code>):"),
}


@router.callback_query(F.data.regexp(r"^ap_(name|price|cost|icon|emoji|warr|desc|imp|notif):"))
async def cb_prod_edit(cb: CallbackQuery, state: FSMContext):
    key, pid = cb.data.split(":")
    action, prompt = PROD_PROMPTS[key]
    await ask(cb.message, state, action, prompt, pid=int(pid))
    await cb.answer()


@router.callback_query(F.data.regexp(r"^ap_(inf|toggle):"))
async def cb_prod_toggle(cb: CallbackQuery):
    key, pid = cb.data.split(":")
    col = "is_infinite_stock" if key == "ap_inf" else "is_active"
    await db.execute(f"UPDATE products SET {col} = 1 - {col} WHERE id=?", (int(pid),))
    await ui.edit(cb, *await render_prod(int(pid)))
    await cb.answer("✅ Đã cập nhật")


@router.callback_query(F.data.startswith("ap_exp:"))
async def cb_prod_export(cb: CallbackQuery):
    pid = int(cb.data.split(":")[1])
    rows = await db.fetchall("SELECT account_data FROM stocks WHERE product_id=? AND is_sold=0 ORDER BY id", (pid,))
    if not rows:
        return await cb.answer("Kho trống!", show_alert=True)
    data = "\n".join(r["account_data"] for r in rows).encode("utf-8")
    await cb.message.answer_document(BufferedInputFile(data, filename=f"stock_product_{pid}.txt"),
                                     caption=f"📤 Kho tồn sản phẩm #{pid}: {len(rows)} acc")
    await cb.answer()


@router.callback_query(F.data.startswith("ap_clr:"))
async def cb_prod_clear(cb: CallbackQuery):
    pid = int(cb.data.split(":")[1])
    await ui.edit(cb, "⚠️ Xóa <b>toàn bộ acc CHƯA BÁN</b> trong kho sản phẩm này?",
                  kb([[btn("🧹 Xóa kho", f"ap_clr2:{pid}", style="danger"), BACK(f"ap:{pid}")]]))
    await cb.answer()


@router.callback_query(F.data.startswith("ap_clr2:"))
async def cb_prod_clear2(cb: CallbackQuery):
    pid = int(cb.data.split(":")[1])
    n = await db.execute("DELETE FROM stocks WHERE product_id=? AND is_sold=0", (pid,))
    await ui.edit(cb, *await render_prod(pid))
    await cb.answer(f"🧹 Đã xóa {n} acc", show_alert=True)


@router.callback_query(F.data.startswith("ap_del:"))
async def cb_prod_del(cb: CallbackQuery):
    pid = int(cb.data.split(":")[1])
    await ui.edit(cb, "⚠️ Xóa sản phẩm và toàn bộ kho? (Lịch sử đơn vẫn được giữ)",
                  kb([[btn("🗑 Xóa vĩnh viễn", f"ap_del2:{pid}", style="danger"), BACK(f"ap:{pid}")]]))
    await cb.answer()


@router.callback_query(F.data.startswith("ap_del2:"))
async def cb_prod_del2(cb: CallbackQuery):
    pid = int(cb.data.split(":")[1])
    p = await S.get_product(pid)
    await db.execute("DELETE FROM products WHERE id=?", (pid,))
    await ui.edit(cb, *(await render_cat(p["category_id"]) if p else await render_cats()))
    await cb.answer("🗑 Đã xóa sản phẩm")


# ======================================================================
# ORDERS
# ======================================================================
async def render_order_admin(o):
    u = await S.get_user(o["user_id"])
    who = f"@{esc(u['username'])}" if u and u["username"] else esc((u or {}).get("full_name") or "")
    acc = o["accounts_delivered"] or "(chưa có / đơn dịch vụ)"
    text = (f"🧾 <b>ĐƠN HÀNG</b> <code>{o['order_id']}</code>\n\n👤 Khách: {who} (<code>{o['user_id']}</code>)\n"
            f"📦 {esc(o['product_name'])} x{o['quantity']}\n💵 Đơn giá: {S.fmt_money(o['unit_price'])}\n"
            f"💰 Tổng: <b>{S.fmt_money(o['total_price'])}</b> | Vốn: {S.fmt_money(o['cost_total'])}\n"
            f"📌 Trạng thái: <b>{o['status']}</b> | Nguồn: {o['source']}\n🕒 {o['created_at']}\n\n"
            f"<b>Nội dung đã giao:</b>\n<pre>{esc(acc[:2500])}</pre>")
    rows = []
    if len(acc) > 2500:
        rows.append([btn("📥 Tải file đầy đủ", f"aod:{o['order_id']}")])
    if o["status"] == "processing":
        rows.append([btn("📤 Gửi nội dung cho khách", f"od_send:{o['order_id']}")])
    if o["status"] != "refunded":
        rows.append([btn("💸 Hoàn tiền đơn", f"od_ref:{o['order_id']}", style="danger")])
    rows.append([btn("👤 Xem khách", f"au:{o['user_id']}"), BACK()])
    return text, kb(rows)


@router.callback_query(F.data == "a:order")
async def cb_order(cb: CallbackQuery, state: FSMContext):
    await ask(cb.message, state, "order_lookup", "🧾 Gửi <b>mã đơn hàng</b> cần tra cứu:")
    await cb.answer()


@router.callback_query(F.data.startswith("aod:"))
async def cb_order_file(cb: CallbackQuery):
    o = await S.get_order(cb.data[4:])
    if o and o["accounts_delivered"]:
        await cb.message.answer_document(
            BufferedInputFile(o["accounts_delivered"].encode("utf-8"), filename=f"{o['order_id']}.txt"))
    await cb.answer()


@router.callback_query(F.data.startswith("od_send:"))
async def cb_order_send(cb: CallbackQuery, state: FSMContext):
    oid = cb.data.split(":")[1]
    await ask(cb.message, state, "deliver", f"📤 Gửi nội dung (tài khoản / thông tin dịch vụ) cho đơn <code>{oid}</code>:",
              oid=oid)
    await cb.answer()


@router.callback_query(F.data.startswith("od_ref:"))
async def cb_order_refund(cb: CallbackQuery, bot: Bot):
    oid = cb.data.split(":")[1]
    r = await S.refund_order(oid, f"Hoàn tiền đơn {oid}")
    if not r:
        return await cb.answer("Đơn không tồn tại hoặc đã hoàn tiền!", show_alert=True)
    uid, amount, bal = r
    await notify.notify_user(bot, uid, f"💸 Đơn <code>{oid}</code> đã được <b>hoàn {S.fmt_money(amount)}</b> vào ví.\n"
                                       f"👛 Số dư: <b>{S.fmt_money(bal)}</b>")
    await append_status(cb, f"💸 Đã hoàn {S.fmt_money(amount)}")
    await cb.answer("✅ Đã hoàn tiền")


async def append_status(cb: CallbackQuery, line: str):
    try:
        await cb.message.edit_text((cb.message.html_text or "") + f"\n\n<b>{line}</b>", reply_markup=None)
    except TelegramBadRequest:
        await cb.message.answer(line)


# ======================================================================
# WARRANTY TICKETS
# ======================================================================
@router.callback_query(F.data == "a:tickets")
async def cb_tickets(cb: CallbackQuery):
    rows = await db.fetchall("SELECT * FROM tickets WHERE status='pending' ORDER BY id LIMIT 30")
    buttons = [[btn(f"#{tk['id']} | {tk['order_id']} | {tk['user_id']}", f"tk:{tk['id']}", style=None)] for tk in rows]
    buttons.append([BACK()])
    await ui.edit(cb, f"🛡 <b>PHIẾU BẢO HÀNH CHỜ XỬ LÝ</b> ({len(rows)})", kb(buttons))
    await cb.answer()


@router.callback_query(F.data.startswith("tk:"))
async def cb_ticket(cb: CallbackQuery):
    tk = await db.fetchone("SELECT * FROM tickets WHERE id=?", (int(cb.data[3:]),))
    if not tk:
        return await cb.answer()
    o = await S.get_order(tk["order_id"])
    text = (f"🛡 <b>PHIẾU #{tk['id']}</b> ({tk['status']})\n👤 User: <code>{tk['user_id']}</code>\n"
            f"🧾 Đơn: <code>{tk['order_id']}</code>\n📦 {esc(o['product_name']) if o else '-'}\n"
            f"💰 {S.fmt_money(o['total_price']) if o else '-'}\n📝 Lý do: {esc(tk['reason'])}\n🕒 {tk['created_at']}\n\n"
            f"<b>Acc đã giao:</b>\n<pre>{esc((o['accounts_delivered'] if o else '')[:1500]) or '-'}</pre>")
    markup = notify.ticket_kb(tk["id"]) if tk["status"] == "pending" else None
    await cb.message.answer(text, reply_markup=markup)
    await cb.answer()


async def _get_pending_ticket(cb: CallbackQuery):
    tk = await db.fetchone("SELECT * FROM tickets WHERE id=?", (int(cb.data.split(":")[1]),))
    if not tk or tk["status"] != "pending":
        await cb.answer("Phiếu đã được xử lý!", show_alert=True)
        return None
    return tk


async def _close_ticket(tid: int, status: str, note: str):
    await db.execute("UPDATE tickets SET status=?, admin_note=?, resolved_at=datetime('now','localtime') WHERE id=?",
                     (status, note, tid))


@router.callback_query(F.data.startswith("wr_ok:"))
async def cb_wr_replace(cb: CallbackQuery, bot: Bot):
    tk = await _get_pending_ticket(cb)
    if not tk:
        return
    acc = await S.replace_one_account(tk["order_id"])
    if not acc:
        return await cb.answer("❌ Kho sản phẩm này đã hết hàng, không thể đổi!", show_alert=True)
    await _close_ticket(tk["id"], "replaced", "Đổi acc mới")
    await notify.notify_user(bot, tk["user_id"], f"✅ <b>Phiếu bảo hành #{tk['id']} đã được duyệt!</b>\n"
                                                 f"🧾 Đơn: <code>{tk['order_id']}</code>\n\n🎁 Tài khoản mới:\n<code>{esc(acc)}</code>")
    await append_status(cb, "✅ Đã đổi acc mới cho khách")
    await cb.answer("✅ Đã gửi acc mới")


@router.callback_query(F.data.startswith("wr_ref:"))
async def cb_wr_refund(cb: CallbackQuery, bot: Bot):
    tk = await _get_pending_ticket(cb)
    if not tk:
        return
    r = await S.refund_order(tk["order_id"], f"Hoàn tiền bảo hành phiếu #{tk['id']}")
    if not r:
        return await cb.answer("Đơn đã được hoàn tiền trước đó!", show_alert=True)
    uid, amount, bal = r
    await _close_ticket(tk["id"], "refunded", f"Hoàn {amount}")
    await notify.notify_user(bot, uid, f"💸 <b>Phiếu bảo hành #{tk['id']}</b>: đã hoàn <b>{S.fmt_money(amount)}</b> "
                                       f"vào ví.\n👛 Số dư: <b>{S.fmt_money(bal)}</b>")
    await append_status(cb, f"💸 Đã hoàn {S.fmt_money(amount)} vào ví khách")
    await cb.answer("✅ Đã hoàn tiền")


@router.callback_query(F.data.startswith("wr_no:"))
async def cb_wr_reject(cb: CallbackQuery, state: FSMContext):
    tk = await _get_pending_ticket(cb)
    if not tk:
        return
    await ask(cb.message, state, "reject_reason", f"❌ Nhập lý do từ chối phiếu <b>#{tk['id']}</b>:", tid=tk["id"])
    await cb.answer()


# ======================================================================
# BANK & AUTO-BANK
# ======================================================================
def _mask(s: str) -> str:
    if not s:
        return "❌ Chưa gắn"
    return f"✅ Đã gắn (<code>{esc(s[:6])}...{esc(s[-4:])}</code>)" if len(s) > 12 else f"✅ <code>{esc(s)}</code>"


async def render_bank():
    cfg = await bank_auto.get_bank_config()
    n_dep = await db.fetchval("SELECT COUNT(*) FROM deposits WHERE status='pending'", default=0)
    n_qr = await db.fetchval("SELECT COUNT(*) FROM payment_intents WHERE kind='order' AND status='pending'", default=0)
    total_pending = n_dep + n_qr
    text = (
        "🏦 <b>CẤU HÌNH THANH TOÁN MOMO & DUYỆT ĐƠN</b>\n\n"
        f"🏛 Ví / Ngân hàng: <b>{esc(cfg['bank_id'])}</b> (Ảnh QR MoMo chính chủ)\n"
        f"💳 Số TK / Mã QR: <code>{esc(cfg['account'] or '(Chưa cài)')}</code>\n"
        f"👤 Chủ tài khoản: <b>{esc(cfg['account_name'] or '(Chưa cài)')}</b>\n"
        f"📝 Cú pháp chuyển khoản: <code>{esc(cfg['prefix'])} [UID / Mã Đơn]</code>\n"
        f"💵 Nạp tối thiểu: <b>{S.fmt_money(cfg['min_deposit'])}</b>\n\n"
        "━━━ <b>CHẾ ĐỘ DUYỆT ĐƠN HIỆN TẠI</b> ━━━\n"
        "✅ <b>Duyệt thủ công 1-Click bởi Admin:</b>\n"
        "• Khi khách mua hàng bằng QR hoặc nạp Ví, Bot gửi đúng ảnh QR MoMo của bạn kèm số tiền & nội dung CK.\n"
        "• Khi khách bấm <b>Tôi đã thanh toán</b>, Bot gửi thông báo kèm nút <b>[✅ Duyệt & Giao sản phẩm ngay]</b> về thẳng Telegram của bạn!\n"
        "• Chỉ khi bạn bấm <b>Duyệt</b> thì Bot mới xuất kho giao tài khoản cho khách."
    )
    rows = [
        [btn(f"⏳ Đơn QR & Nạp Ví chờ duyệt ({total_pending})", "a:pdep", style="success")],
        [btn("🖼 Xem thử ảnh QR MoMo gửi cho khách", "ab:testqr")],
        [btn("🏛 Chọn Ngân hàng / MoMo", "ab:pick_bank"), btn("💳 Đổi Số TK/SĐT", "ab:acc"), btn("👤 Đổi Chủ TK", "ab:name")],
        [btn("📝 Đổi Cú pháp nạp", "ab:prefix"), btn("💵 Đổi Min nạp", "ab:min")],
        [btn("⚡ Cài nhanh (NH|STK|TÊN)", "ab:quick"), btn("🧪 Giả lập duyệt đơn", "ab:sim")],
        [BACK()],
    ]
    return text, kb(rows)


@router.callback_query(F.data == "a:bank")
async def cb_bank_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await ui.edit(cb, *await render_bank())
    await cb.answer()


@router.callback_query(F.data == "ab:toggle_auto")
async def cb_bank_toggle_auto(cb: CallbackQuery):
    cfg = await bank_auto.get_bank_config()
    new_val = "0" if cfg["auto_approve"] else "1"
    await S.set_setting("bank_auto_approve", new_val)
    await ui.edit(cb, *await render_bank())
    await cb.answer("⚡ Đã BẬT tự động duyệt!" if new_val == "1" else "Đã TẮT tự động duyệt (chuyển sang API / duyệt 1-click)")


@router.callback_query(F.data == "ab:pick_bank")
async def cb_bank_pick(cb: CallbackQuery):
    rows, row = [], []
    for code, label in bank_auto.VIETQR_BANKS:
        row.append(btn(f"{code} ({label})", f"ab_setb:{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([btn("✏️ Tự nhập mã ngân hàng khác", "ab:bank_custom")])
    rows.append([BACK("a:bank")])
    await ui.edit(cb, "🏛 <b>CHỌN NGÂN HÀNG CỦA BẠN (VIETQR):</b>", kb(rows))
    await cb.answer()


@router.callback_query(F.data.startswith("ab_setb:"))
async def cb_bank_set_code(cb: CallbackQuery):
    code = cb.data.split(":")[1]
    await S.set_setting("bank_id", code)
    await ui.edit(cb, *await render_bank())
    await cb.answer(f"✅ Đã chọn ngân hàng {code}")


BANK_PROMPTS = {
    "ab:bank_custom": ("bank_id", "🏛 Nhập mã ngân hàng VietQR (vd: <code>MB</code>, <code>VCB</code>, <code>TCB</code>, <code>ACB</code>, <code>BIDV</code>):"),
    "ab:acc": ("bank_account", "💳 Nhập <b>Số tài khoản</b> ngân hàng của bạn:"),
    "ab:name": ("bank_account_name", "👤 Nhập <b>Tên chủ tài khoản</b> (viết hoa không dấu, vd: <code>NGUYEN VAN A</code>):"),
    "ab:prefix": ("deposit_prefix", "📝 Nhập <b>Cú pháp nạp tiền</b> (mặc định: <code>NAP</code>):"),
    "ab:min": ("min_deposit", "💵 Nhập <b>Số tiền nạp tối thiểu</b> (vd: <code>10000</code> hoặc <code>10k</code>):"),
    "ab:quick": ("bank_quick", "⚡ <b>CÀI NHANH NGÂN HÀNG</b>\n\nGửi 1 dòng theo định dạng:\n<code>MÃ_NH|SỐ_TK|TÊN_CHỦ_TK</code>\n\nVí dụ:\n<code>MB|0123456789|NGUYEN VAN A</code>"),
    "ab:sepay": ("sepay_token", "🔌 Gửi <b>SePay API Token</b> (lấy tại my.sepay.vn → Cấu hình Công ty → API Access).\nBot sẽ tự động quét lịch sử giao dịch mỗi 12 giây.\nGửi <code>0</code> để xóa."),
    "ab:casso": ("casso_key", "🔌 Gửi <b>Casso API Key</b> (lấy tại Casso.vn → Thiết lập → API Keys).\nBot sẽ tự động quét giao dịch mỗi 12 giây.\nGửi <code>0</code> để xóa."),
    "ab:web2m": ("web2m_url", "🌐 Gửi <b>Link API Lịch sử giao dịch (Web2M / API riêng)</b> trả về JSON danh sách giao dịch.\nVí dụ: <code>https://api.web2m.com/historyapimbv3/PASS/STK/TOKEN</code>\nGửi <code>0</code> để xóa."),
    "ab:imap": ("imap_quick", "📧 <b>GẮN GMAIL ĐỌC THÔNG BÁO MOMO / NGÂN HÀNG (MIỄN PHÍ 100%)</b>\n\n"
                              "Khi có người chuyển khoản vào MoMo hoặc Ngân hàng (MSB, VCB, Cake...), MoMo/Bank sẽ gửi email thông báo về Gmail của bạn. Bot sẽ tự động đọc email mỗi 8 giây và duyệt đơn ngay lập tức!\n\n"
                              "📌 <b>Cách lấy Mật khẩu ứng dụng Gmail (1 phút):</b>\n"
                              "1. Bật Xác minh 2 bước tại <code>myaccount.google.com/security</code>\n"
                              "2. Vào <code>myaccount.google.com/apppasswords</code> → Tạo mật khẩu ứng dụng (16 ký tự).\n"
                              "3. Gửi cho Bot theo định dạng:\n<code>email_cua_ban@gmail.com|mat_khau_16_ky_tu</code>\n\n"
                              "Gửi <code>0</code> để xóa."),
    "ab:sim": ("bank_sim", "🧪 <b>GIẢ LẬP NỔ TIỀN BANK / ĐƠN QR</b>\n\nGửi theo định dạng:\n• Nạp Ví: <code>UID|SỐ_TIỀN</code> (vd: <code>8754685711|50000</code>)\n• Đơn QR trực tiếp: <code>MÃ_DH|SỐ_TIỀN</code> (vd: <code>DH123456|150000</code>)"),
}


@router.callback_query(F.data.in_(BANK_PROMPTS.keys()))
async def cb_bank_prompt(cb: CallbackQuery, state: FSMContext):
    action, prompt = BANK_PROMPTS[cb.data]
    await ask(cb.message, state, action, prompt)
    await cb.answer()


@router.callback_query(F.data == "ab:scan")
async def cb_bank_scan(cb: CallbackQuery, bot: Bot):
    cfg = await bank_auto.get_bank_config()
    if not (cfg["sepay_token"] or cfg["casso_key"] or cfg["web2m_url"] or (cfg.get("imap_email") and cfg.get("imap_pass"))):
        return await cb.answer("⚠️ Chưa gắn Gmail IMAP / SePay / Casso / Web2M!", show_alert=True)
    n = await bank_auto.check_bank_transactions_once(bot)
    await cb.answer(f"✅ Đã quét xong! Có {n} giao dịch mới được cộng tiền/giao đơn.", show_alert=True)


@router.callback_query(F.data == "ab:testqr")
async def cb_bank_testqr(cb: CallbackQuery):
    cfg = await bank_auto.get_bank_config()
    content = f"{cfg['prefix']} {cb.from_user.id}"
    amount = max(10000, cfg["min_deposit"])
    caption = f"🖼 <b>XEM THỬ MÃ QR HIỂN THỊ CHO KHÁCH</b>\n\n📝 Nội dung CK: <code>{esc(content)}</code>"
    await cb.answer("⏳ Đang tải ảnh QR...")
    await bank_auto.send_vietqr_photo(cb.message, cfg, amount, content, caption)


@router.callback_query(F.data.startswith("adm_qrok:"))
async def cb_adm_qrok(cb: CallbackQuery, bot: Bot):
    pay_code = cb.data.split(":")[1]
    intent = await db.fetchone("SELECT * FROM payment_intents WHERE pay_code=?", (pay_code,))
    if not intent or intent["status"] != "pending":
        return await cb.answer("Đơn này đã được xử lý!", show_alert=True)
    ok, res_id = await bank_auto.deliver_direct_order(bot, intent, f"ADM_{pay_code}", "Admin-Approve")
    if ok:
        await append_status(cb, f"✅ Đã duyệt & giao sản phẩm (Mã đơn: {res_id})")
        await cb.answer("✅ Đã giao sản phẩm cho khách!")
    else:
        await cb.answer("Đơn đã được xử lý trước đó!", show_alert=True)


@router.callback_query(F.data.startswith("adm_qrno:"))
async def cb_adm_qrno(cb: CallbackQuery, bot: Bot):
    pay_code = cb.data.split(":")[1]
    intent = await db.fetchone("SELECT * FROM payment_intents WHERE pay_code=?", (pay_code,))
    if not intent or intent["status"] != "pending":
        return await cb.answer("Đơn này đã được xử lý!", show_alert=True)
    await db.execute("UPDATE payment_intents SET status='rejected' WHERE pay_code=?", (pay_code,))
    await notify.notify_user(bot, intent["user_id"], f"❌ Yêu cầu thanh toán QR <code>{pay_code}</code> đã bị từ chối.")
    await append_status(cb, "❌ Đã từ chối")
    await cb.answer("Đã từ chối")


# ======================================================================
# CRYPTO & BANK PENDING
# ======================================================================
@router.callback_query(F.data == "a:pdep")
async def cb_pending_deps(cb: CallbackQuery):
    qr_rows = await db.fetchall("SELECT * FROM payment_intents WHERE kind='order' AND status='pending' ORDER BY id DESC LIMIT 15")
    dep_rows = await db.fetchall("SELECT * FROM deposits WHERE status='pending' ORDER BY id DESC LIMIT 15")
    if not qr_rows and not dep_rows:
        return await cb.answer("Không có đơn QR hay yêu cầu nạp nào đang chờ duyệt.", show_alert=True)
    for intent in qr_rows:
        p = await S.get_product(intent["product_id"])
        await cb.message.answer(
            f"🔔 <b>ĐƠN MUA QR CHỜ DUYỆT</b> <code>{intent['pay_code']}</code>\n"
            f"👤 Khách: <code>{intent['user_id']}</code>\n"
            f"📦 Sản phẩm: <b>{esc(p['name'] if p else '')}</b> x{intent['quantity']}\n"
            f"💰 Số tiền: <b>{S.fmt_money(intent['amount'])}</b>\n"
            f"📝 Nội dung CK: <code>{esc(intent['content'])}</code>\n"
            f"🕒 {intent['created_at']}",
            reply_markup=kb([
                [btn("✅ Duyệt & Giao sản phẩm ngay", f"adm_qrok:{intent['pay_code']}", style="success")],
                [btn("❌ Từ chối đơn này", f"adm_qrno:{intent['pay_code']}", style="danger")],
            ]),
        )
    for d in dep_rows:
        await cb.message.answer(f"💎 <b>NẠP VÍ CHỜ DUYỆT #{d['id']}</b>\n👤 <code>{d['user_id']}</code>\n🔖 {esc(d['method'])}\n"
                                f"💰 {S.fmt_money(d['amount'])}\n🧾 <code>{esc(d['note'])}</code>\n🕒 {d['created_at']}",
                                reply_markup=notify.crypto_kb(d["id"]))
    await cb.answer()


@router.callback_query(F.data.startswith("cr_ok:"))
async def cb_crypto_ok(cb: CallbackQuery, bot: Bot):
    r = await S.approve_pending_deposit(int(cb.data.split(":")[1]))
    if not r:
        return await cb.answer("Yêu cầu đã được xử lý!", show_alert=True)
    uid, amount, method, bal = r
    u = await S.get_user(uid)
    await notify.notify_user(bot, uid, t(u["language"], "deposit_ok", amount=S.fmt_money(amount),
                                         method=esc(method), balance=S.fmt_money(bal)))
    await append_status(cb, f"✅ Đã duyệt +{S.fmt_money(amount)}")
    await cb.answer("✅ Đã duyệt")


@router.callback_query(F.data.startswith("cr_no:"))
async def cb_crypto_no(cb: CallbackQuery, bot: Bot):
    d = await S.reject_pending_deposit(int(cb.data.split(":")[1]))
    if not d:
        return await cb.answer("Yêu cầu đã được xử lý!", show_alert=True)
    await notify.notify_user(bot, d["user_id"], f"❌ Yêu cầu nạp <b>#{d['id']}</b> ({esc(d['method'])}) đã bị từ chối. "
                                                f"Liên hệ hỗ trợ nếu có nhầm lẫn.")
    await append_status(cb, "❌ Đã từ chối")
    await cb.answer("Đã từ chối")


# ======================================================================
# STATS
# ======================================================================
@router.callback_query(F.data.startswith("st:"))
async def cb_stats(cb: CallbackQuery):
    days = int(cb.data[3:])
    since = f"-{days - 1} days"
    cond = "date(created_at) >= date('now','localtime',?)"
    o = await db.fetchone(f"SELECT COALESCE(SUM(total_price),0) rev, COALESCE(SUM(cost_total),0) cost, COUNT(*) n, "
                          f"COALESCE(SUM(quantity),0) q FROM orders WHERE status!='refunded' AND {cond}", (since,))
    new_users = await db.fetchval(f"SELECT COUNT(*) FROM users WHERE {cond}", (since,), 0)
    dep = await db.fetchval(f"SELECT SUM(amount) FROM transactions WHERE type='deposit' AND {cond}", (since,), 0)
    refunds = await db.fetchval(f"SELECT SUM(amount) FROM transactions WHERE type='refund' AND {cond}", (since,), 0)
    top_dep = await db.fetchall(
        f"SELECT t.user_id, u.username, SUM(t.amount) s FROM transactions t LEFT JOIN users u ON u.user_id=t.user_id "
        f"WHERE t.type='deposit' AND date(t.created_at) >= date('now','localtime',?) GROUP BY t.user_id ORDER BY s DESC LIMIT 5",
        (since,))
    top_prod = await db.fetchall(
        f"SELECT product_name, SUM(quantity) q, SUM(total_price) s FROM orders WHERE status!='refunded' AND {cond} "
        f"GROUP BY product_name ORDER BY s DESC LIMIT 5", (since,))
    total_users = await db.fetchval("SELECT COUNT(*) FROM users", default=0)
    total_bal = await db.fetchval("SELECT SUM(balance) FROM users", default=0)
    label = {1: "HÔM NAY", 7: "7 NGÀY", 30: "30 NGÀY"}.get(days, f"{days} NGÀY")
    text = (f"📊 <b>THỐNG KÊ {label}</b>\n\n💰 Doanh thu: <b>{S.fmt_money(o['rev'])}</b>\n"
            f"📈 Lợi nhuận: <b>{S.fmt_money(o['rev'] - o['cost'])}</b>\n🧾 Số đơn: {o['n']} ({o['q']} sản phẩm)\n"
            f"📥 Tổng nạp: {S.fmt_money(dep)}\n💸 Hoàn tiền: {S.fmt_money(refunds)}\n🆕 Thành viên mới: {new_users}\n\n"
            f"🏆 <b>Top nạp tiền:</b>\n" + ("\n".join(
                f"{i + 1}. {('@' + esc(r['username'])) if r['username'] else r['user_id']} — {S.fmt_money(r['s'])}"
                for i, r in enumerate(top_dep)) or "-") +
            "\n\n🔥 <b>Top sản phẩm:</b>\n" + ("\n".join(
                f"{i + 1}. {esc(r['product_name'][:35])} — {r['q']} sp — {S.fmt_money(r['s'])}"
                for i, r in enumerate(top_prod)) or "-") +
            f"\n\n👥 Tổng user: {total_users} | 👛 Tổng số dư khách: {S.fmt_money(total_bal)}")
    markup = kb([[btn(("• " if days == d else "") + n, f"st:{d}") for d, n in ((1, "Hôm nay"), (7, "7 ngày"), (30, "30 ngày"))],
                 [BACK()]])
    await ui.edit(cb, text, markup)
    await cb.answer()


# ======================================================================
# BROADCAST
# ======================================================================
@router.callback_query(F.data == "a:bc")
async def cb_bc(cb: CallbackQuery, state: FSMContext):
    await ask(cb.message, state, "bc", "📢 <b>BROADCAST</b>\n\nGửi nội dung muốn phát (chữ, ảnh, video, file... "
                                       "hỗ trợ định dạng <b>đậm</b>, <i>nghiêng</i>, link):")
    await cb.answer()


@router.callback_query(F.data.startswith("bc_"))
async def cb_bc_action(cb: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if "bc_msg" not in data:
        return await cb.answer("Hết phiên, hãy soạn lại.", show_alert=True)
    if cb.data == "bc_btn":
        data["bc_btn"] = not data.get("bc_btn", False)
        await state.update_data(bc_btn=data["bc_btn"])
        await cb.message.edit_reply_markup(reply_markup=bc_kb(data["bc_btn"]))
        return await cb.answer()
    await state.clear()
    if cb.data == "bc_cancel":
        await cb.message.edit_text("❌ Đã hủy broadcast.")
        return await cb.answer()
    await cb.message.edit_text("🚀 Đang gửi broadcast...")
    asyncio.create_task(run_broadcast(bot, cb.message, data["bc_chat"], data["bc_msg"], data.get("bc_btn", False)))
    await cb.answer()


def bc_kb(with_btn: bool):
    return kb([[btn(f"{'✅' if with_btn else '⬜'} Gắn nút 🛒 Mua hàng", "bc_btn")],
               [btn("🚀 Gửi ngay", "bc_go", style="success"), btn("❌ Hủy", "bc_cancel", style="danger")]])


async def run_broadcast(bot: Bot, status_msg: Message, from_chat: int, msg_id: int, with_btn: bool):
    users = await db.fetchall("SELECT user_id FROM users WHERE is_banned=0")
    markup = None
    if with_btn:
        markup = kb([[btn("Mua hàng", "u:buy", icon=await ui.menu_icon("buy"), emoji="🛒")]])
    ok = fail = 0
    total = len(users)

    async def send_one(uid, mk):
        await bot.copy_message(uid, from_chat, msg_id, reply_markup=mk)

    for i, u in enumerate(users, 1):
        for attempt in range(3):
            try:
                try:
                    await send_one(u["user_id"], markup)
                except TelegramBadRequest as e:
                    if markup and ui._is_icon_error(e):
                        markup = ui._strip_markup(markup)
                        await send_one(u["user_id"], markup)
                    else:
                        raise
                ok += 1
                break
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except (TelegramForbiddenError, TelegramBadRequest):
                fail += 1
                break
            except Exception as e:  # noqa
                log.warning("broadcast %s: %s", u["user_id"], e)
                fail += 1
                break
        await asyncio.sleep(0.05)  # ~20 msg/s < giới hạn 30 msg/s của Telegram
        if i % 200 == 0:
            try:
                await status_msg.edit_text(f"🚀 Đang gửi... {i}/{total} (✅ {ok} | ❌ {fail})")
            except TelegramBadRequest:
                pass
    await status_msg.edit_text(f"✅ <b>BROADCAST HOÀN TẤT</b>\n\n👥 Tổng: {total}\n✅ Thành công: {ok}\n"
                               f"❌ Thất bại / chặn bot: {fail}")


# ======================================================================
# PREMIUM ICONS
# ======================================================================
async def render_icons():
    rows, row = [], []
    for k in ICON_KEYS:
        icon = await S.get_setting(f"icon_{k}")
        row.append(btn(ICON_LABELS[k], f"ai:{k}", icon=icon, emoji=ICON_EMOJI[k]))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([BACK()])
    text = ("🎨 <b>ICON PREMIUM (CUSTOM EMOJI)</b>\n\n"
            "• Bấm 1 nút bên dưới rồi gửi emoji Premium để đổi icon nút menu.\n"
            "• Icon danh mục / sản phẩm: vào 📂 Sản phẩm & Kho → chọn mục → 💎 Icon Premium.\n"
            "• Gán hàng loạt: gõ /icons rồi gửi nhiều dòng dạng <code>[emoji premium] TÊN</code>.\n"
            "• Lấy ID: gửi bất kỳ emoji Premium nào cho bot, bot sẽ trả về ID.\n\n"
            "⚠️ Icon trên nút chỉ hiển thị khi <b>chủ bot có Telegram Premium</b>.")
    return text, kb(rows)


@router.callback_query(F.data == "a:icons")
async def cb_icons(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await ui.edit(cb, *await render_icons())
    await cb.answer()


@router.callback_query(F.data.startswith("ai:"))
async def cb_icon_set(cb: CallbackQuery, state: FSMContext):
    key = cb.data[3:]
    await ask(cb.message, state, "menu_icon", f"💎 Gửi emoji Premium cho nút <b>{ICON_LABELS[key]}</b> "
                                              f"(hoặc ID số, gửi 0 để xóa):", key=key)
    await cb.answer()


@router.message(Command("icons"))
async def cmd_icons(message: Message, state: FSMContext):
    await ask(message, state, "bulk_icons",
              "🎨 <b>GÁN ICON HÀNG LOẠT</b>\n\nGửi 1 tin nhắn, mỗi dòng gồm <b>1 emoji Premium + tên</b> "
              "danh mục / sản phẩm / nút menu. Ví dụ:\n<code>[🎬] YOUTUBE\n[🤖] CHAT GPT\n[🛒] Mua hàng\n[❌] Hết hàng\n"
              "[🧿] Cập nhật sản phẩm</code>\n\n(thay [..] bằng emoji Premium thật)")


async def bulk_icons(message: Message) -> str:
    text = message.text or message.caption or ""
    ents = [e for e in (message.entities or message.caption_entities or []) if e.type == "custom_emoji"]
    cats = await db.fetchall("SELECT id, name FROM categories")
    prods = await db.fetchall("SELECT id, name FROM products")
    menu_map = {}
    for lang in TEXTS:
        for k, _ in MENU_ITEMS:
            menu_map[norm(TEXTS[lang][f"m_{k}"])] = k
        menu_map[norm(TEXTS[lang]["refresh"])] = "refresh"
    menu_map.update({"HETHANG": "soldout", "SOLDOUT": "soldout", "REFRESH": "refresh"})

    done, miss = [], []
    pos = 0
    for line in text.split("\n"):
        ln = len(line.encode("utf-16-le")) // 2
        line_ents = [e for e in ents if pos <= e.offset < pos + ln]
        pos += ln + 1
        if not line_ents:
            continue
        icon = line_ents[0].custom_emoji_id
        lb = line.encode("utf-16-le")
        for e in sorted(line_ents, key=lambda e: e.offset, reverse=True):
            s = (e.offset - (pos - ln - 1)) * 2
            lb = lb[:s] + lb[s + e.length * 2:]
        raw = lb.decode("utf-16-le", errors="ignore").strip()
        n = norm(raw.replace("...", ""))
        if "❌" in raw and not n:
            n = "HETHANG"
        if not n:
            continue
        target = None
        if n in menu_map:
            await S.set_setting(f"icon_{menu_map[n]}", icon)
            target = f"nút {menu_map[n]}"
        else:
            c = next((c for c in cats if norm(c["name"]) == n), None) or \
                next((c for c in cats if norm(c["name"]).startswith(n) and len(n) >= 3), None)
            if c:
                await db.execute("UPDATE categories SET custom_emoji_id=? WHERE id=?", (icon, c["id"]))
                target = f"danh mục {c['name']}"
            else:
                p = next((p for p in prods if norm(p["name"]) == n), None) or \
                    next((p for p in prods if norm(p["name"]).startswith(n) and len(n) >= 5), None)
                if p:
                    await db.execute("UPDATE products SET custom_emoji_id=? WHERE id=?", (icon, p["id"]))
                    target = f"SP {p['name'][:30]}"
        (done if target else miss).append(target or raw)
    return (f"✅ Đã gán {len(done)} icon:\n" + "\n".join(f"• {esc(x)}" for x in done) +
            (f"\n\n⚠️ Không tìm thấy ({len(miss)}):\n" + "\n".join(f"• {esc(x)}" for x in miss) if miss else ""))


# ======================================================================
# GENERIC INPUT HANDLER
# ======================================================================
@router.message(AdminSG.input)
async def on_input(message: Message, state: FSMContext, bot: Bot):
    from handlers.user import parse_amount  # tránh vòng import

    data = await state.get_data()
    action = data.get("action")
    txt = (message.text or "").strip()

    async def done(reply: str, markup=None):
        await state.clear()
        await ui.answer(message, reply, markup)

    # ---------- users ----------
    if action == "search_user":
        u = await S.find_user(txt)
        if not u:
            return await message.answer("❌ Không tìm thấy user. Gửi lại hoặc /cancel.")
        await state.clear()
        return await ui.answer(message, *await render_user(u["user_id"]))

    if action == "adj_amount":
        amt = parse_amount(txt)
        if not amt or amt <= 0:
            return await message.answer("❌ Số tiền không hợp lệ.")
        await state.update_data(action="adj_reason", amount=amt)
        return await message.answer("📝 Nhập lý do (sẽ gửi cho user):")

    if action == "adj_reason":
        uid, amt, sign = data["uid"], data["amount"], data["sign"]
        try:
            bal = await S.adjust_balance(uid, sign * amt, "admin_adjust", txt[:200] or "Admin điều chỉnh")
        except S.ShopError as e:
            return await done(f"❌ Lỗi: {e.code} (số dư hiện tại không đủ để trừ?)")
        u = await S.get_user(uid)
        key = "notify_add" if sign > 0 else "notify_sub"
        await notify.notify_user(bot, uid, t(u["language"], key, amount=S.fmt_money(amt), reason=esc(txt),
                                             balance=S.fmt_money(bal)))
        await state.clear()
        await message.answer(f"✅ Đã {'cộng' if sign > 0 else 'trừ'} {S.fmt_money(amt)}. Số dư mới: {S.fmt_money(bal)}")
        return await ui.answer(message, *await render_user(uid))

    if action == "disc":
        try:
            v = float(txt.replace(",", ".").rstrip("%"))
            assert 0 <= v <= 100
        except (ValueError, AssertionError):
            return await message.answer("❌ Nhập số từ 0 đến 100.")
        await db.execute("UPDATE users SET discount_rate=? WHERE user_id=?", (v, data["uid"]))
        await state.clear()
        return await ui.answer(message, *await render_user(data["uid"]))

    if action == "rate":
        if not txt.isdigit():
            return await message.answer("❌ Nhập số nguyên.")
        await db.execute("UPDATE users SET api_rate_limit=? WHERE user_id=?", (int(txt), data["uid"]))
        await state.clear()
        return await ui.answer(message, *await render_user(data["uid"]))

    # ---------- categories ----------
    if action == "cat_add":
        ids = ui.custom_emoji_ids(message)
        name = strip_custom_emoji(txt, message.entities)
        if not name:
            return await message.answer("❌ Tên không hợp lệ.")
        pos = await db.fetchval("SELECT MAX(position) FROM categories", default=0) + 1
        cid = await db.execute("INSERT INTO categories(name, custom_emoji_id, position) VALUES (?,?,?)",
                               (name, ids[0] if ids else None, pos))
        await state.clear()
        return await ui.answer(message, *await render_cat(cid))

    if action in ("cat_name", "cat_emoji", "cat_pos", "cat_icon"):
        cid = data["cid"]
        if action == "cat_icon":
            ok, icon = parse_icon(message)
            if not ok:
                return await message.answer("❌ Không thấy emoji Premium. Gửi lại hoặc /cancel.")
            await db.execute("UPDATE categories SET custom_emoji_id=? WHERE id=?", (icon, cid))
        elif action == "cat_name":
            await db.execute("UPDATE categories SET name=? WHERE id=?", (txt, cid))
        elif action == "cat_emoji":
            await db.execute("UPDATE categories SET emoji=? WHERE id=?", ("" if txt == "0" else txt[:8], cid))
        else:
            if not txt.lstrip("-").isdigit():
                return await message.answer("❌ Nhập số.")
            await db.execute("UPDATE categories SET position=? WHERE id=?", (int(txt), cid))
        await state.clear()
        return await ui.answer(message, *await render_cat(cid))

    # ---------- products ----------
    if action == "prod_add_name":
        ids = ui.custom_emoji_ids(message)
        name = strip_custom_emoji(txt, message.entities) if ids else txt
        if not name:
            return await message.answer("❌ Tên không hợp lệ.")
        await state.update_data(action="prod_add_price", name=name, custom_icon=ids[0] if ids else None)
        return await message.answer("💰 Gửi giá bán (vd: 30000 hoặc 30k):")

    if action == "prod_add_price":
        price = parse_amount(txt)
        if price is None or price < 0:
            return await message.answer("❌ Giá không hợp lệ.")
        pos = await db.fetchval("SELECT MAX(position) FROM products WHERE category_id=?", (data["cid"],), 0) + 1
        pid = await db.execute(
            "INSERT INTO products(category_id, name, price, custom_emoji_id, position) VALUES (?,?,?,?,?)",
            (data["cid"], data["name"], price, data.get("custom_icon"), pos),
        )
        await state.update_data(action="prod_add_stock", pid=pid)
        return await message.answer(
            "📦 <b>Đã tạo sản phẩm!</b>\n\n"
            "👉 Bây giờ hãy gửi <b>danh sách tài khoản</b> (mỗi dòng 1 acc hoặc file <code>.txt</code>) để nhập kho và <b>tự động bắn thông báo có hàng mới</b> cho toàn bộ người dùng!\n"
            "• Hoặc gửi <code>inf</code> nếu là Kho vô hạn (∞)\n"
            "• Hoặc gửi <code>0</code> nếu chưa nhập kho ngay:"
        )

    if action == "prod_add_stock":
        pid = data["pid"]
        if not message.document and txt.lower() in ("0", "khong", "không"):
            await state.clear()
            return await ui.answer(message, *await render_prod(pid))
        if not message.document and txt.lower() in ("inf", "vohan", "∞"):
            await db.execute("UPDATE products SET is_infinite_stock=1 WHERE id=?", (pid,))
            await state.clear()
            asyncio.create_task(notify.broadcast_new_stock(bot, pid, 1))
            await message.answer("📣 Đã bật Kho vô hạn (∞) và đang gửi <b>Thông báo có hàng mới</b> tới toàn bộ người dùng!")
            return await ui.answer(message, *await render_prod(pid))

        if message.document:
            if message.document.file_size and message.document.file_size > 20 * 1024 * 1024:
                return await message.answer("❌ File quá lớn (tối đa 20MB).")
            buf = await bot.download(message.document)
            content = buf.read().decode("utf-8-sig", errors="ignore")
        else:
            content = message.text or ""
        lines = [x for x in content.replace("\r", "").split("\n") if x.strip()]
        if not lines:
            return await message.answer("❌ Không có dữ liệu. Gửi lại hoặc /cancel.")
        added, dup = await S.import_stock(pid, lines)
        await state.clear()
        if added > 0:
            asyncio.create_task(notify.broadcast_new_stock(bot, pid, added))
        await message.answer(
            f"📥 <b>ĐÃ LÊN SẢN PHẨM & NHẬP KHO HOÀN TẤT</b>\n"
            f"✅ Thêm mới: <b>{added}</b> (Trùng lặp: {dup})\n"
            f"📣 Đang tự động gửi <b>Thông báo có hàng mới</b> tới toàn bộ người dùng!"
        )
        return await ui.answer(message, *await render_prod(pid))

    if action in ("prod_name", "prod_price", "prod_cost", "prod_icon", "prod_emoji", "prod_warr", "prod_desc"):
        pid = data["pid"]
        if action == "prod_icon":
            ok, icon = parse_icon(message)
            if not ok:
                return await message.answer("❌ Không thấy emoji Premium. Gửi lại hoặc /cancel.")
            await db.execute("UPDATE products SET custom_emoji_id=? WHERE id=?", (icon, pid))
        elif action in ("prod_price", "prod_cost"):
            v = parse_amount(txt)
            if v is None or v < 0:
                return await message.answer("❌ Giá không hợp lệ.")
            col = "price" if action == "prod_price" else "cost_price"
            await db.execute(f"UPDATE products SET {col}=? WHERE id=?", (v, pid))
        else:
            col = {"prod_name": "name", "prod_emoji": "emoji", "prod_warr": "warranty_info",
                   "prod_desc": "description"}[action]
            val = "" if (txt == "0" and col in ("emoji", "description")) else txt
            if col == "name" and not val:
                return await message.answer("❌ Tên không hợp lệ.")
            await db.execute(f"UPDATE products SET {col}=? WHERE id=?", (val, pid))
        await state.clear()
        return await ui.answer(message, *await render_prod(pid))

    if action == "import":
        pid = data["pid"]
        if message.document:
            if message.document.file_size and message.document.file_size > 20 * 1024 * 1024:
                return await message.answer("❌ File quá lớn (tối đa 20MB).")
            buf = await bot.download(message.document)
            content = buf.read().decode("utf-8-sig", errors="ignore")
        else:
            content = message.text or ""
        lines = [x for x in content.replace("\r", "").split("\n") if x.strip()]
        if not lines:
            return await message.answer("❌ Không có dữ liệu. Gửi lại hoặc /cancel.")
        added, dup = await S.import_stock(pid, lines)
        await state.clear()
        if added > 0:
            asyncio.create_task(notify.broadcast_new_stock(bot, pid, added))
        await message.answer(
            f"📥 <b>NHẬP KHO HOÀN TẤT</b>\n"
            f"✅ Thêm mới: <b>{added}</b>\n"
            f"♻️ Trùng lặp / bỏ qua: {dup}\n"
            + ("📣 Đã tự động gửi <b>Thông báo có hàng mới</b> tới toàn bộ người dùng!" if added > 0 else "")
        )
        return await ui.answer(message, *await render_prod(pid))

    if action == "prod_notif":
        pid = data["pid"]
        qty = int(txt) if txt.isdigit() and int(txt) > 0 else 1
        await state.clear()
        asyncio.create_task(notify.broadcast_new_stock(bot, pid, qty))
        await message.answer(f"📣 Đang gửi <b>Thông báo có hàng mới (Thêm: {qty})</b> tới toàn bộ người dùng!")
        return await ui.answer(message, *await render_prod(pid))

    # ---------- orders / tickets ----------
    if action == "order_lookup":
        o = await S.get_order(txt)
        if not o:
            return await message.answer("❌ Không tìm thấy đơn. Gửi lại hoặc /cancel.")
        await state.clear()
        return await ui.answer(message, *await render_order_admin(o))

    if action == "deliver":
        oid = data["oid"]
        o = await S.get_order(oid)
        content = message.text or message.caption or ""
        if not o or not content:
            return await message.answer("❌ Nội dung trống.")
        await db.execute("UPDATE orders SET accounts_delivered=?, status='completed' WHERE order_id=?",
                         ((o["accounts_delivered"] + "\n" if o["accounts_delivered"] else "") + content, oid))
        sent = await notify.notify_user(bot, o["user_id"], f"📦 <b>ĐƠN</b> <code>{oid}</code> <b>ĐÃ ĐƯỢC XỬ LÝ!</b>\n"
                                                           f"📦 {esc(o['product_name'])}\n\n<code>{esc(content)}</code>")
        return await done(f"✅ Đã giao đơn {oid}" + ("" if sent else " (⚠️ khách đã chặn bot)"))

    if action == "reject_reason":
        tid = data["tid"]
        tk = await db.fetchone("SELECT * FROM tickets WHERE id=?", (tid,))
        await _close_ticket(tid, "rejected", txt)
        await notify.notify_user(bot, tk["user_id"], f"❌ <b>Phiếu bảo hành #{tid}</b> (đơn <code>{tk['order_id']}</code>) "
                                                     f"bị từ chối.\n📝 Lý do: {esc(txt)}")
        return await done(f"✅ Đã từ chối phiếu #{tid}")

    # ---------- broadcast ----------
    if action == "bc":
        await state.update_data(action="bc_wait", bc_chat=message.chat.id, bc_msg=message.message_id, bc_btn=False)
        return await message.answer("👆 Xem trước nội dung ở trên. Chọn thao tác:", reply_markup=bc_kb(False))

    # ---------- icons ----------
    if action == "menu_icon":
        ok, icon = parse_icon(message)
        if not ok:
            return await message.answer("❌ Không thấy emoji Premium. Gửi lại hoặc /cancel.")
        await S.set_setting(f"icon_{data['key']}", icon)
        await state.clear()
        return await ui.answer(message, *await render_icons())

    if action == "bulk_icons":
        await state.clear()
        return await message.answer(await bulk_icons(message))

    # ---------- bank & auto-bank ----------
    if action in ("bank_id", "bank_account", "bank_account_name", "deposit_prefix", "min_deposit",
                  "sepay_token", "casso_key", "web2m_url"):
        if action == "min_deposit":
            amt = parse_amount(txt)
            if not amt or amt < 1000:
                return await message.answer("❌ Số tiền tối thiểu không hợp lệ (tối thiểu 1.000đ).")
            val = str(amt)
        elif action in ("sepay_token", "casso_key", "web2m_url") and txt in ("0", "-", "xoa", "xóa"):
            val = ""
        elif action == "bank_id":
            val = txt.upper().strip()
        elif action == "deposit_prefix":
            val = re.sub(r"\s+", "", txt.upper()) or "NAP"
        else:
            val = txt.strip()
        await S.set_setting(action, val)
        await state.clear()
        await message.answer("✅ Đã lưu cấu hình ngân hàng!")
        return await ui.answer(message, *await render_bank())

    if action == "bank_quick":
        parts = [p.strip() for p in txt.split("|")]
        if len(parts) < 3 or not parts[0] or not parts[1]:
            return await message.answer("❌ Sai định dạng! Hãy gửi: <code>MÃ_NH|SỐ_TK|TÊN_CHỦ_TK</code>\nVí dụ: <code>MOMO|0912345678|NGUYEN LE HOANG NHAT</code>")
        await S.set_setting("bank_id", parts[0].upper())
        await S.set_setting("bank_account", parts[1])
        await S.set_setting("bank_account_name", parts[2].upper())
        await state.clear()
        await message.answer(f"✅ Đã cài ngân hàng/ví: <b>{esc(parts[0].upper())}</b> - <code>{esc(parts[1])}</code> ({esc(parts[2].upper())})")
        return await ui.answer(message, *await render_bank())

    if action == "imap_quick":
        if txt in ("0", "-", "xoa", "xóa"):
            await S.set_setting("imap_email", "")
            await S.set_setting("imap_pass", "")
            await state.clear()
            await message.answer("✅ Đã xóa cấu hình Gmail IMAP.")
            return await ui.answer(message, *await render_bank())
        parts = [p.strip() for p in txt.split("|")]
        if len(parts) < 2 or "@" not in parts[0] or not parts[1]:
            return await message.answer("❌ Sai định dạng! Hãy gửi: <code>email@gmail.com|mat_khau_ung_dung</code>")
        email_addr = parts[0].strip()
        app_pass = parts[1].replace(" ", "").strip()
        await S.set_setting("imap_email", email_addr)
        await S.set_setting("imap_pass", app_pass)
        await state.clear()
        await message.answer(f"✅ Đã gắn Gmail đọc thông báo MoMo/Bank: <code>{esc(email_addr)}</code>!")
        return await ui.answer(message, *await render_bank())

    if action == "bank_sim":
        parts = [p.strip() for p in txt.split("|")]
        if len(parts) < 2 or not parts[0]:
            return await message.answer("❌ Sai định dạng! Hãy gửi: <code>UID|SỐ_TIỀN</code> hoặc <code>DHxxxxxx|SỐ_TIỀN</code>")
        target_str = parts[0].upper()
        amt = parse_amount(parts[1])
        if not amt or amt <= 0:
            return await message.answer("❌ Số tiền không hợp lệ.")
        cfg = await bank_auto.get_bank_config()
        tx_ref = "SIM_" + secrets.token_hex(4).upper()
        content = f"{cfg['prefix']} {target_str}"
        ok = await bank_auto.process_bank_tx(bot, tx_ref, amt, content, "AutoBank-Test")
        await state.clear()
        if ok:
            await message.answer(f"✅ Đã xử lý giao dịch <b>+{S.fmt_money(amt)}</b> với nội dung <code>{content}</code> (mã GD: <code>{tx_ref}</code>)!")
        else:
            await message.answer(f"❌ Không tìm thấy đơn chờ hoặc UID hợp lệ cho nội dung <code>{content}</code>.")
        return await ui.answer(message, *await render_bank())

    await state.clear()


# ======================================================================
# EMOJI ID TOOL (router riêng, đăng ký cuối cùng)
# ======================================================================
emoji_router = Router(name="emoji_tool")
emoji_router.message.filter(IsAdmin())


@emoji_router.message(F.entities | F.caption_entities)
async def emoji_ids(message: Message):
    ents = (message.entities or []) + (message.caption_entities or [])
    items = [e for e in ents if e.type == "custom_emoji"]
    if not items:
        return
    text = message.text or message.caption or ""
    b = text.encode("utf-16-le")
    lines = []
    for e in items:
        ch = b[e.offset * 2:(e.offset + e.length) * 2].decode("utf-16-le", errors="ignore")
        lines.append(f'{ui.ce(e.custom_emoji_id, ch)} <code>{e.custom_emoji_id}</code>')
    await ui.answer(message, "💎 <b>Custom Emoji ID:</b>\n" + "\n".join(lines) +
                    "\n\n💡 Dùng /icons để gán hàng loạt hoặc /admin → 🎨 Icon Premium.")
