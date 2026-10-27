"""Quản lý cấu hình Ngân hàng động, tạo ảnh VietQR trực tiếp (PNG) &
Tự động kiểm tra giao dịch / nội dung chuyển khoản để duyệt tiền hoặc giao sản phẩm tự động."""
import asyncio
import base64
import hashlib
import io
import logging
import re
import secrets
from urllib.parse import quote

import aiohttp
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile
from PIL import Image, ImageDraw

import config
import db
import notify
import services as S
from texts import t
from ui import btn, esc, kb

log = logging.getLogger(__name__)

# Danh sách ngân hàng & Ví điện tử phổ biến hỗ trợ QR
VIETQR_BANKS = [
    ("MOMO", "Ví MoMo"),
    ("MSB", "MSB Bank"),
    ("MB", "MB Bank"),
    ("VCB", "Vietcombank"),
    ("TCB", "Techcombank"),
    ("ACB", "ACB"),
    ("BIDV", "BIDV"),
    ("ICB", "VietinBank"),
    ("VPB", "VPBank"),
    ("TPB", "TPBank"),
    ("STB", "Sacombank"),
    ("VIB", "VIB"),
    ("OCB", "OCB"),
    ("SHB", "SHB"),
    ("EIB", "Eximbank"),
    ("HDB", "HDBank"),
    ("LPB", "LPBank"),
    ("SEAB", "SeABank"),
    ("CAKE", "CAKE by VPBank"),
    ("TIMO", "Timo"),
]

_B64_PNG_RE = re.compile(rb"data:image/png;base64,([A-Za-z0-9+/=\s]+)")


async def get_bank_config() -> dict:
    bank_id = await S.get_setting("bank_id", config.BANK_ID or "MSB")
    account = await S.get_setting("bank_account", config.BANK_ACCOUNT)
    account_name = await S.get_setting("bank_account_name", config.BANK_ACCOUNT_NAME)
    prefix = (await S.get_setting("deposit_prefix", config.DEPOSIT_PREFIX or "NAP")).upper()
    min_dep_raw = await S.get_setting("min_deposit", str(config.MIN_DEPOSIT))
    try:
        min_deposit = int(min_dep_raw)
    except (TypeError, ValueError):
        min_deposit = 10000

    auto_approve = await S.get_setting("bank_auto_approve", "1")
    sepay_token = await S.get_setting("sepay_token", config.SEPAY_API_KEY)
    casso_key = await S.get_setting("casso_key", config.CASSO_SECURE_TOKEN)
    web2m_url = await S.get_setting("web2m_url", "")
    webhook_key = await S.get_setting("bank_webhook_key", config.BANK_WEBHOOK_KEY)
    imap_email = await S.get_setting("imap_email", "")
    imap_pass = await S.get_setting("imap_pass", "")

    return {
        "bank_id": bank_id,
        "account": account or "",
        "account_name": account_name or "",
        "prefix": prefix,
        "min_deposit": min_deposit,
        "auto_approve": str(auto_approve) == "1",
        "sepay_token": sepay_token or "",
        "casso_key": casso_key or "",
        "web2m_url": web2m_url or "",
        "webhook_key": webhook_key or "",
        "imap_email": imap_email or "",
        "imap_pass": imap_pass or "",
    }


# ======================================================================
# TẢI & XỬ LÝ ẢNH VIETQR TRỰC TIẾP (LUÔN TRẢ VỀ PNG HỢP LỆ CHO TELEGRAM)
# ======================================================================
def _fallback_qr_card(bank_id: str, account: str, account_name: str, amount: int, content: str) -> bytes:
    img = Image.new("RGB", (540, 420), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((12, 12, 528, 408), outline=(22, 163, 74), width=4)
    lines = [
        "VIETQR THANH TOAN TU DONG",
        f"Ngan hang : {bank_id}",
        f"So TK     : {account}",
        f"Chu TK    : {account_name}",
        f"So tien   : {amount:,} VND",
        f"Noi dung  : {content}",
    ]
    y = 55
    for ln in lines:
        d.text((40, y), ln, fill=(20, 20, 20))
        y += 50
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _render_vietqr_svg_to_png(svg_bytes: bytes, account_name: str, account: str, amount: int, content: str) -> bytes | None:
    """Render đầy đủ SVG của img.vietqr.io (khung + ma trận QR + logo tâm + chữ dưới) sang ảnh PNG thật."""
    text = svg_bytes.decode("utf-8", errors="ignore")
    imgs = re.findall(r'href="data:image/(?:png|jpeg);base64,([A-Za-z0-9+/=\s]+)"', text)
    if not imgs:
        return None
    base = Image.open(io.BytesIO(base64.b64decode(imgs[0]))).convert("RGBA")
    bg = Image.new("RGBA", base.size, (255, 255, 255, 255))
    bg.alpha_composite(base)
    draw = ImageDraw.Draw(bg)

    # 1. Vẽ ma trận QR từ thẻ <g transform="translate(tx ty) scale(s)"><path d="M..."/>
    m_tr = re.search(r'transform="translate\(([\d.]+)\s+([\d.]+)\)\s*scale\(([\d.]+)\)"', text)
    m_path = re.search(r'<path[^>]*d="([^"]+)"', text)
    if m_tr and m_path:
        tx, ty, sc = float(m_tr.group(1)), float(m_tr.group(2)), float(m_tr.group(3))
        for mx, my, mw in re.findall(r"M(\d+)\s+(\d+)h(\d+)v1", m_path.group(1)):
            x0 = tx + int(mx) * sc
            y0 = ty + int(my) * sc
            x1 = x0 + int(mw) * sc
            y1 = y0 + sc
            draw.rectangle((x0, y0, x1, y1), fill=(17, 17, 17, 255))

        # 2. Vẽ logo nhỏ ở tâm QR (nếu có)
        if len(imgs) > 1:
            m_logo = re.search(
                r'<image[^>]*id="vietqr-logo"[^>]*x="([\d.]+)"[^>]*y="([\d.]+)"[^>]*width="([\d.]+)"[^>]*height="([\d.]+)"',
                text,
            )
            if m_logo:
                lx = int(round(tx + float(m_logo.group(1)) * sc))
                ly = int(round(ty + float(m_logo.group(2)) * sc))
                lw = max(1, int(round(float(m_logo.group(3)) * sc)))
                lh = max(1, int(round(float(m_logo.group(4)) * sc)))
                try:
                    logo_im = Image.open(io.BytesIO(base64.b64decode(imgs[1]))).convert("RGBA").resize((lw, lh), Image.Resampling.LANCZOS)
                    bg.paste(logo_im, (lx, ly), logo_im)
                except Exception:
                    pass

    # 3. Vẽ thông tin Chủ TK / Số TK / Số tiền / Nội dung ở chân ảnh
    try:
        from PIL import ImageFont
        font_b = ImageFont.truetype("arialbd.ttf", 17)
        font_r = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        from PIL import ImageFont
        font_b = font_r = ImageFont.load_default()

    w = bg.width
    footer = [
        (account_name, 552, font_b, (50, 50, 50, 255)),
        (f"STK: {account}", 576, font_r, (70, 70, 70, 255)),
        (f"So tien: {amount:,} VND  |  ND: {content}".replace(",", "."), 600, font_b, (20, 120, 50, 255)),
    ]
    for line, y, fnt, color in footer:
        bbox = draw.textbbox((0, 0), line, font=fnt)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) / 2, y), line, font=fnt, fill=color)

    out = io.BytesIO()
    bg.convert("RGB").save(out, format="PNG")
    return out.getvalue()


def _crc16_ccitt(data: bytes) -> str:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = (((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)) & 0xFFFF
    return f"{crc:04X}"


def _build_momo_vietqr_payload(amount: int, content: str) -> str:
    """Tạo chuỗi EMVCo VietQR Napas247 động từ mã MoMo gốc của chủ shop,
    tự động gắn sẵn Số tiền (Tag 54) và Nội dung chuyển khoản (Subtag 08 trong Tag 62)."""
    amt_str = str(int(amount)) if amount and amount > 0 else ""
    tag54 = f"54{len(amt_str):02d}{amt_str}" if amt_str else ""
    clean_content = "".join(ch for ch in (content or "") if ch.isalnum() or ch == " ").strip()
    sub08 = f"08{len(clean_content):02d}{clean_content}" if clean_content else ""
    inner62 = f"0515MOMOW2W858022180622UKPF-n8bhJJfriRMhRvq9w{sub08}"
    tag62 = f"62{len(inner62):02d}{inner62}"
    body = (
        "000201"
        + ("010212" if tag54 else "010211")
        + "38630010A000000727013300069710250119PSP26108187000001100208QRIBFTTA"
        + "5303704"
        + tag54
        + "5802VN"
        + tag62
        + "6304"
    )
    return body + _crc16_ccitt(body.encode("ascii"))


async def fetch_vietqr_png(bank_id: str, account: str, account_name: str, amount: int, content: str) -> bytes:
    """Trả về đúng khung ảnh QR đã cắt gọn (momo_qr.jpg) không hiện tên/STK/số tiền dạng chữ,
    nhưng bên trong mã QR tự động mã hóa sẵn đúng Số tiền mua hàng / Số tiền nạp và Nội dung CK."""
    import os
    import qrcode

    momo_img_path = os.path.join(config.BASE_DIR, "momo_qr.jpg")
    if os.path.exists(momo_img_path):
        try:
            base = Image.open(momo_img_path).convert("RGBA")
            r_badge = 33
            cx, cy = 290, 251
            badge = base.crop((cx - r_badge, cy - r_badge, cx + r_badge, cy + r_badge))
            mask = Image.new("L", (r_badge * 2, r_badge * 2), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, r_badge * 2, r_badge * 2), fill=255)

            payload = _build_momo_vietqr_payload(amount, content)
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=0,
            )
            qr.add_data(payload)
            qr.make(fit=True)
            qr_im = (
                qr.make_image(fill_color="black", back_color="white")
                .convert("RGBA")
                .resize((289, 289), Image.Resampling.NEAREST)
            )

            out_im = base.copy()
            ImageDraw.Draw(out_im).rectangle((144, 105, 436, 397), fill=(255, 255, 255, 255))
            out_im.paste(qr_im, (146, 107))
            out_im.paste(badge, (cx - r_badge, cy - r_badge), mask)

            buf = io.BytesIO()
            out_im.convert("RGB").save(buf, format="PNG")
            return buf.getvalue()
        except Exception as e:
            log.warning("Dynamic momo_qr render error: %s", e)
            with open(momo_img_path, "rb") as f:
                return f.read()

    if bank_id.upper() == "MOMO":
        # Chuẩn chuỗi QR nhận tiền của Ví MoMo (điền sẵn Số tiền + Lời nhắn)
        momo_qr_data = f"2|99|{account}|{account_name}||0|0|{amount}|{content}|transfer_myqr"
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=360x360&margin=10&data={quote(momo_qr_data)}"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(qr_url, timeout=aiohttp.ClientTimeout(total=12)) as r:
                    if r.status == 200:
                        qr_im = Image.open(io.BytesIO(await r.read())).convert("RGB")
                        card = Image.new("RGB", (540, 640), (255, 255, 255))
                        d = ImageDraw.Draw(card)
                        d.rounded_rectangle((20, 20, 520, 620), radius=24, outline=(165, 0, 100), width=4)
                        d.rectangle((20, 20, 520, 95), fill=(165, 0, 100))
                        try:
                            from PIL import ImageFont
                            f_title = ImageFont.truetype("arialbd.ttf", 26)
                            f_b = ImageFont.truetype("arialbd.ttf", 18)
                            f_r = ImageFont.truetype("arial.ttf", 17)
                        except Exception:
                            from PIL import ImageFont
                            f_title = f_b = f_r = ImageFont.load_default()
                        d.text((140, 42), "VI DIEN TU MOMO", font=f_title, fill=(255, 255, 255))
                        card.paste(qr_im.resize((360, 360)), (90, 125))
                        footer = [
                            (account_name, 505, f_b, (40, 40, 40)),
                            (f"SDT MoMo: {account}", 535, f_r, (70, 70, 70)),
                            (f"So tien: {amount:,} VND".replace(",", "."), 565, f_b, (165, 0, 100)),
                            (f"Loi nhan: {content}", 592, f_b, (20, 120, 50)),
                        ]
                        for line, y, fnt, col in footer:
                            bb = d.textbbox((0, 0), line, font=fnt)
                            d.text(((540 - (bb[2] - bb[0])) / 2, y), line, font=fnt, fill=col)
                        out = io.BytesIO()
                        card.save(out, format="PNG")
                        return out.getvalue()
        except Exception as e:
            log.warning("MoMo QR render error: %s", e)

    url = (
        f"https://img.vietqr.io/image/{bank_id}-{account}-compact2.png"
        f"?amount={amount}&addInfo={quote(content)}&accountName={quote(account_name)}"
    )
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=aiohttp.ClientTimeout(total=12),
            ) as r:
                if r.status == 200:
                    raw = await r.read()
                    if b"<svg" in raw[:200]:
                        png = _render_vietqr_svg_to_png(raw, account_name, account, amount, content)
                        if png:
                            return png
                    else:
                        im = Image.open(io.BytesIO(raw)).convert("RGB")
                        out = io.BytesIO()
                        im.save(out, format="PNG")
                        return out.getvalue()
        except Exception as e:
            log.warning("fetch_vietqr_png primary (%s): %s", url, e)

        try:
            # Dự phòng qua cổng PNG trực tiếp của SePay QR
            u2 = f"https://qr.sepay.vn/img?acc={quote(account)}&bank={quote(bank_id)}&amount={amount}&des={quote(content)}&template=compact"
            async with s.get(u2, timeout=aiohttp.ClientTimeout(total=12)) as r2:
                if r2.status == 200:
                    raw2 = await r2.read()
                    im2 = Image.open(io.BytesIO(raw2)).convert("RGB")
                    out2 = io.BytesIO()
                    im2.save(out2, format="PNG")
                    return out2.getvalue()
        except Exception as e2:
            log.warning("fetch_vietqr_png sepay fallback: %s", e2)
    return _fallback_qr_card(bank_id, account, account_name, amount, content)


async def send_vietqr_photo(target_message, cfg: dict, amount: int, content: str, caption: str, markup=None):
    """Luôn tải và upload file ảnh VietQR trực tiếp lên Telegram (không bao giờ gửi link)."""
    png = await fetch_vietqr_png(cfg["bank_id"], cfg["account"], cfg["account_name"], amount, content)
    photo_file = BufferedInputFile(png, filename=f"vietqr_{content.replace(' ', '_')}.png")
    return await target_message.answer_photo(photo_file, caption=caption, reply_markup=markup)


# ======================================================================
# QUẢN LÝ PHIÊN THANH TOÁN QR (PAYMENT INTENTS) & TỰ ĐỘNG GIAO HÀNG
# ======================================================================
async def create_order_intent(uid: int, pid: int, qty: int, amount: int) -> dict:
    """Tạo mã thanh toán QR trực tiếp cho đơn hàng sản phẩm."""
    for _ in range(10):
        code = "DH" + "".join(secrets.choice("0123456789") for _ in range(6))
        exist = await db.fetchone("SELECT 1 FROM payment_intents WHERE pay_code=?", (code,))
        if not exist:
            break
    cfg = await get_bank_config()
    content = f"{cfg['prefix']} {code}"
    await db.execute(
        """INSERT INTO payment_intents(pay_code, user_id, intent_type, product_id, quantity, amount, content, status)
           VALUES (?,?,?,?,?,?,?,'pending')""",
        (code, uid, "order", pid, qty, amount, content),
    )
    return await db.fetchone("SELECT * FROM payment_intents WHERE pay_code=?", (code,))


async def create_deposit_intent(uid: int, amount: int) -> dict:
    """Tạo mã thanh toán QR cho nạp Ví."""
    for _ in range(10):
        code = "NP" + "".join(secrets.choice("0123456789") for _ in range(6))
        exist = await db.fetchone("SELECT 1 FROM payment_intents WHERE pay_code=?", (code,))
        if not exist:
            break
    cfg = await get_bank_config()
    content = f"{cfg['prefix']} {uid}"
    await db.execute(
        """INSERT INTO payment_intents(pay_code, user_id, intent_type, amount, content, status)
           VALUES (?,?,?,?,?,'pending')""",
        (code, uid, "deposit", amount, content),
    )
    return await db.fetchone("SELECT * FROM payment_intents WHERE pay_code=?", (code,))


async def bind_intent_message(pay_code: str, chat_id: int, message_id: int):
    await db.execute(
        "UPDATE payment_intents SET chat_id=?, message_id=? WHERE pay_code=?",
        (chat_id, message_id, pay_code),
    )


async def deliver_direct_order(bot, intent: dict, tx_ref: str, gateway: str) -> tuple[bool, str]:
    """Duyệt phiên thanh toán QR sản phẩm -> Cộng tiền -> Xuất kho -> Gửi sản phẩm tự động cho User."""
    pay_code = intent["pay_code"]
    uid = intent["user_id"]
    pid = intent["product_id"]
    qty = intent["quantity"]
    amount = intent["amount"]

    # 1. Đánh dấu hoàn thành intent + cộng tiền nạp tương ứng (chống trùng theo tx_ref / pay_code)
    bal = await S.credit_deposit(
        uid, amount, f"QR Trực tiếp ({gateway})", f"qr:{pay_code}:{tx_ref}", intent["content"]
    )
    if bal is None:
        return False, "already_processed"
    await db.execute(
        "UPDATE payment_intents SET status='completed', tx_ref=? WHERE pay_code=?",
        (tx_ref, pay_code),
    )

    # 2. Cập nhật nút trên tin nhắn ảnh QR cũ (nếu có)
    if intent.get("chat_id") and intent.get("message_id"):
        try:
            await bot.edit_message_reply_markup(
                chat_id=intent["chat_id"],
                message_id=intent["message_id"],
                reply_markup=kb([[btn("✅ Đã thanh toán & Giao hàng", "noop", style="success")]]),
            )
        except TelegramBadRequest:
            pass

    user = await S.get_user(uid)
    lang = user["language"] if user else "vi"

    # 3. Thực hiện mua & xuất kho tự động
    try:
        res = await S.purchase(uid, pid, qty, source="qr_direct")
    except S.ShopError as e:
        # Nếu kho vừa hết trong lúc khách chuyển khoản -> Tiền đã nằm sẵn trong Ví của khách
        await notify.notify_user(
            bot,
            uid,
            f"✅ Đã nhận thanh toán <b>{S.fmt_money(amount)}</b> cho mã <code>{pay_code}</code>!\n"
            f"⚠️ Tuy nhiên sản phẩm vừa hết hàng ({e.code}), số tiền <b>{S.fmt_money(amount)}</b> đã được cộng vào <b>👛 Ví</b> của bạn.\n"
            f"👛 Số dư hiện tại: <b>{S.fmt_money(bal)}</b>",
            kb([[btn(t(lang, "m_buy"), "u:buy", emoji="🛒"), btn(t(lang, "home"), "u:menu", style=None)]]),
        )
        return True, "credited_to_wallet"

    # 4. Gửi tài khoản sản phẩm tự động cho khách
    text = (
        f"🎉 <b>THANH TOÁN QR THÀNH CÔNG — ĐÃ GIAO HÀNG!</b>\n\n"
        f"🔖 Mã thanh toán: <code>{pay_code}</code>\n"
        f"🧾 Mã đơn hàng: <code>{res['order_id']}</code>\n"
        f"📦 Sản phẩm: <b>{esc(res['product_name'])}</b>\n"
        f"🔢 Số lượng: {res['quantity']}\n"
        f"💰 Đã thanh toán: <b>{S.fmt_money(res['total_price'])}</b>\n"
        f"👛 Số dư Ví: {S.fmt_money(res['balance'])}"
    )
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

    await notify.notify_user(
        bot,
        uid,
        text,
        kb([[btn(t(lang, "m_buy"), "u:buy", emoji="🛒"), btn(t(lang, "home"), "u:menu", style=None)]]),
    )
    if as_file:
        try:
            await bot.send_document(
                uid,
                BufferedInputFile("\n".join(accounts).encode("utf-8"), filename=f"{res['order_id']}.txt"),
                caption=f"🧾 {res['order_id']} | {esc(res['product_name'])}",
            )
        except Exception as e:
            log.warning("send_document order %s error: %s", res["order_id"], e)

    who = f"@{esc(user['username'])}" if user and user["username"] else esc((user or {}).get("full_name") or "")
    admin_text = (
        f"🏦 <b>ĐƠN MUA TRỰC TIẾP QUA QR</b> <code>{res['order_id']}</code>\n"
        f"🔖 Mã QR: <code>{pay_code}</code> ({gateway})\n"
        f"👤 {who} (<code>{uid}</code>)\n"
        f"📦 {esc(res['product_name'])} x{res['quantity']}\n"
        f"💰 {S.fmt_money(res['total_price'])}"
    )
    if res["status"] == "processing":
        await notify.notify_admins(
            bot,
            admin_text + "\n\n⏳ <b>Đơn dịch vụ cần xử lý!</b>",
            notify.service_order_kb(res["order_id"]),
        )
    else:
        await notify.notify_admins(bot, admin_text)

    return True, res["order_id"]


# ======================================================================
# PHÂN TÍCH NỘI DUNG CHUYỂN KHOẢN & TỰ ĐỘNG DUYỆT TIỀN / GIAO SẢN PHẨM
# ======================================================================
def extract_uid(content: str, prefix: str = "NAP") -> int | None:
    if not content:
        return None
    m = re.search(rf"\b{re.escape(prefix)}\s*(\d{{5,15}})\b", content, re.I)
    if m:
        return int(m.group(1))
    m2 = re.search(rf"{re.escape(prefix)}(\d{{5,15}})", content, re.I)
    return int(m2.group(1)) if m2 else None


def extract_pay_code(content: str) -> str | None:
    if not content:
        return None
    m = re.search(r"\b((?:DH|NP)\d{6})\b", content, re.I)
    if m:
        return m.group(1).upper()
    m2 = re.search(r"((?:DH|NP)\d{6})", content, re.I)
    return m2.group(1).upper() if m2 else None


async def process_bank_tx(bot, tx_ref: str, amount: int, content: str, gateway: str) -> bool:
    """Xử lý 1 giao dịch ngân hàng:
    1. Kiểm tra mã đơn thanh toán trực tiếp `DHxxxxxx` hoặc mã nạp `NPxxxxxx` trong nội dung CK.
    2. Kiểm tra nội dung `NAP [UID]`. Nếu UID đó đang có đơn QR trực tiếp chờ cùng số tiền thì giao hàng luôn,
       ngược lại tự động cộng tiền vào Ví cho User.
    """
    cfg = await get_bank_config()
    if amount <= 0:
        return False

    # 1. Tìm theo mã pay_code (DHxxxxxx / NPxxxxxx) trong nội dung chuyển khoản
    code = extract_pay_code(content)
    if code:
        intent = await db.fetchone(
            "SELECT * FROM payment_intents WHERE pay_code=? AND status='pending'", (code,)
        )
        if intent:
            if intent["intent_type"] == "order" and amount >= intent["amount"]:
                ok, _ = await deliver_direct_order(bot, intent, tx_ref, gateway)
                return ok
            if intent["intent_type"] == "deposit" and amount >= cfg["min_deposit"]:
                await db.execute(
                    "UPDATE payment_intents SET status='completed', tx_ref=? WHERE pay_code=?",
                    (tx_ref, code),
                )
                bal = await S.credit_deposit(
                    intent["user_id"], amount, f"Bank ({gateway})", f"{gateway}:{tx_ref}", content
                )
                if bal is not None:
                    await notify.deposit_success(bot, intent["user_id"], amount, f"Ngân hàng ({gateway})", bal)
                    return True

    # 2. Tìm theo nội dung NAP [UID]
    uid = extract_uid(content, cfg["prefix"])
    if uid:
        # Nếu khách chuyển nội dung NAP [UID] nhưng đang có đơn mua trực tiếp chờ đúng số tiền đó -> ưu tiên giao đơn
        pending_order = await db.fetchone(
            """SELECT * FROM payment_intents
               WHERE user_id=? AND intent_type='order' AND status='pending' AND amount<=?
               ORDER BY created_at DESC LIMIT 1""",
            (uid, amount),
        )
        if pending_order:
            ok, _ = await deliver_direct_order(bot, pending_order, tx_ref, gateway)
            if ok:
                return True

        if amount < cfg["min_deposit"]:
            return False
        bal = await S.credit_deposit(uid, amount, f"Bank ({gateway})", f"{gateway}:{tx_ref}", content)
        if bal is None:
            return False
        await db.execute(
            "UPDATE payment_intents SET status='completed', tx_ref=? WHERE user_id=? AND intent_type='deposit' AND status='pending'",
            (tx_ref, uid),
        )
        await notify.deposit_success(bot, uid, amount, f"Ngân hàng ({gateway})", bal)
        return True

    return False


# ======================================================================
# QUÉT GIAO DỊCH TỰ ĐỘNG TỪ CÁC CỔNG API NGÂN HÀNG
# ======================================================================
async def _poll_sepay(session: aiohttp.ClientSession, bot, token: str) -> int:
    url = "https://my.sepay.vn/userapi/transactions/list?limit=25"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as r:
        if r.status != 200:
            return 0
        data = await r.json()
    txs = data.get("transactions") or []
    credited = 0
    for tx in txs:
        amt_in = float(tx.get("amount_in") or 0)
        if amt_in <= 0:
            continue
        content = f"{tx.get('transaction_content', '')} {tx.get('reference_number', '')}"
        tx_id = str(tx.get("id") or tx.get("reference_number") or "")
        if tx_id and await process_bank_tx(bot, tx_id, int(amt_in), content, "SePay"):
            credited += 1
    return credited


async def _poll_casso(session: aiohttp.ClientSession, bot, api_key: str) -> int:
    url = "https://oauth.casso.vn/v2/transactions?pageSize=25&sort=DESC"
    headers = {"Authorization": f"Apikey {api_key}", "Content-Type": "application/json"}
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as r:
        if r.status != 200:
            return 0
        data = await r.json()
    records = ((data.get("data") or {}).get("records")) or []
    credited = 0
    for tx in records:
        amt = int(tx.get("amount") or 0)
        if amt <= 0:
            continue
        content = str(tx.get("description") or "")
        tx_id = str(tx.get("id") or tx.get("tid") or "")
        if tx_id and await process_bank_tx(bot, tx_id, amt, content, "Casso"):
            credited += 1
    return credited


async def _poll_web2m(session: aiohttp.ClientSession, bot, url: str) -> int:
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
        if r.status != 200:
            return 0
        data = await r.json(content_type=None)
    txs = (
        data.get("transactions")
        or data.get("data")
        or (data if isinstance(data, list) else [])
    )
    credited = 0
    for tx in txs:
        if not isinstance(tx, dict):
            continue
        ttype = str(tx.get("type") or tx.get("CD") or "IN").upper()
        if ttype not in ("IN", "+", "CREDIT", "C"):
            continue
        raw_amt = str(tx.get("amount") or tx.get("creditAmount") or "0")
        raw_amt = re.sub(r"[^\d]", "", raw_amt.split(".")[0])
        amt = int(raw_amt) if raw_amt.isdigit() else 0
        if amt <= 0:
            continue
        content = f"{tx.get('description', '')} {tx.get('content', '')} {tx.get('addDescription', '')}"
        tx_id = str(
            tx.get("transactionID")
            or tx.get("id")
            or tx.get("refNo")
            or hashlib.sha1(f"{amt}:{content}".encode()).hexdigest()[:16]
        )
        if await process_bank_tx(bot, tx_id, amt, content, "AutoBank"):
            credited += 1
    return credited


def parse_free_text_notification(text: str) -> tuple[int, str] | None:
    """Bóc tách (số tiền, nội dung) từ tin nhắn thông báo MoMo / App Ngân hàng / Email."""
    if not text:
        return None
    # Tìm số tiền dạng +45.000đ, 45,000 VND, 45.000d, 150000 VND...
    m_amt = re.search(
        r"(?:\+|\bnhận\s+được\s+|\bsố\s+tiền[:\s]+|\bamount[:\s]+|\bgd[:\s]*\+?)?\s*(\d{1,3}(?:[.,]\d{3})+|\d{4,9})\s*(?:đ|d|vnđ|vnd)\b",
        text,
        re.I,
    )
    if not m_amt:
        return None
    raw_num = re.sub(r"[^\d]", "", m_amt.group(1))
    amount = int(raw_num) if raw_num.isdigit() else 0
    if amount <= 0:
        return None
    return amount, text


def _fetch_imap_emails_sync(email_user: str, email_pass: str) -> list[tuple[str, str]]:
    """Đọc các email thông báo biến động số dư (MoMo / MSB / Ngân hàng) chưa đọc trong Gmail."""
    import email
    from email.header import decode_header
    import imaplib

    results = []
    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        mail.login(email_user, email_pass.replace(" ", ""))
        mail.select("INBOX")
        status, messages = mail.search(None, '(UNSEEN)')
        if status != "OK" or not messages or not messages[0]:
            return results
        msg_ids = messages[0].split()[-15:]
        for mid in msg_ids:
            st, msg_data = mail.fetch(mid, "(RFC822)")
            if st != "OK":
                continue
            for part_item in msg_data:
                if not isinstance(part_item, tuple):
                    continue
                msg = email.message_from_bytes(part_item[1])
                subj = ""
                for s_part, enc in decode_header(msg.get("Subject", "")):
                    if isinstance(s_part, bytes):
                        subj += s_part.decode(enc or "utf-8", errors="ignore")
                    else:
                        subj += str(s_part)
                body = ""
                if msg.is_multipart():
                    for p in msg.walk():
                        ctype = p.get_content_type()
                        if ctype in ("text/plain", "text/html"):
                            payload = p.get_payload(decode=True)
                            if payload:
                                body += " " + payload.decode(p.get_content_charset() or "utf-8", errors="ignore")
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")
                clean_body = re.sub(r"<[^>]+>", " ", f"{subj} {body}")
                clean_body = re.sub(r"\s+", " ", clean_body)
                msg_uid = msg.get("Message-ID") or mid.decode()
                results.append((hashlib.sha1(msg_uid.encode()).hexdigest()[:16], clean_body))
    finally:
        try:
            mail.logout()
        except Exception:
            pass
    return results


async def _poll_imap_gmail(bot, email_user: str, email_pass: str) -> int:
    emails = await asyncio.to_thread(_fetch_imap_emails_sync, email_user, email_pass)
    credited = 0
    for msg_id, full_text in emails:
        parsed = parse_free_text_notification(full_text)
        if not parsed:
            continue
        amt, content = parsed
        if await process_bank_tx(bot, f"mail_{msg_id}", amt, content, "Email-Auto"):
            credited += 1
    return credited


async def check_bank_transactions_once(bot) -> int:
    """Quét 1 lượt tất cả các cổng API ngân hàng / Gmail đã cấu hình."""
    cfg = await get_bank_config()
    if not (cfg["sepay_token"] or cfg["casso_key"] or cfg["web2m_url"] or (cfg["imap_email"] and cfg["imap_pass"])):
        return 0
    total = 0
    if cfg["imap_email"] and cfg["imap_pass"]:
        try:
            total += await _poll_imap_gmail(bot, cfg["imap_email"], cfg["imap_pass"])
        except Exception as e:
            log.debug("IMAP Gmail poll error: %s", e)

    if cfg["sepay_token"] or cfg["casso_key"] or cfg["web2m_url"]:
        async with aiohttp.ClientSession() as session:
            if cfg["sepay_token"]:
                try:
                    total += await _poll_sepay(session, bot, cfg["sepay_token"])
                except Exception as e:
                    log.debug("SePay poll error: %s", e)
            if cfg["casso_key"]:
                try:
                    total += await _poll_casso(session, bot, cfg["casso_key"])
                except Exception as e:
                    log.debug("Casso poll error: %s", e)
            if cfg["web2m_url"]:
                try:
                    total += await _poll_web2m(session, bot, cfg["web2m_url"])
                except Exception as e:
                    log.debug("Web2M poll error: %s", e)
    return total


async def _poller_loop(bot):
    log.info("Auto-Bank background poller started (interval=8s)")
    while True:
        try:
            await check_bank_transactions_once(bot)
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.warning("Bank poller loop error: %s", e)
        await asyncio.sleep(8)


def start_bank_poller(bot) -> asyncio.Task:
    return asyncio.create_task(_poller_loop(bot))
