"""Dữ liệu mẫu ban đầu (chạy tự động khi khởi tạo DB lần đầu).

Đã tích hợp sẵn toàn bộ `custom_emoji_id` từ gói icon thương hiệu riêng của bot:
https://t.me/addemoji/ntn_brands_by_BANQUYEN1_bot
và bộ RestrictedEmoji của Telegram.
"""

MENU_DEFAULT_ICONS = {
    "icon_buy": "5431499171045581032",       # 🛒
    "icon_profile": "5373012449597335010",   # 👤
    "icon_history": "5426900601101374618",   # 🧿
    "icon_wallet": "5472363448404809929",    # 👛
    "icon_api": "5375129357373165375",       # 🔗
    "icon_support": "5465300082628763143",   # 💬
    "icon_warranty": "5375296873982604963",  # 🛡
    "icon_language": "5399898266265475100",  # 🌐
    "icon_refresh": "5426900601101374618",   # 🧿
    "icon_soldout": "5465665476971471368",   # ❌
    "bank_id": "MSB",
    "bank_account": "80000448919",
    "bank_account_name": "NGUYEN LE HOANG NHAT",
    "bank_auto_approve": "1",
}

# (emoji, name, is_active, custom_emoji_id)
CATEGORIES = [
    ("▶️", "YOUTUBE", 1, "6269042631561454681"),
    ("🤖", "CHAT GPT", 1, "6271586502036169067"),
    ("🅰️", "GOOGLE ULTRA", 1, "6271293194424557801"),
    ("💄", "APP LÀM ĐẸP", 1, "6269227740356944273"),
    ("🌐", "APP VPN", 1, "6271741112268890316"),
    ("📑", "MICROSOFT 365", 1, "6271580076765094434"),
    ("🎨", "ADOBE", 1, "6271279965925286077"),
    ("🎨", "CANVA", 1, "6269492099888981210"),
    ("✂️", "CAPCUT", 1, "6269443459384353775"),
    ("✳️", "API CLAUDE / CO...", 1, "6271376894747223124"),
    ("🦉", "DOULINGO", 0, "6271742044276793817"),
    ("🎞", "Seedance", 0, "6271651480596390134"),
    ("📧", "OUTLOOK", 1, "6271729477202486177"),
    ("Ⓜ️", "GMAIL", 1, "6269304581616837699"),
    ("1️⃣", "GOOGLE ONE", 1, "6271418268167184773"),
    ("✖️", "GROK", 0, "6271327893465342624"),
    ("🎦", "KLING", 1, "6271448599226229313"),
    ("💳", "MB Bank", 1, "6271672530231108413"),
    ("🍏", "APPLE", 1, "6271802478761616142"),
    ("🎬", "NETFLIX", 0, "6269018240442179387"),
    ("🅝", "NOTION", 1, "6269298040381645676"),
    ("🆀", "QUIZLET", 1, "6271545751386465385"),
    ("🟢", "SPOTIFY", 1, "6271515922838594352"),
    ("🎬", "APP PHIM", 1, "6269175234381750743"),
    ("🅰️", "AUTODESK", 1, "6271305911822721872"),
    ("🔴", "MINIMAX", 1, "6271269679478613652"),
    ("🧡", "LOCKET", 1, "6271366788689175328"),
    ("📘", "COURSESA", 0, "6269336935605478228"),
    ("🔲", "ELEVENLABS", 1, "6271340782662197897"),
    ("💫", "HIGGFIELD", 1, "6269420004567952733"),
    ("🎵", "SUNO", 0, "6271576206999560349"),
    ("📦", "AMAZON PRIME", 0, "6271691342187866142"),
    ("🌐", "DEEPSEEK", 1, "6271479106378931962"),
    ("🍏", "ICLOUD 2TB", 1, "6269399770977018812"),
    ("ℹ️", "LINKEDIN", 1, "6269207966327514068"),
    ("💻", "ZOOM PRO", 1, "6269485404034970407"),
    ("Ⓜ️", "MUSE AI", 1, "6271556188156993620"),
    ("🖼", "OPENART", 0, "6271430513118946157"),
    ("🟨", "XBOX", 1, "6271637118225752955"),
    ("✈️", "Tele", 1, "6271288401241055003"),
    ("📁", "Khác", 0, "6271715071882176082"),
]

# (category, name, price, warranty, infinite_stock, demo_stock_count)
PRODUCTS = [
    ("MUSE AI", "API MUSE TẠO 333 VIDEO 10s 1 THÁNG BHF", 150000, "Bảo hành full 1 tháng", 0, 4),
    ("MUSE AI", "MUSE AI 31 TỈ TOKEN BẢO HÀNH 24H", 85000, "Bảo hành 24h", 0, 17),
    ("CHAT GPT", "CHAT GPT PLUS 1 THÁNG BẢO HÀNH 12H", 95000, "Bảo hành 12h", 0, 0),
    ("CHAT GPT", "CHAT GPT PLUS 1 THÁNG BẢO HÀNH 5 NGÀY", 155000, "Bảo hành 5 ngày", 0, 9),
    ("CHAT GPT", "CHAT GPT PLUS 1 THÁNG BẢO HÀNH FULL", 200000, "Bảo hành full 1 tháng", 0, 33),
    ("CHAT GPT", "SLOT CHATGPT BUSINESS DÙNG CHUNG 1 THÁNG BHF", 119000, "Bảo hành full 1 tháng", 1, 0),
    ("CAPCUT", "CAPCUT PRO TEAM 7 NGÀY BHF", 10000, "Bảo hành full 7 ngày", 0, 0),
    ("CAPCUT", "CAPCUT PRO 1 THÁNG BHF", 38000, "Bảo hành full 1 tháng", 0, 20),
    ("GOOGLE ULTRA", "SLOT VEO3 ULTRA X5 RANDOM CREDITS 1 THÁNG", 360000, "Bảo hành 1 tháng", 0, 0),
    ("GOOGLE ULTRA", "SLOT VEO3 ULTRA X20 RANDOM CREDITS 1 THÁNG", 450000, "Bảo hành 1 tháng", 1, 0),
    ("GMAIL", "GMAIL US CỔ DATE 201X-202X 2FA", 45000, "Bảo hành login 24h", 0, 56),
    ("Tele", "THUÊ BOT TELEGRAM BINANCE ĐỂ ĐẤU API", 100000, "Hỗ trợ trong thời gian thuê", 0, 38),
]


async def seed_data(c):
    for k, v in MENU_DEFAULT_ICONS.items():
        await c.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES (?,?)", (k, v)
        )

    ids = {}
    for pos, (emoji, name, active, icon_id) in enumerate(CATEGORIES):
        cur = await c.execute(
            "INSERT INTO categories(name, emoji, custom_emoji_id, is_active, position) VALUES (?,?,?,?,?)",
            (name, emoji, icon_id, active, pos),
        )
        ids[name] = cur.lastrowid

    for pos, (cat, name, price, warranty, inf, stock_cnt) in enumerate(PRODUCTS):
        cur = await c.execute(
            "INSERT INTO products(category_id, name, price, warranty_info, is_infinite_stock, position)"
            " VALUES (?,?,?,?,?,?)",
            (ids[cat], name, price, warranty, inf, pos),
        )
        pid = cur.lastrowid
        if stock_cnt > 0:
            await c.executemany(
                "INSERT OR IGNORE INTO stocks(product_id, account_data) VALUES (?,?)",
                [(pid, f"demo{i+1}_{pid}@shop.local|Pass@{i+1:03d}|2FASECRET{i+1:03d}|TOKEN_{pid}_{i+1}")
                 for i in range(stock_cnt)],
            )
