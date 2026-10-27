"""Handlers phía khách hàng."""
import logging
import math
import secrets
from urllib.parse import quote

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

import bank_auto
import crypto
import db
import notify
import services as S
import ui
from config import (BANK_ACCOUNT, BANK_ACCOUNT_NAME, BANK_ID, BINANCE_PAY_ID, CHANNEL_LINK,
                    DEPOSIT_PREFIX, GROUP_LINK, MIN_DEPOSIT, PUBLIC_URL, SHOP_NAME, SUPPORT_USERNAME,
                    USDT_BEP20_ADDRESS, USDT_RATE, USDT_TRC20_ADDRESS)
from texts import menu_label_map, t
from ui import btn, esc, kb

log = logging.getLogger(__name__)
router = Router(name="user")
MENU_LABELS = menu_label_map()


class UserSG(StatesGroup):
    qty = State()
    bank_amount = State()
    trc20_txid = State()
    crypto_amount = State()
    crypto_txid = State()
    w_order = State()
    w_reason = State()


def home_btn(lang):
    return btn(t(lang, "home"), "u:menu", style=None)


# ======================================================================
# RENDERERS -> (text, markup)
# ======================================================================
async def render_main(user):
    lang = user["language"]
    return t(lang, "start_3"), await ui.main_menu_kb(lang)


async def render_shop(user, page: int = 0):
    lang = user["language"]
    cats = await S.list_categories()
    rows, row = [], []
    for c in cats:
        row.append(await ui.category_button(c, f"cat:{c['id']}:0"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    prods = await S.list_products()
    per = max(5, 95 - len(cats) - 5)  # Telegram giới hạn 100 nút / bàn phím
    pages = max(1, math.ceil(len(prods) / per))
    page = max(0, min(page, pages - 1))
    for p in prods[page * per:(page + 1) * per]:
        rows.append([await ui.product_button(p, user, f"p:{p['id']}")])
    if pages > 1:
        rows.append([
            btn("◀️", f"shop:{max(0, page - 1)}", style=None),
            btn(f"{page + 1}/{pages}", "noop", style=None),
            btn("▶️", f"shop:{min(pages - 1, page + 1)}", style=None),
        ])
    rows.append([btn(t(lang, "refresh"), f"rf:shop:{page}", icon=await ui.menu_icon("refresh"), emoji="🧿")])
    rows.append([home_btn(lang)])
    return t(lang, "shop_title"), kb(rows)


async def render_category(user, cid: int, page: int = 0):
    lang = user["language"]
    c = await S.get_category(cid)
    if not c:
        return None
    prods = await S.list_products(cid)
    per = 40
    pages = max(1, math.ceil(len(prods) / per))
    page = max(0, min(page, pages - 1))
    rows = [[await ui.product_button(p, user, f"p:{p['id']}")] for p in prods[page * per:(page + 1) * per]]
    if pages > 1:
        rows.append([
            btn("◀️", f"cat:{cid}:{max(0, page - 1)}", style=None),
            btn(f"{page + 1}/{pages}", "noop", style=None),
            btn("▶️", f"cat:{cid}:{min(pages - 1, page + 1)}", style=None),
        ])
    rows.append([btn(t(lang, "refresh"), f"rf:cat:{cid}:{page}", icon=await ui.menu_icon("refresh"), emoji="🧿")])
    rows.append([btn(t(lang, "back"), "u:buy", style=None), home_btn(lang)])
    text = t(lang, "cat_title", icon=ui.ce(c["custom_emoji_id"], c["emoji"] or "📁"), name=esc(c["name"]))
    if not prods:
        text += "\n\n" + t(lang, "cat_empty")
    return text, kb(rows)


async def render_product(user, pid: int):
    lang = user["language"]
    p = await S.get_product(pid)
    if not p or not p["is_active"] or not p["cat_active"]:
        return None
    price = S.unit_price(user, p)
    disc = ""
    if price != p["price"]:
        disc = t(lang, "disc_note", old=S.fmt_money(p["price"]), rate=f"{user['discount_rate']:g}")
    stock = "∞" if p["is_infinite_stock"] else str(p["stock"])
    icon, emoji = ui.item_icon(p)
    text = t(lang, "product_info", icon=ui.ce(icon, emoji or "📦"), name=esc(p["name"]),
             price=S.fmt_money(price), disc=disc, stock=stock,
             warranty=esc(p["warranty_info"] or "-"),
             desc=(f"📝 {esc(p['description'])}\n" if p["description"] else ""),
             balance=S.fmt_money(user["balance"]))
    rows = []
    if S.in_stock(p):
        opts = [q for q in (1, 2, 3, 5, 10) if p["is_infinite_stock"] or q <= p["stock"]]
        rows.append([btn(str(q), f"q:{pid}:{q}") for q in opts])
        rows.append([btn(t(lang, "btn_quick_qr", price=S.fmt_money(price)), f"qrpay:{pid}:1", style="success")])
        rows.append([btn(t(lang, "enter_qty"), f"qc:{pid}")])
    else:
        text = t(lang, "out_of_stock", name=esc(p["name"]), avail=0)
        sim = await S.similar_products(p)
        if sim:
            text += t(lang, "suggest")
            for s in sim:
                rows.append([await ui.product_button(s, user, f"p:{s['id']}")])
    rows.append([btn(t(lang, "back"), f"cat:{p['category_id']}:0", style=None), home_btn(lang)])
    return text, kb(rows)


async def render_confirm(user, pid: int, qty: int):
    lang = user["language"]
    p = await S.get_product(pid)
    if not p or not p["is_active"]:
        return None
    price = S.unit_price(user, p)
    total = price * qty
    text = t(lang, "confirm", name=esc(p["name"]), qty=qty, price=S.fmt_money(price),
             total=S.fmt_money(total), balance=S.fmt_money(user["balance"]))
    rows = [[btn(t(lang, "btn_pay_qr", total=S.fmt_money(total)), f"qrpay:{pid}:{qty}", style="success")]]
    if user["balance"] < total:
        text += t(lang, "not_enough", need=S.fmt_money(total - user["balance"]))
        rows.append([btn(t(lang, "btn_topup"), "u:wallet"), btn(t(lang, "back"), f"p:{pid}", style=None)])
    else:
        rows.append([btn(t(lang, "btn_confirm"), f"b:{pid}:{qty}", style="primary"),
                     btn(t(lang, "btn_cancel"), f"p:{pid}", style="danger")])
    return text, kb(rows)


async def render_profile(user):
    lang = user["language"]
    n_orders = await db.fetchval("SELECT COUNT(*) FROM orders WHERE user_id=?", (user["user_id"],), 0)
    disc = f" (-{user['discount_rate']:g}%)" if user["discount_rate"] else ""
    text = t(lang, "profile", uid=user["user_id"],
             username=f"@{esc(user['username'])}" if user["username"] else "-",
             balance=S.fmt_money(user["balance"]), deposited=S.fmt_money(user["total_deposited"]),
             spent=S.fmt_money(user["total_spent"]),
             role=t(lang, "role_reseller" if user["role"] == "reseller" else "role_member"),
             disc=disc, orders=n_orders, joined=user["created_at"])
    return text, kb([[btn(t(lang, "m_wallet"), "u:wallet", icon=await ui.menu_icon("wallet"), emoji="👛"),
                      btn(t(lang, "m_history"), "hist:0", icon=await ui.menu_icon("history"), emoji="🧿")],
                     [home_btn(lang)]])


async def render_history(user, page: int = 0):
    lang = user["language"]
    per, max_total = 10, 50
    total = min(max_total, await db.fetchval("SELECT COUNT(*) FROM orders WHERE user_id=?",
                                             (user["user_id"],), 0))
    if not total:
        return t(lang, "history_empty"), kb([[home_btn(lang)]])
    pages = math.ceil(total / per)
    page = max(0, min(page, pages - 1))
    orders = await db.fetchall(
        "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
        (user["user_id"], per, page * per))
    rows = [[btn(f"{o['order_id']} | {o['product_name'][:28]} | {S.fmt_k(o['total_price'])}",
                 f"ord:{o['order_id']}", style=None)] for o in orders]
    if pages > 1:
        rows.append([btn("◀️", f"hist:{max(0, page - 1)}", style=None),
                     btn(f"{page + 1}/{pages}", "noop", style=None),
                     btn("▶️", f"hist:{min(pages - 1, page + 1)}", style=None)])
    rows.append([home_btn(lang)])
    return t(lang, "history_title", page=page + 1), kb(rows)


async def render_wallet(user):
    lang = user["language"]
    text = t(lang, "wallet", balance=S.fmt_money(user["balance"]),
             deposited=S.fmt_money(user["total_deposited"]))
    return text, kb([[btn(t(lang, "btn_bank"), "dep:bank")],
                     [btn(t(lang, "btn_crypto"), "dep:crypto")],
                     [btn(t(lang, "btn_txhist"), "txh")],
                     [home_btn(lang)]])


async def render_api(user):
    lang = user["language"]
    key = user["api_key"] or await S.reset_api_key(user["user_id"])
    text = t(lang, "api_info", key=key, rate=user["api_rate_limit"], base=f"{PUBLIC_URL}/api/v1")
    return text, kb([[btn(t(lang, "btn_api_reset"), "api:reset"), btn(t(lang, "btn_api_docs"), "api:docs")],
                     [home_btn(lang)]])


async def render_support(user):
    lang = user["language"]
    text = t(lang, "support", support=SUPPORT_USERNAME, group=GROUP_LINK, channel=CHANNEL_LINK)
    rows = [[btn(t(lang, "btn_contact"), url=f"https://t.me/{SUPPORT_USERNAME}")]] if SUPPORT_USERNAME else []
    rows.append([home_btn(lang)])
    return text, kb(rows)


def render_language():
    return t("vi", "lang_choose"), kb([[btn("🇻🇳 Tiếng Việt", "lang:vi"), btn("🇬🇧 English", "lang:en")]])


async def show(target, rendered):
    """target: CallbackQuery (edit) hoặc Message (gửi mới)."""
    if rendered is None:
        return
    text, markup = rendered
    if isinstance(target, CallbackQuery):
        await ui.edit(target, text, markup, disable_web_page_preview=True)
    else:
        await ui.answer(target, text, markup, disable_web_page_preview=True)


# ======================================================================
# /start & menu
# ======================================================================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: dict, lang: str):
    await state.clear()
    await ui.answer(message, t(lang, "start_1"), await ui.reply_menu_kb(lang))
    await ui.answer(message, t(lang, "start_2"))
    await show(message, await render_main(user))
    welcome = t(lang, "welcome", shop=esc(SHOP_NAME), group=GROUP_LINK, channel=CHANNEL_LINK,
                support=SUPPORT_USERNAME)
    w = await ui.answer(message, welcome, disable_web_page_preview=True)
    try:
        await w.pin(disable_notification=True)
    except TelegramBadRequest:
        pass


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, lang: str):
    await state.clear()
    await message.answer(t(lang, "cancel"))


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, user: dict):
    await state.clear()
    await show(message, await render_main(user))


@router.message(F.text.in_(MENU_LABELS.keys()))
async def quick_menu(message: Message, state: FSMContext, user: dict, lang: str):
    await state.clear()
    await dispatch_menu(message, state, user, lang, MENU_LABELS[message.text])


@router.callback_query(F.data.startswith("u:"))
async def cb_menu(cb: CallbackQuery, state: FSMContext, user: dict, lang: str):
    await state.clear()
    await dispatch_menu(cb, state, user, lang, cb.data[2:])
    await cb.answer()


async def dispatch_menu(target, state, user, lang, key):
    if key == "menu":
        await show(target, await render_main(user))
    elif key == "buy":
        await show(target, await render_shop(user))
    elif key == "profile":
        await show(target, await render_profile(user))
    elif key == "history":
        await show(target, await render_history(user))
    elif key == "wallet":
        await show(target, await render_wallet(user))
    elif key == "api":
        await show(target, await render_api(user))
    elif key == "support":
        await show(target, await render_support(user))
    elif key == "warranty":
        await state.set_state(UserSG.w_order)
        await show(target, (t(lang, "warranty_ask_order"), kb([[home_btn(lang)]])))
    elif key == "language":
        await show(target, render_language())


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()


# ======================================================================
# SHOP
# ======================================================================
@router.callback_query(F.data.startswith("shop:"))
async def cb_shop(cb: CallbackQuery, user: dict):
    await show(cb, await render_shop(user, int(cb.data.split(":")[1])))
    await cb.answer()


@router.callback_query(F.data.startswith("cat:"))
async def cb_cat(cb: CallbackQuery, user: dict, lang: str):
    _, cid, page = cb.data.split(":")
    c = await S.get_category(int(cid))
    if not c or not c["is_active"]:
        return await cb.answer(t(lang, "cat_paused"), show_alert=True)
    await show(cb, await render_category(user, int(cid), int(page)))
    await cb.answer()


@router.callback_query(F.data.startswith("rf:"))
async def cb_refresh(cb: CallbackQuery, user: dict, lang: str):
    parts = cb.data.split(":")
    if parts[1] == "shop":
        await show(cb, await render_shop(user, int(parts[2])))
    else:
        await show(cb, await render_category(user, int(parts[2]), int(parts[3])))
    await cb.answer(t(lang, "refreshed"))


@router.callback_query(F.data.startswith("p:"))
async def cb_product(cb: CallbackQuery, state: FSMContext, user: dict, lang: str):
    await state.clear()
    r = await render_product(user, int(cb.data[2:]))
    if r is None:
        return await cb.answer(t(lang, "inactive"), show_alert=True)
    await show(cb, r)
    await cb.answer()


@router.callback_query(F.data.startswith("q:"))
async def cb_qty(cb: CallbackQuery, user: dict, lang: str):
    _, pid, qty = cb.data.split(":")
    r = await render_confirm(user, int(pid), int(qty))
    if r is None:
        return await cb.answer(t(lang, "inactive"), show_alert=True)
    await show(cb, r)
    await cb.answer()


@router.callback_query(F.data.startswith("qc:"))
async def cb_qty_custom(cb: CallbackQuery, state: FSMContext, lang: str):
    pid = int(cb.data[3:])
    p = await S.get_product(pid)
    if not p:
        return await cb.answer()
    mx = 1000 if p["is_infinite_stock"] else max(1, p["stock"])
    await state.set_state(UserSG.qty)
    await state.update_data(pid=pid, max=mx)
    await cb.message.answer(t(lang, "ask_qty", max=mx))
    await cb.answer()


@router.message(UserSG.qty, F.text)
async def st_qty(message: Message, state: FSMContext, user: dict, lang: str):
    data = await state.get_data()
    txt = message.text.strip()
    if not txt.isdigit() or not (1 <= int(txt) <= data["max"]):
        return await message.answer(t(lang, "bad_qty"))
    await state.clear()
    await show(message, await render_confirm(user, data["pid"], int(txt)))


@router.callback_query(F.data.startswith("b:"))
async def cb_buy(cb: CallbackQuery, bot: Bot, user: dict, lang: str):
    _, pid, qty = cb.data.split(":")
    pid, qty = int(pid), int(qty)
    await cb.answer(t(lang, "processing_buy"))
    try:
        res = await S.purchase(user["user_id"], pid, qty)
    except S.ShopError as e:
        p = await S.get_product(pid)
        if e.code == "insufficient":
            text = t(lang, "not_enough", need=S.fmt_money(e.info["total"] - e.info["balance"])).strip()
            return await show(cb, (text, kb([[btn(t(lang, "btn_topup"), "u:wallet")], [home_btn(lang)]])))
        if e.code == "out_of_stock" and p:
            text = t(lang, "out_of_stock", name=esc(p["name"]), avail=e.info.get("available", 0))
            rows = []
            sim = await S.similar_products(p)
            if sim:
                text += t(lang, "suggest")
                rows = [[await ui.product_button(s, user, f"p:{s['id']}")] for s in sim]
            rows.append([btn(t(lang, "back"), f"p:{pid}", style=None), home_btn(lang)])
            return await show(cb, (text, kb(rows)))
        return await show(cb, (t(lang, "inactive"), kb([[home_btn(lang)]])))
    await deliver(cb, bot, user, lang, res)


@router.callback_query(F.data.startswith("qrpay:"))
async def cb_qrpay(cb: CallbackQuery, user: dict, lang: str):
    _, pid, qty = cb.data.split(":")
    pid, qty = int(pid), int(qty)
    cfg = await bank_auto.get_bank_config()
    if not cfg["account"]:
        return await cb.answer(t(lang, "bank_off"), show_alert=True)
    p = await S.get_product(pid)
    if not p or not p["is_active"] or not p["cat_active"]:
        return await cb.answer(t(lang, "inactive"), show_alert=True)
    if not p["is_infinite_stock"] and p["stock"] < qty:
        return await cb.answer(
            t(lang, "out_of_stock", name=p["name"], avail=p["stock"]), show_alert=True
        )
    price = S.unit_price(user, p)
    total = price * qty
    await cb.answer("⏳ Đang tạo ảnh mã QR thanh toán...")

    intent = await bank_auto.create_order_intent(user["user_id"], pid, qty, total)
    pay_code = intent["pay_code"]
    content = intent["content"]
    caption = t(
        lang,
        "direct_qr",
        product=esc(p["name"]),
        qty=qty,
        bank=esc(cfg["bank_id"]),
        acc=esc(cfg["account"]),
        name=esc(cfg["account_name"]),
        amount=S.fmt_money(total),
        content=esc(content),
    )
    markup = kb([
        [btn(t(lang, "direct_qr_paid_btn"), f"qrdone:{pay_code}", style="success")],
        [btn(t(lang, "btn_cancel"), f"qrcancel:{pay_code}", style="danger"), home_btn(lang)],
    ])
    msg = await bank_auto.send_vietqr_photo(cb.message, cfg, total, content, caption, markup)
    await bank_auto.bind_intent_message(pay_code, msg.chat.id, msg.message_id)


@router.callback_query(F.data.startswith("qrcancel:"))
async def cb_qrcancel(cb: CallbackQuery, lang: str):
    pay_code = cb.data.split(":")[1]
    await db.execute(
        "UPDATE payment_intents SET status='cancelled' WHERE pay_code=? AND status='pending'",
        (pay_code,),
    )
    try:
        await cb.message.delete()
    except TelegramBadRequest:
        pass
    await cb.answer(t(lang, "cancel"))


@router.callback_query(F.data.startswith("qrdone:"))
async def cb_qrdone(cb: CallbackQuery, bot: Bot, user: dict, lang: str):
    pay_code = cb.data.split(":")[1]
    intent = await db.fetchone("SELECT * FROM payment_intents WHERE pay_code=?", (pay_code,))
    if not intent or intent["user_id"] != user["user_id"]:
        return await cb.answer("❌ Không tìm thấy đơn thanh toán.", show_alert=True)
    if intent["status"] == "completed":
        return await cb.answer("✅ Đơn hàng này đã được thanh toán và giao sản phẩm!", show_alert=True)
    if intent["status"] != "pending":
        return await cb.answer("❌ Đơn thanh toán đã hủy hoặc từ chối.", show_alert=True)

    # 1. Nếu có gắn API đọc tự động thì kiểm tra xem có giao dịch chưa
    await bank_auto.check_bank_transactions_once(bot)
    intent = await db.fetchone("SELECT * FROM payment_intents WHERE pay_code=?", (pay_code,))
    if intent["status"] == "completed":
        return await cb.answer("✅ Đã xác nhận giao dịch và gửi sản phẩm!")

    # 2. Chế độ duyệt thủ công bởi Admin (báo ngay về cho Admin duyệt 1-click)
    cfg = await bank_auto.get_bank_config()
    if intent.get("tx_ref") != "notified_admin":
        await db.execute("UPDATE payment_intents SET tx_ref='notified_admin' WHERE pay_code=?", (pay_code,))
        p = await S.get_product(intent["product_id"])
        who = f"@{esc(user['username'])}" if user["username"] else esc(user["full_name"] or "")
        await notify.notify_admins(
            bot,
            f"🔔 <b>ĐƠN MUA BẰNG QR CHỜ DUYỆT</b> <code>{pay_code}</code>\n\n"
            f"👤 Khách hàng: {who} (<code>{user['user_id']}</code>)\n"
            f"📦 Sản phẩm: <b>{esc(p['name'] if p else '')}</b> x{intent['quantity']}\n"
            f"🏛 Nhận qua: <b>{esc(cfg['bank_id'])}</b> - <b>{esc(cfg['account_name'])}</b>\n"
            f"💰 Số tiền: <b>{S.fmt_money(intent['amount'])}</b>\n"
            f"📝 Nội dung CK: <code>{esc(intent['content'])}</code>\n\n"
            f"👇 <i>Kiểm tra MoMo nhận đủ tiền rồi bấm nút bên dưới để Bot tự động xuất kho giao hàng cho khách:</i>",
            kb([
                [btn("✅ Duyệt & Giao sản phẩm ngay", f"adm_qrok:{pay_code}", style="success")],
                [btn("❌ Từ chối đơn này", f"adm_qrno:{pay_code}", style="danger")],
            ]),
        )
        try:
            await cb.message.edit_reply_markup(
                reply_markup=kb([
                    [btn("⏳ Đang chờ Admin xác nhận & giao hàng...", f"qrdone:{pay_code}")],
                    [home_btn(lang)],
                ])
            )
        except TelegramBadRequest:
            pass

    await cb.answer(
        "✅ Đã gửi thông báo thanh toán cho Admin!\n\n"
        "⏳ Vui lòng đợi trong giây lát, ngay khi Admin xác nhận tiền vào MoMo, hệ thống sẽ tự động gửi tài khoản sản phẩm cho bạn tại đây!",
        show_alert=True,
    )


async def deliver(cb: CallbackQuery, bot: Bot, user: dict, lang: str, res: dict):
    text = t(lang, "buy_ok", order_id=res["order_id"], name=esc(res["product_name"]), qty=res["quantity"],
             total=S.fmt_money(res["total_price"]), balance=S.fmt_money(res["balance"]))
    accounts = res["accounts"]
    as_file = False
    if res["status"] == "processing":
        text += t(lang, "buy_service")
    elif accounts:
        acc_html = "\n".join(f"<code>{esc(a)}</code>" for a in accounts)
        if len(accounts) <= 10 and len(acc_html) < 3000:
            text += t(lang, "buy_accounts", accounts=acc_html)
        else:
            as_file = True
            text += t(lang, "buy_file")
    text += t(lang, "buy_warranty", warranty=esc(res["warranty"] or "-"), order_id=res["order_id"])
    await show(cb, (text, kb([[btn(t(lang, "m_buy"), "u:buy", icon=await ui.menu_icon("buy"), emoji="🛒"),
                               home_btn(lang)]])))
    if as_file:
        await cb.message.answer_document(
            BufferedInputFile("\n".join(accounts).encode("utf-8"), filename=f"{res['order_id']}.txt"),
            caption=f"🧾 {res['order_id']} | {esc(res['product_name'])}")

    who = f"@{esc(user['username'])}" if user["username"] else esc(user["full_name"] or "")
    admin_text = (f"🛒 <b>ĐƠN MỚI</b> <code>{res['order_id']}</code>\n👤 {who} (<code>{user['user_id']}</code>)\n"
                  f"📦 {esc(res['product_name'])} x{res['quantity']}\n💰 {S.fmt_money(res['total_price'])}")
    if res["status"] == "processing":
        await notify.notify_admins(bot, admin_text + "\n\n⏳ <b>Đơn dịch vụ cần xử lý!</b>",
                                   notify.service_order_kb(res["order_id"]))
    else:
        await notify.notify_admins(bot, admin_text, disable_notification=True)


# ======================================================================
# HISTORY
# ======================================================================
@router.callback_query(F.data.startswith("hist:"))
async def cb_history(cb: CallbackQuery, user: dict):
    await show(cb, await render_history(user, int(cb.data[5:])))
    await cb.answer()


@router.callback_query(F.data.startswith("ord:"))
async def cb_order(cb: CallbackQuery, user: dict, lang: str):
    o = await S.get_order(cb.data[4:])
    if not o or o["user_id"] != user["user_id"]:
        return await cb.answer("❌", show_alert=True)
    text = t(lang, "order_detail", order_id=o["order_id"], name=esc(o["product_name"]), qty=o["quantity"],
             total=S.fmt_money(o["total_price"]), status=t(lang, f"status_{o['status']}"), time=o["created_at"])
    rows = []
    if o["accounts_delivered"]:
        rows.append([btn(t(lang, "btn_download"), f"dl:{o['order_id']}")])
    rows.append([btn(t(lang, "back"), "hist:0", style=None), home_btn(lang)])
    await show(cb, (text, kb(rows)))
    await cb.answer()


@router.callback_query(F.data.startswith("dl:"))
async def cb_download(cb: CallbackQuery, user: dict):
    o = await S.get_order(cb.data[3:])
    if not o or o["user_id"] != user["user_id"] or not o["accounts_delivered"]:
        return await cb.answer("❌", show_alert=True)
    await cb.message.answer_document(
        BufferedInputFile(o["accounts_delivered"].encode("utf-8"), filename=f"{o['order_id']}.txt"),
        caption=f"🧾 {o['order_id']} | {esc(o['product_name'])}")
    await cb.answer()


# ======================================================================
# WALLET
# ======================================================================
@router.callback_query(F.data == "dep:bank")
async def cb_dep_bank(cb: CallbackQuery, lang: str):
    cfg = await bank_auto.get_bank_config()
    if not cfg["account"]:
        return await cb.answer(t(lang, "bank_off"), show_alert=True)
    min_dep = cfg["min_deposit"]
    amounts = [20000, 50000, 100000, 200000, 500000, 1000000]
    amounts = [a for a in amounts if a >= min_dep]
    rows = [[btn(S.fmt_money(a), f"bq:{a}") for a in amounts[i:i + 3]] for i in range(0, len(amounts), 3)]
    rows.append([btn(t(lang, "bank_custom"), "bq:c")])
    rows.append([btn(t(lang, "back"), "u:wallet", style=None)])
    await show(cb, (t(lang, "bank_choose", min=S.fmt_money(min_dep)), kb(rows)))
    await cb.answer()


async def send_bank_qr(message: Message, user: dict, lang: str, amount: int):
    cfg = await bank_auto.get_bank_config()
    if not cfg["account"]:
        return await message.answer(t(lang, "bank_off"))
    intent = await bank_auto.create_deposit_intent(user["user_id"], amount)
    content = intent["content"]
    caption = t(lang, "bank_qr", bank=cfg["bank_id"], acc=cfg["account"], name=esc(cfg["account_name"]),
                amount=S.fmt_money(amount), content=content)
    markup = kb([
        [btn(t(lang, "bank_paid_btn"), f"bdone:{amount}:{intent['pay_code']}", style="success")],
        [home_btn(lang)],
    ])
    msg = await bank_auto.send_vietqr_photo(message, cfg, amount, content, caption, markup)
    await bank_auto.bind_intent_message(intent["pay_code"], msg.chat.id, msg.message_id)


@router.callback_query(F.data.startswith("bq:"))
async def cb_bank_amount(cb: CallbackQuery, state: FSMContext, user: dict, lang: str):
    cfg = await bank_auto.get_bank_config()
    v = cb.data[3:]
    if v == "c":
        await state.set_state(UserSG.bank_amount)
        await cb.message.answer(t(lang, "ask_amount", min=S.fmt_money(cfg["min_deposit"])))
    else:
        await send_bank_qr(cb.message, user, lang, int(v))
    await cb.answer()


@router.callback_query(F.data.startswith("bdone:"))
async def cb_bank_done(cb: CallbackQuery, bot: Bot, user: dict, lang: str):
    parts = cb.data.split(":")
    amount = int(parts[1])
    nonce = parts[2] if len(parts) > 2 else "0"
    cfg = await bank_auto.get_bank_config()

    # 1. Quét ngay lịch sử giao dịch thật từ API ngân hàng
    await bank_auto.check_bank_transactions_once(bot)
    intent = await db.fetchone("SELECT * FROM payment_intents WHERE pay_code=?", (nonce,))
    if intent and intent["status"] == "completed":
        try:
            await cb.message.edit_reply_markup(reply_markup=kb([[home_btn(lang)]]))
        except TelegramBadRequest:
            pass
        return await cb.answer("✅ Đã xác nhận giao dịch ngân hàng và cộng tiền vào Ví!")

    # 2. Gửi yêu cầu cho Admin duyệt thủ công 1-Click
    ref = f"bankreq:{user['user_id']}:{nonce}"
    method = f"{cfg['bank_id']} ({cfg['account_name']})"
    note = f"{cfg['prefix']} {user['user_id']}"
    dep_id = await S.create_pending_deposit(user["user_id"], method, amount, ref, note)
    if dep_id is not None:
        who = f"@{esc(user['username'])}" if user["username"] else esc(user["full_name"] or "")
        await notify.notify_admins(
            bot,
            f"🔔 <b>YÊU CẦU DUYỆT NẠP VÍ #{dep_id}</b>\n\n"
            f"👤 Khách hàng: {who} (<code>{user['user_id']}</code>)\n"
            f"🏛 Nhận qua: <b>{esc(cfg['bank_id'])}</b> - <b>{esc(cfg['account_name'])}</b>\n"
            f"💰 Số tiền: <b>{S.fmt_money(amount)}</b>\n"
            f"📝 Nội dung CK: <code>{esc(note)}</code>\n\n"
            f"👇 <i>Kiểm tra MoMo nhận đủ tiền rồi bấm Duyệt bên dưới để cộng số dư cho khách:</i>",
            notify.crypto_kb(dep_id),
        )
        try:
            await cb.message.edit_reply_markup(
                reply_markup=kb([
                    [btn("⏳ Đang chờ Admin xác nhận cộng tiền...", "noop")],
                    [home_btn(lang)],
                ])
            )
        except TelegramBadRequest:
            pass

    await cb.answer(
        "✅ Đã gửi yêu cầu xác nhận nạp tiền cho Admin!\n\n"
        "⏳ Số dư Ví sẽ được cộng tự động ngay khi Admin bấm Duyệt.",
        show_alert=True,
    )


def parse_amount(s: str) -> int | None:
    s = s.lower().replace(".", "").replace(",", "").replace(" ", "").replace("đ", "").replace("vnd", "")
    mult = 1
    if s.endswith("k"):
        mult, s = 1000, s[:-1]
    elif s.endswith(("tr", "m")):
        mult, s = 1_000_000, s.rstrip("trm")
    try:
        return int(float(s) * mult)
    except ValueError:
        return None


@router.message(UserSG.bank_amount, F.text)
async def st_bank_amount(message: Message, state: FSMContext, user: dict, lang: str):
    cfg = await bank_auto.get_bank_config()
    amt = parse_amount(message.text)
    if not amt or amt < cfg["min_deposit"]:
        return await message.answer(t(lang, "bad_amount"))
    await state.clear()
    await send_bank_qr(message, user, lang, amt)


@router.callback_query(F.data == "dep:crypto")
async def cb_dep_crypto(cb: CallbackQuery, lang: str):
    rows = [[btn("USDT - TRC20", "cx:trc20")], [btn("USDT - BEP20", "cx:bep20")],
            [btn("Binance Pay", "cx:binance")], [btn(t(lang, "back"), "u:wallet", style=None)]]
    await show(cb, (t(lang, "crypto_menu", rate=S.fmt_money(USDT_RATE)), kb(rows)))
    await cb.answer()


@router.callback_query(F.data.startswith("cx:"))
async def cb_crypto_net(cb: CallbackQuery, state: FSMContext, lang: str):
    net = cb.data[3:]
    rate = S.fmt_money(USDT_RATE)
    if net == "trc20":
        if not USDT_TRC20_ADDRESS:
            return await cb.answer(t(lang, "crypto_off"), show_alert=True)
        await state.set_state(UserSG.trc20_txid)
        await cb.message.answer(t(lang, "crypto_trc20", addr=USDT_TRC20_ADDRESS, rate=rate))
    else:
        addr = USDT_BEP20_ADDRESS if net == "bep20" else BINANCE_PAY_ID
        if not addr:
            return await cb.answer(t(lang, "crypto_off"), show_alert=True)
        label = "Địa chỉ ví BEP20" if net == "bep20" else "Binance Pay ID"
        await state.set_state(UserSG.crypto_amount)
        await state.update_data(net=net)
        await cb.message.answer(t(lang, "crypto_manual", net=net.upper(), label=label, addr=addr, rate=rate))
    await cb.answer()


@router.message(UserSG.trc20_txid, F.text)
async def st_trc20(message: Message, state: FSMContext, bot: Bot, user: dict, lang: str):
    txid = message.text.strip()
    ref = f"trc20:{txid.lower()}"
    if await db.fetchone("SELECT 1 FROM deposits WHERE ref=?", (ref,)):
        await state.clear()
        return await message.answer(t(lang, "tx_used"))
    wait = await message.answer(t(lang, "tx_checking"))
    usdt = await crypto.check_trc20(txid)
    if not usdt:
        return await wait.edit_text(t(lang, "tx_not_found"))
    await state.clear()
    amount = int(usdt * USDT_RATE)
    bal = await S.credit_deposit(user["user_id"], amount, f"USDT-TRC20 ({usdt:g} USDT)", ref)
    if bal is None:
        return await wait.edit_text(t(lang, "tx_used"))
    await wait.delete()
    await notify.deposit_success(bot, user["user_id"], amount, f"USDT-TRC20 ({usdt:g} USDT)", bal)


@router.message(UserSG.crypto_amount, F.text)
async def st_crypto_amount(message: Message, state: FSMContext, lang: str):
    try:
        usdt = float(message.text.strip().replace(",", "."))
        assert usdt > 0
    except (ValueError, AssertionError):
        return await message.answer(t(lang, "bad_amount"))
    await state.update_data(usdt=usdt)
    await state.set_state(UserSG.crypto_txid)
    await message.answer(t(lang, "ask_txid"))


@router.message(UserSG.crypto_txid, F.text)
async def st_crypto_txid(message: Message, state: FSMContext, bot: Bot, user: dict, lang: str):
    data = await state.get_data()
    await state.clear()
    txid = message.text.strip()[:200]
    net, usdt = data["net"], data["usdt"]
    amount = int(usdt * USDT_RATE)
    method = f"USDT-{net.upper()} ({usdt:g} USDT)"
    dep_id = await S.create_pending_deposit(user["user_id"], method, amount, f"{net}:{txid.lower()}", txid)
    if dep_id is None:
        return await message.answer(t(lang, "tx_used"))
    await message.answer(t(lang, "tx_pending"))
    who = f"@{esc(user['username'])}" if user["username"] else esc(user["full_name"] or "")
    await notify.notify_admins(
        bot, f"💎 <b>YÊU CẦU NẠP CRYPTO #{dep_id}</b>\n👤 {who} (<code>{user['user_id']}</code>)\n"
             f"🌐 Mạng: {net.upper()}\n💵 {usdt:g} USDT = <b>{S.fmt_money(amount)}</b>\n🔖 TXID: <code>{esc(txid)}</code>",
        notify.crypto_kb(dep_id))


@router.callback_query(F.data == "txh")
async def cb_txhist(cb: CallbackQuery, user: dict, lang: str):
    rows = await db.fetchall("SELECT * FROM transactions WHERE user_id=? ORDER BY trans_id DESC LIMIT 20",
                             (user["user_id"],))
    if not rows:
        text = t(lang, "txhist_empty")
    else:
        text = t(lang, "txhist_title") + "\n".join(
            f"<code>{r['created_at'][5:16]}</code> | <b>{'+' if r['amount'] > 0 else ''}{S.fmt_money(r['amount'])}</b>"
            f" | {esc(r['description'][:40])}" for r in rows)
    await show(cb, (text, kb([[btn(t(lang, "back"), "u:wallet", style=None)]])))
    await cb.answer()


# ======================================================================
# API
# ======================================================================
@router.callback_query(F.data == "api:reset")
async def cb_api_reset(cb: CallbackQuery, user: dict, lang: str):
    user["api_key"] = await S.reset_api_key(user["user_id"])
    await show(cb, await render_api(user))
    await cb.answer(t(lang, "api_reset_ok"), show_alert=True)


@router.callback_query(F.data == "api:docs")
async def cb_api_docs(cb: CallbackQuery, lang: str):
    base = f"{PUBLIC_URL}/api/v1"
    text = (
        "📖 <b>TÀI LIỆU API</b>\n\n"
        "Xác thực: header <code>X-API-Key: YOUR_KEY</code> (hoặc <code>?api_key=</code>)\n\n"
        f"1️⃣ <b>Số dư</b>\n<code>GET {base}/balance</code>\n\n"
        f"2️⃣ <b>Danh sách sản phẩm</b>\n<code>GET {base}/products</code>\n\n"
        f"3️⃣ <b>Mua hàng</b>\n<code>POST {base}/buy</code>\nBody JSON: <code>{{\"product_id\": 1, \"quantity\": 1}}</code>\n\n"
        f"4️⃣ <b>Tra cứu đơn</b>\n<code>GET {base}/order/ORDXXXXXXXX</code>\n\n"
        "Ví dụ:\n<pre>curl -X POST " + base + "/buy \\\n -H \"X-API-Key: sk_xxx\" \\\n"
        " -H \"Content-Type: application/json\" \\\n -d '{\"product_id\":1,\"quantity\":2}'</pre>\n"
        "Phản hồi: <code>{\"success\":true,\"order_id\":\"...\",\"accounts\":[\"email|pass|2fa\"]}</code>"
    )
    await show(cb, (text, kb([[btn(t(lang, "back"), "u:api", style=None)]])))
    await cb.answer()


# ======================================================================
# WARRANTY
# ======================================================================
@router.message(UserSG.w_order, F.text)
async def st_w_order(message: Message, state: FSMContext, user: dict, lang: str):
    o = await S.get_order(message.text)
    if not o or o["user_id"] != user["user_id"]:
        return await message.answer(t(lang, "warranty_bad_order"))
    if await db.fetchone("SELECT 1 FROM tickets WHERE order_id=? AND status='pending'", (o["order_id"],)):
        await state.clear()
        return await message.answer(t(lang, "warranty_dup"))
    await state.update_data(order_id=o["order_id"])
    await state.set_state(UserSG.w_reason)
    await message.answer(t(lang, "warranty_ask_reason"))


@router.message(UserSG.w_reason, F.text)
async def st_w_reason(message: Message, state: FSMContext, bot: Bot, user: dict, lang: str):
    data = await state.get_data()
    await state.clear()
    reason = message.text.strip()[:1000]
    tid = await db.execute("INSERT INTO tickets(order_id, user_id, reason) VALUES (?,?,?)",
                           (data["order_id"], user["user_id"], reason))
    await message.answer(t(lang, "warranty_sent", tid=tid))
    o = await S.get_order(data["order_id"])
    who = f"@{esc(user['username'])}" if user["username"] else esc(user["full_name"] or "")
    acc_preview = esc(o["accounts_delivered"][:800]) or "-"
    await notify.notify_admins(
        bot, f"🛡 <b>PHIẾU BẢO HÀNH #{tid}</b>\n👤 {who} (<code>{user['user_id']}</code>)\n"
             f"🧾 Đơn: <code>{o['order_id']}</code>\n📦 {esc(o['product_name'])} x{o['quantity']}\n"
             f"💰 {S.fmt_money(o['total_price'])}\n🕒 {o['created_at']}\n📝 Lý do: {esc(reason)}\n\n"
             f"<b>Acc đã giao:</b>\n<pre>{acc_preview}</pre>",
        notify.ticket_kb(tid))


# ======================================================================
# LANGUAGE
# ======================================================================
@router.callback_query(F.data.startswith("lang:"))
async def cb_lang(cb: CallbackQuery, user: dict):
    lang = cb.data[5:]
    await db.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user["user_id"]))
    user["language"] = lang
    await cb.answer(t(lang, "lang_ok"))
    await ui.answer(cb.message, t(lang, "lang_ok"), await ui.reply_menu_kb(lang))
    await show(cb, await render_main(user))
