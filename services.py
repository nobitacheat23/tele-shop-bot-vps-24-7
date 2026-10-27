"""Business logic dùng chung cho Bot + Web API."""
import secrets
import string
import time

import db
from config import RESELLER_DEFAULT_DISCOUNT


class ShopError(Exception):
    def __init__(self, code: str, **info):
        super().__init__(code)
        self.code = code
        self.info = info


# ---------------- formatting ----------------
def fmt_money(v) -> str:
    return f"{int(v):,}".replace(",", ".") + "đ"


def fmt_k(v) -> str:
    v = int(v)
    if v >= 1_000_000:
        s = f"{v / 1_000_000:.2f}".rstrip("0").rstrip(".")
        return f"{s}tr"
    if v >= 1000:
        s = f"{v / 1000:.1f}".rstrip("0").rstrip(".")
        return f"{s}k"
    return f"{v}đ"


def gen_order_id() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "ORD" + "".join(secrets.choice(alphabet) for _ in range(8))


def gen_api_key() -> str:
    return "sk_" + secrets.token_hex(20)


# ---------------- settings (cache) ----------------
_settings_cache: dict[str, str | None] = {}


async def get_setting(key: str, default=None):
    if key not in _settings_cache:
        _settings_cache[key] = await db.fetchval("SELECT value FROM settings WHERE key=?", (key,))
    v = _settings_cache[key]
    return default if v in (None, "") else v


async def set_setting(key: str, value):
    await db.execute(
        "INSERT INTO settings(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    _settings_cache[key] = value


# ---------------- users ----------------
async def upsert_user(tg_user) -> dict:
    uid = tg_user.id
    username = tg_user.username or ""
    full_name = tg_user.full_name or ""
    u = await db.fetchone("SELECT * FROM users WHERE user_id=?", (uid,))
    if not u:
        lang = "en" if (getattr(tg_user, "language_code", None) or "").startswith("en") else "vi"
        await db.execute(
            "INSERT OR IGNORE INTO users(user_id, username, full_name, language) VALUES (?,?,?,?)",
            (uid, username, full_name, lang),
        )
        u = await db.fetchone("SELECT * FROM users WHERE user_id=?", (uid,))
        u["_is_new"] = True
        return u
    if u["username"] != username or u["full_name"] != full_name:
        await db.execute(
            "UPDATE users SET username=?, full_name=? WHERE user_id=?", (username, full_name, uid)
        )
        u["username"], u["full_name"] = username, full_name
    return u


async def get_user(uid: int):
    return await db.fetchone("SELECT * FROM users WHERE user_id=?", (uid,))


async def find_user(query: str):
    q = query.strip().lstrip("@")
    if q.isdigit():
        return await get_user(int(q))
    return await db.fetchone("SELECT * FROM users WHERE lower(username)=lower(?)", (q,))


async def get_user_by_api_key(key: str):
    if not key:
        return None
    return await db.fetchone("SELECT * FROM users WHERE api_key=?", (key,))


async def reset_api_key(uid: int) -> str:
    key = gen_api_key()
    await db.execute("UPDATE users SET api_key=? WHERE user_id=?", (key, uid))
    return key


async def set_role(uid: int, role: str, discount: float | None = None):
    if discount is None:
        discount = RESELLER_DEFAULT_DISCOUNT if role == "reseller" else 0
    await db.execute(
        "UPDATE users SET role=?, discount_rate=? WHERE user_id=?", (role, discount, uid)
    )


async def adjust_balance(uid: int, amount: int, ttype: str, desc: str, ref: str | None = None,
                         count_deposit: bool = False) -> int:
    """Cộng (+) / trừ (-) tiền trong transaction. Trả về số dư mới."""
    async with db.tx() as c:
        cur = await c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        row = await cur.fetchone()
        if not row:
            raise ShopError("user_not_found")
        new_bal = row["balance"] + amount
        if new_bal < 0:
            raise ShopError("insufficient", balance=row["balance"])
        await c.execute(
            "UPDATE users SET balance=?, total_deposited = total_deposited + ? WHERE user_id=?",
            (new_bal, amount if (count_deposit and amount > 0) else 0, uid),
        )
        await c.execute(
            "INSERT INTO transactions(user_id, amount, type, description, ref) VALUES (?,?,?,?,?)",
            (uid, amount, ttype, desc, ref),
        )
        return new_bal


async def credit_deposit(uid: int, amount: int, method: str, ref: str, note: str = ""):
    """Cộng tiền nạp, chống cộng trùng theo `ref`. Trả về số dư mới hoặc None nếu trùng/không có user."""
    async with db.tx() as c:
        cur = await c.execute("SELECT 1 FROM deposits WHERE ref=?", (ref,))
        if await cur.fetchone():
            return None
        cur = await c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        row = await cur.fetchone()
        if not row:
            return None
        await c.execute(
            "INSERT INTO deposits(user_id, method, amount, ref, status, note) VALUES (?,?,?,?,?,?)",
            (uid, method, amount, ref, "success", note[:500]),
        )
        await c.execute(
            "UPDATE users SET balance = balance + ?, total_deposited = total_deposited + ? WHERE user_id=?",
            (amount, amount, uid),
        )
        await c.execute(
            "INSERT INTO transactions(user_id, amount, type, description, ref) VALUES (?,?,?,?,?)",
            (uid, amount, "deposit", f"Nạp tiền qua {method}", ref),
        )
        return row["balance"] + amount


async def create_pending_deposit(uid: int, method: str, amount: int, ref: str, note: str = ""):
    """Tạo yêu cầu nạp chờ duyệt. Trả về id hoặc None nếu ref đã tồn tại."""
    async with db.tx() as c:
        cur = await c.execute("SELECT 1 FROM deposits WHERE ref=?", (ref,))
        if await cur.fetchone():
            return None
        cur = await c.execute(
            "INSERT INTO deposits(user_id, method, amount, ref, status, note) VALUES (?,?,?,?,?,?)",
            (uid, method, amount, ref, "pending", note[:500]),
        )
        return cur.lastrowid


async def approve_pending_deposit(dep_id: int):
    """Duyệt nạp chờ. Trả về (user_id, amount, method, new_balance) hoặc None."""
    async with db.tx() as c:
        cur = await c.execute("SELECT * FROM deposits WHERE id=? AND status='pending'", (dep_id,))
        d = await cur.fetchone()
        if not d:
            return None
        await c.execute("UPDATE deposits SET status='success' WHERE id=?", (dep_id,))
        await c.execute(
            "UPDATE users SET balance = balance + ?, total_deposited = total_deposited + ? WHERE user_id=?",
            (d["amount"], d["amount"], d["user_id"]),
        )
        await c.execute(
            "INSERT INTO transactions(user_id, amount, type, description, ref) VALUES (?,?,?,?,?)",
            (d["user_id"], d["amount"], "deposit", f"Nạp tiền qua {d['method']}", d["ref"]),
        )
        cur = await c.execute("SELECT balance FROM users WHERE user_id=?", (d["user_id"],))
        bal = (await cur.fetchone())["balance"]
        return d["user_id"], d["amount"], d["method"], bal


async def reject_pending_deposit(dep_id: int):
    d = await db.fetchone("SELECT * FROM deposits WHERE id=? AND status='pending'", (dep_id,))
    if not d:
        return None
    await db.execute("UPDATE deposits SET status='rejected' WHERE id=?", (dep_id,))
    return d


# ---------------- catalog ----------------
STOCK_SQL = "(SELECT COUNT(*) FROM stocks s WHERE s.product_id=p.id AND s.is_sold=0)"


async def list_categories():
    return await db.fetchall(
        f"""SELECT c.*, (SELECT COUNT(*) FROM products p WHERE p.category_id=c.id AND p.is_active=1
                 AND (p.is_infinite_stock=1 OR {STOCK_SQL} > 0)) AS avail,
                 (SELECT COUNT(*) FROM products p WHERE p.category_id=c.id) AS n_products
            FROM categories c ORDER BY c.position, c.id"""
    )


async def get_category(cid: int):
    return await db.fetchone("SELECT * FROM categories WHERE id=?", (cid,))


async def list_products(category_id: int | None = None, only_active: bool = True):
    where, params = [], []
    if only_active:
        where.append("p.is_active=1 AND c.is_active=1")
    if category_id is not None:
        where.append("p.category_id=?")
        params.append(category_id)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    return await db.fetchall(
        f"""SELECT p.*, c.name AS cat_name, c.emoji AS cat_emoji, c.custom_emoji_id AS cat_icon,
                   {STOCK_SQL} AS stock
            FROM products p JOIN categories c ON c.id=p.category_id {w}
            ORDER BY c.position, c.id, p.position, p.id""",
        params,
    )


async def get_product(pid: int):
    return await db.fetchone(
        f"""SELECT p.*, c.name AS cat_name, c.emoji AS cat_emoji, c.custom_emoji_id AS cat_icon,
                   c.is_active AS cat_active, {STOCK_SQL} AS stock,
                   (SELECT COUNT(*) FROM stocks s WHERE s.product_id=p.id AND s.is_sold=1) AS sold
            FROM products p JOIN categories c ON c.id=p.category_id WHERE p.id=?""",
        (pid,),
    )


def in_stock(p) -> bool:
    return bool(p["is_infinite_stock"]) or p["stock"] > 0


def unit_price(user: dict, product: dict) -> int:
    disc = float(user.get("discount_rate") or 0) if user else 0
    disc = max(0.0, min(disc, 100.0))
    return int(round(product["price"] * (100 - disc) / 100))


async def similar_products(product: dict, limit: int = 5):
    items = await list_products(product["category_id"])
    return [p for p in items if p["id"] != product["id"] and in_stock(p)][:limit]


# ---------------- purchase (ACID) ----------------
async def purchase(uid: int, pid: int, qty: int, source: str = "bot") -> dict:
    if qty < 1 or qty > 1000:
        raise ShopError("qty")
    async with db.tx() as c:
        cur = await c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
        user = await cur.fetchone()
        if not user:
            raise ShopError("user_not_found")
        user = dict(user)
        if user["is_banned"]:
            raise ShopError("banned")
        cur = await c.execute(
            "SELECT p.*, c.is_active AS cat_active FROM products p JOIN categories c ON c.id=p.category_id WHERE p.id=?",
            (pid,),
        )
        p = await cur.fetchone()
        if not p:
            raise ShopError("not_found")
        p = dict(p)
        if not p["is_active"] or not p["cat_active"]:
            raise ShopError("inactive")
        price = unit_price(user, p)
        total = price * qty
        if user["balance"] < total:
            raise ShopError("insufficient", balance=user["balance"], total=total)

        order_id = gen_order_id()
        accounts: list[str] = []
        status = "completed"
        if not p["is_infinite_stock"]:
            cur = await c.execute(
                "SELECT id, account_data FROM stocks WHERE product_id=? AND is_sold=0 ORDER BY id LIMIT ?",
                (pid, qty),
            )
            rows = await cur.fetchall()
            if len(rows) < qty:
                raise ShopError("out_of_stock", available=len(rows))
            ids = [r["id"] for r in rows]
            accounts = [r["account_data"] for r in rows]
            q = ",".join("?" * len(ids))
            cur = await c.execute(
                f"UPDATE stocks SET is_sold=1, sold_to_user_id=?, sold_at=datetime('now','localtime'), order_id=?"
                f" WHERE is_sold=0 AND id IN ({q})",
                (uid, order_id, *ids),
            )
            if cur.rowcount != qty:
                raise ShopError("out_of_stock", available=0)
        else:
            status = "processing"  # dịch vụ: admin xử lý / gửi nội dung

        await c.execute(
            "UPDATE users SET balance = balance - ?, total_spent = total_spent + ? WHERE user_id=? AND balance >= ?",
            (total, total, uid, total),
        )
        await c.execute(
            """INSERT INTO orders(order_id, user_id, product_id, product_name, quantity, unit_price,
                   total_price, cost_total, accounts_delivered, status, source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (order_id, uid, pid, p["name"], qty, price, total, p["cost_price"] * qty,
             "\n".join(accounts), status, source),
        )
        await c.execute(
            "INSERT INTO transactions(user_id, amount, type, description, ref) VALUES (?,?,?,?,?)",
            (uid, -total, "purchase", f"Mua {qty} x {p['name']}", order_id),
        )
    return {
        "order_id": order_id,
        "product_id": pid,
        "product_name": p["name"],
        "quantity": qty,
        "unit_price": price,
        "total_price": total,
        "balance": user["balance"] - total,
        "accounts": accounts,
        "status": status,
        "warranty": p["warranty_info"],
    }


async def get_order(order_id: str):
    return await db.fetchone("SELECT * FROM orders WHERE order_id=?", (order_id.strip().upper(),))


async def refund_order(order_id: str, reason: str = "Hoàn tiền đơn hàng"):
    """Hoàn toàn bộ tiền đơn vào ví. Trả về (user_id, amount, new_balance) hoặc None."""
    async with db.tx() as c:
        cur = await c.execute("SELECT * FROM orders WHERE order_id=?", (order_id,))
        o = await cur.fetchone()
        if not o or o["status"] == "refunded":
            return None
        await c.execute("UPDATE orders SET status='refunded' WHERE order_id=?", (order_id,))
        await c.execute(
            "UPDATE users SET balance = balance + ?, total_spent = MAX(0, total_spent - ?) WHERE user_id=?",
            (o["total_price"], o["total_price"], o["user_id"]),
        )
        await c.execute(
            "INSERT INTO transactions(user_id, amount, type, description, ref) VALUES (?,?,?,?,?)",
            (o["user_id"], o["total_price"], "refund", reason, order_id),
        )
        cur = await c.execute("SELECT balance FROM users WHERE user_id=?", (o["user_id"],))
        bal = (await cur.fetchone())["balance"]
        return o["user_id"], o["total_price"], bal


async def replace_one_account(order_id: str):
    """Lấy 1 acc mới trong kho giao bù cho đơn (bảo hành). Trả về acc hoặc None nếu hết kho."""
    async with db.tx() as c:
        cur = await c.execute("SELECT * FROM orders WHERE order_id=?", (order_id,))
        o = await cur.fetchone()
        if not o:
            return None
        cur = await c.execute(
            "SELECT id, account_data FROM stocks WHERE product_id=? AND is_sold=0 ORDER BY id LIMIT 1",
            (o["product_id"],),
        )
        s = await cur.fetchone()
        if not s:
            return None
        await c.execute(
            "UPDATE stocks SET is_sold=1, sold_to_user_id=?, sold_at=datetime('now','localtime'), order_id=? WHERE id=?",
            (o["user_id"], order_id, s["id"]),
        )
        new_acc = (o["accounts_delivered"] + "\n" if o["accounts_delivered"] else "") + s["account_data"]
        await c.execute("UPDATE orders SET accounts_delivered=? WHERE order_id=?", (new_acc, order_id))
        return s["account_data"]


# ---------------- stock management ----------------
async def import_stock(pid: int, lines: list[str]) -> tuple[int, int]:
    clean, seen = [], set()
    for ln in lines:
        ln = ln.strip().strip("\ufeff")
        if ln and ln not in seen:
            seen.add(ln)
            clean.append(ln)
    if not clean:
        return 0, 0
    async with db.tx() as c:
        cur = await c.execute("SELECT COUNT(*) AS n FROM stocks WHERE product_id=?", (pid,))
        before = (await cur.fetchone())["n"]
        await c.executemany(
            "INSERT OR IGNORE INTO stocks(product_id, account_data) VALUES (?,?)",
            [(pid, x) for x in clean],
        )
        cur = await c.execute("SELECT COUNT(*) AS n FROM stocks WHERE product_id=?", (pid,))
        after = (await cur.fetchone())["n"]
    added = after - before
    return added, len(lines) - added


# ---------------- API rate limit ----------------
_rate: dict[int, list[float]] = {}


def rate_limited(uid: int, limit_per_min: int) -> bool:
    now = time.time()
    q = [t for t in _rate.get(uid, []) if now - t < 60]
    if len(q) >= max(1, limit_per_min):
        _rate[uid] = q
        return True
    q.append(now)
    _rate[uid] = q
    return False
