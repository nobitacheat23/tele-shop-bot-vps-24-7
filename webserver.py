"""HTTP Server (aiohttp):
1. Webhook nạp ngân hàng tự động (SePay / Casso / Web2M):
   - POST /webhook/sepay
   - POST /webhook/casso
   - POST /webhook/bank
2. REST API cho khách đấu nối tự động:
   - GET  /api/v1/balance
   - GET  /api/v1/products
   - POST /api/v1/buy
   - GET  /api/v1/order/{order_id}
"""
import hashlib
import logging

from aiohttp import web

import bank_auto
import notify
import services as S
from config import WEB_HOST, WEB_PORT

log = logging.getLogger(__name__)


# ======================================================================
# WEBHOOKS NẠP NGÂN HÀNG
# ======================================================================
async def wh_sepay(req: web.Request) -> web.Response:
    cfg = await bank_auto.get_bank_config()
    if cfg["sepay_token"]:
        auth = req.headers.get("Authorization", "")
        if auth not in (f"Apikey {cfg['sepay_token']}", f"Bearer {cfg['sepay_token']}") and req.query.get("key") != cfg["sepay_token"]:
            return web.json_response({"success": False, "error": "unauthorized"}, status=401)
    try:
        data = await req.json()
    except Exception:
        return web.json_response({"success": False, "error": "invalid_json"}, status=400)

    if str(data.get("transferType", "in")).lower() != "in":
        return web.json_response({"success": True, "ignored": True})

    amount = int(data.get("transferAmount") or data.get("amount") or 0)
    content = f"{data.get('content', '')} {data.get('description', '')}"
    tx_id = str(data.get("id") or data.get("referenceCode") or hashlib.sha1(content.encode()).hexdigest()[:16])
    credited = await bank_auto.process_bank_tx(req.app["bot"], tx_id, amount, content, "SePay")
    return web.json_response({"success": True, "credited": credited})


async def wh_casso(req: web.Request) -> web.Response:
    cfg = await bank_auto.get_bank_config()
    if cfg["casso_key"]:
        token = req.headers.get("secure-token", "") or req.query.get("key", "")
        if token != cfg["casso_key"]:
            return web.json_response({"error": 401, "message": "unauthorized"}, status=401)
    try:
        payload = await req.json()
    except Exception:
        return web.json_response({"error": 400}, status=400)

    items = payload.get("data") or []
    if isinstance(items, dict):
        items = [items]
    count = 0
    for item in items:
        amount = int(item.get("amount") or 0)
        content = str(item.get("description") or "")
        tx_id = str(item.get("id") or item.get("tid") or "")
        if amount > 0 and tx_id:
            if await bank_auto.process_bank_tx(req.app["bot"], tx_id, amount, content, "Casso"):
                count += 1
    return web.json_response({"error": 0, "credited": count})


async def wh_bank_generic(req: web.Request) -> web.Response:
    """Webhook tổng quát cho Web2M / tự bắn: hỗ trợ cả danh sách transactions hoặc 1 object."""
    cfg = await bank_auto.get_bank_config()
    if cfg["webhook_key"]:
        key = req.headers.get("X-Webhook-Key") or req.headers.get("Authorization", "").removeprefix("Bearer ").strip() or req.query.get("key")
        if key != cfg["webhook_key"]:
            return web.json_response({"status": False, "msg": "unauthorized"}, status=401)
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"status": False, "msg": "invalid_json"}, status=400)

    txs = body.get("transactions") if isinstance(body, dict) and "transactions" in body else [body]
    count = 0
    for tx in txs:
        if not isinstance(tx, dict):
            continue
        if str(tx.get("type", "IN")).upper() not in ("IN", "CREDIT", "+"):
            continue
        raw_amt = str(tx.get("amount") or tx.get("transferAmount") or "0").replace(",", "").replace(".", "")
        amount = int(raw_amt) if raw_amt.isdigit() else 0
        content = str(tx.get("description") or tx.get("content") or "")
        tx_id = str(tx.get("transactionID") or tx.get("id") or tx.get("ref") or "")
        if amount > 0 and tx_id:
            if await bank_auto.process_bank_tx(req.app["bot"], tx_id, amount, content, "Bank"):
                count += 1
    return web.json_response({"status": True, "credited": count})


async def wh_notify(req: web.Request) -> web.Response:
    """Webhook nhận thông báo đẩy từ điện thoại (App Notification Forwarder / SMS Forwarder / MacroDroid)
    dành cho MoMo, MSB và mọi ngân hàng."""
    cfg = await bank_auto.get_bank_config()
    if cfg["webhook_key"]:
        key = req.headers.get("X-Webhook-Key") or req.query.get("key") or ""
        if key != cfg["webhook_key"]:
            return web.json_response({"status": False, "msg": "unauthorized"}, status=401)
    raw_text = await req.text()
    try:
        import json
        data = json.loads(raw_text)
        if isinstance(data, dict):
            raw_text = " ".join(str(v) for v in data.values() if v)
    except Exception:
        pass
    amount, content = bank_auto.parse_free_text_notification(raw_text)
    if amount <= 0:
        return web.json_response({"status": False, "msg": "no_amount_detected", "raw": raw_text[:200]})
    tx_id = "NTF_" + hashlib.sha1(raw_text.encode("utf-8", errors="ignore")).hexdigest()[:14]
    credited = await bank_auto.process_bank_tx(req.app["bot"], tx_id, amount, content, "Phone-Notify")
    return web.json_response({"status": True, "credited": credited, "amount": amount})


# ======================================================================
# REST API CHO KHÁCH HÀNG ĐẤU NỐI
# ======================================================================
async def _auth_api_user(req: web.Request):
    key = (
        req.headers.get("X-API-Key")
        or req.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        or req.query.get("api_key")
        or ""
    ).strip()
    user = await S.get_user_by_api_key(key)
    if not user:
        raise web.HTTPUnauthorized(
            text='{"success":false,"error":"invalid_api_key"}',
            content_type="application/json",
        )
    if user["is_banned"]:
        raise web.HTTPForbidden(
            text='{"success":false,"error":"user_banned"}',
            content_type="application/json",
        )
    if S.rate_limited(user["user_id"], user["api_rate_limit"]):
        raise web.HTTPTooManyRequests(
            text='{"success":false,"error":"rate_limit_exceeded"}',
            content_type="application/json",
        )
    return user


async def api_balance(req: web.Request) -> web.Response:
    u = await _auth_api_user(req)
    return web.json_response({
        "success": True,
        "user_id": u["user_id"],
        "username": u["username"],
        "balance": u["balance"],
        "role": u["role"],
        "discount_rate": u["discount_rate"],
    })


async def api_products(req: web.Request) -> web.Response:
    u = await _auth_api_user(req)
    prods = await S.list_products()
    return web.json_response({
        "success": True,
        "products": [
            {
                "id": p["id"],
                "category_id": p["category_id"],
                "category_name": p["cat_name"],
                "name": p["name"],
                "price": S.unit_price(u, p),
                "original_price": p["price"],
                "stock": -1 if p["is_infinite_stock"] else p["stock"],
                "is_infinite_stock": bool(p["is_infinite_stock"]),
                "warranty": p["warranty_info"],
            }
            for p in prods
        ],
    })


async def api_buy(req: web.Request) -> web.Response:
    u = await _auth_api_user(req)
    try:
        data = await req.json()
    except Exception:
        data = dict(req.query)
    try:
        pid = int(data.get("product_id") or 0)
        qty = int(data.get("quantity") or 1)
    except ValueError:
        return web.json_response({"success": False, "error": "invalid_params"}, status=400)

    try:
        res = await S.purchase(u["user_id"], pid, qty, source="api")
    except S.ShopError as e:
        return web.json_response({"success": False, "error": e.code, **e.info}, status=400)

    bot = req.app["bot"]
    await notify.notify_admins(
        bot,
        f"🔌 <b>ĐƠN QUA API</b> <code>{res['order_id']}</code>\n"
        f"👤 <code>{u['user_id']}</code> (@{u['username'] or '-'})\n"
        f"📦 {res['product_name']} x{res['quantity']}\n"
        f"💰 {S.fmt_money(res['total_price'])}",
        disable_notification=True,
    )
    return web.json_response({
        "success": True,
        "order_id": res["order_id"],
        "product_id": res["product_id"],
        "product_name": res["product_name"],
        "quantity": res["quantity"],
        "unit_price": res["unit_price"],
        "total_price": res["total_price"],
        "balance_remaining": res["balance"],
        "status": res["status"],
        "accounts": res["accounts"],
    })


async def api_order(req: web.Request) -> web.Response:
    u = await _auth_api_user(req)
    oid = req.match_info.get("order_id", "")
    o = await S.get_order(oid)
    if not o or o["user_id"] != u["user_id"]:
        return web.json_response({"success": False, "error": "order_not_found"}, status=404)
    return web.json_response({
        "success": True,
        "order_id": o["order_id"],
        "product_id": o["product_id"],
        "product_name": o["product_name"],
        "quantity": o["quantity"],
        "total_price": o["total_price"],
        "status": o["status"],
        "created_at": o["created_at"],
        "accounts": [x for x in o["accounts_delivered"].split("\n") if x],
    })


async def health(req: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "TÀI NGUYÊN MMO BOT 24/7"})


async def _keep_alive_loop():
    """Tự động ping URL Cloud VPS mỗi 5 phút để giữ container luôn thức 24/7."""
    import asyncio
    import os
    import aiohttp

    url = os.getenv("SPACE_PUBLIC_URL") or os.getenv("PUBLIC_URL") or ""
    if not url or "localhost" in url:
        return
    await asyncio.sleep(30)
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    await r.read()
        except Exception:
            pass
        await asyncio.sleep(240)


async def start_webserver(bot) -> web.AppRunner:
    import asyncio

    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/", health)
    app.router.add_post("/webhook/sepay", wh_sepay)
    app.router.add_post("/webhook/casso", wh_casso)
    app.router.add_post("/webhook/bank", wh_bank_generic)
    app.router.add_post("/webhook/notify", wh_notify)
    app.router.add_get("/api/v1/balance", api_balance)
    app.router.add_get("/api/v1/products", api_products)
    app.router.add_post("/api/v1/buy", api_buy)
    app.router.add_get("/api/v1/order/{order_id}", api_order)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_HOST, WEB_PORT)
    await site.start()
    asyncio.create_task(_keep_alive_loop())
    log.info("Web server listening on http://%s:%s", WEB_HOST, WEB_PORT)
    return runner
