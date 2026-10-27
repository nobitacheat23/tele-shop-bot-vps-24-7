"""SQLite database layer (aiosqlite).

Mọi thao tác ghi quan trọng (trừ tiền, xuất kho, nạp tiền) đều đi qua `tx()`:
- Khóa asyncio toàn cục + `BEGIN IMMEDIATE` => tuần tự hóa giao dịch, đảm bảo ACID,
  không thể xảy ra race condition (2 người mua trùng 1 acc / trừ tiền âm).
"""
import asyncio
import contextlib

import aiosqlite

from config import DB_PATH

_conn: aiosqlite.Connection | None = None
_lock = asyncio.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id         INTEGER PRIMARY KEY,
    username        TEXT,
    full_name       TEXT,
    balance         INTEGER NOT NULL DEFAULT 0,
    total_deposited INTEGER NOT NULL DEFAULT 0,
    total_spent     INTEGER NOT NULL DEFAULT 0,
    role            TEXT NOT NULL DEFAULT 'member',
    discount_rate   REAL NOT NULL DEFAULT 0,
    api_key         TEXT UNIQUE,
    api_rate_limit  INTEGER NOT NULL DEFAULT 30,
    is_banned       INTEGER NOT NULL DEFAULT 0,
    language        TEXT NOT NULL DEFAULT 'vi',
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    CHECK (balance >= 0)
);

CREATE TABLE IF NOT EXISTS categories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    emoji           TEXT NOT NULL DEFAULT '',
    custom_emoji_id TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    position        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id       INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    price             INTEGER NOT NULL DEFAULT 0,
    cost_price        INTEGER NOT NULL DEFAULT 0,
    emoji             TEXT NOT NULL DEFAULT '',
    custom_emoji_id   TEXT,
    warranty_info     TEXT NOT NULL DEFAULT '',
    description       TEXT NOT NULL DEFAULT '',
    is_infinite_stock INTEGER NOT NULL DEFAULT 0,
    is_active         INTEGER NOT NULL DEFAULT 1,
    position          INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS stocks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    account_data    TEXT NOT NULL,
    is_sold         INTEGER NOT NULL DEFAULT 0,
    sold_to_user_id INTEGER,
    sold_at         TEXT,
    order_id        TEXT,
    UNIQUE (product_id, account_data)
);
CREATE INDEX IF NOT EXISTS idx_stocks_pid_sold ON stocks(product_id, is_sold);

CREATE TABLE IF NOT EXISTS orders (
    order_id           TEXT PRIMARY KEY,
    user_id            INTEGER NOT NULL,
    product_id         INTEGER,
    product_name       TEXT NOT NULL DEFAULT '',
    quantity           INTEGER NOT NULL,
    unit_price         INTEGER NOT NULL DEFAULT 0,
    total_price        INTEGER NOT NULL,
    cost_total         INTEGER NOT NULL DEFAULT 0,
    accounts_delivered TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL DEFAULT 'completed',
    source             TEXT NOT NULL DEFAULT 'bot',
    created_at         TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id, created_at);

CREATE TABLE IF NOT EXISTS transactions (
    trans_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    amount      INTEGER NOT NULL,
    type        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    ref         TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_trans_user ON transactions(user_id, created_at);

CREATE TABLE IF NOT EXISTS deposits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    method     TEXT NOT NULL,
    amount     INTEGER NOT NULL,
    ref        TEXT UNIQUE,
    status     TEXT NOT NULL DEFAULT 'success',
    note       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    TEXT NOT NULL,
    user_id     INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    admin_note  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS payment_intents (
    pay_code    TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    intent_type TEXT NOT NULL DEFAULT 'order',
    product_id  INTEGER,
    quantity    INTEGER NOT NULL DEFAULT 1,
    amount      INTEGER NOT NULL,
    content     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    chat_id     INTEGER,
    message_id  INTEGER,
    tx_ref      TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_intents_status ON payment_intents(status, created_at);

"""


async def init_db():
    global _conn
    _conn = await aiosqlite.connect(DB_PATH, isolation_level=None)
    _conn.row_factory = aiosqlite.Row
    await _conn.execute("PRAGMA journal_mode=WAL")
    await _conn.execute("PRAGMA foreign_keys=ON")
    await _conn.executescript(SCHEMA)
    row = await fetchone("SELECT COUNT(*) AS n FROM categories")
    if row["n"] == 0:
        from seed import seed_data
        async with tx() as c:
            await seed_data(c)


async def close_db():
    if _conn:
        await _conn.close()


async def fetchone(sql, params=()):
    cur = await _conn.execute(sql, params)
    row = await cur.fetchone()
    await cur.close()
    return dict(row) if row else None


async def fetchall(sql, params=()):
    cur = await _conn.execute(sql, params)
    rows = await cur.fetchall()
    await cur.close()
    return [dict(r) for r in rows]


async def fetchval(sql, params=(), default=None):
    row = await fetchone(sql, params)
    if not row:
        return default
    v = list(row.values())[0]
    return default if v is None else v


async def execute(sql, params=()):
    """Câu lệnh ghi đơn lẻ (tự commit). KHÔNG gọi bên trong tx()."""
    async with _lock:
        cur = await _conn.execute(sql, params)
        lid, rc = cur.lastrowid, cur.rowcount
        await cur.close()
        return lid if lid else rc


@contextlib.asynccontextmanager
async def tx():
    """Giao dịch ACID. Bên trong dùng `await c.execute(...)` trực tiếp."""
    async with _lock:
        await _conn.execute("BEGIN IMMEDIATE")
        try:
            yield _conn
        except BaseException:
            await _conn.execute("ROLLBACK")
            raise
        else:
            await _conn.execute("COMMIT")
