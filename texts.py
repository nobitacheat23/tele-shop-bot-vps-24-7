"""Đa ngôn ngữ (vi / en) cho phần giao diện khách hàng."""

MENU_ITEMS = [
    # key, default emoji
    ("buy", "🛒"),
    ("profile", "👤"),
    ("history", "🧿"),
    ("wallet", "👛"),
    ("api", "🔗"),
    ("support", "💬"),
    ("warranty", "🛡"),
    ("language", "🌐"),
]
MENU_EMOJI = dict(MENU_ITEMS)

TEXTS = {
    "vi": {
        "m_buy": "Mua hàng", "m_profile": "Hồ sơ", "m_history": "Lịch sử mua", "m_wallet": "Ví",
        "m_api": "Liên kết API", "m_support": "Hỗ trợ", "m_warranty": "Bảo hành", "m_language": "Ngôn ngữ",
        "start_1": 'Xin chào! Hãy chọn sản phẩm bạn muốn mua <tg-emoji emoji-id="5431499171045581032">🛒</tg-emoji>',
        "start_2": '<tg-emoji emoji-id="5436040291507247633">🎉</tg-emoji> Đã bật menu nhanh dưới ô chat.',
        "start_3": '<tg-emoji emoji-id="5436040291507247633">🎉</tg-emoji> Vui lòng chọn menu:',
        "placeholder": "Chọn menu nhanh bên dưới",
        "welcome": (
            '<tg-emoji emoji-id="5420315771991497307">🔥</tg-emoji> <b>CHÀO MỪNG ANH EM ĐẾN VỚI TÀI NGUYÊN MMO</b> <tg-emoji emoji-id="5420315771991497307">🔥</tg-emoji>\n'
            '<tg-emoji emoji-id="5350460637182993292">🎯</tg-emoji> Nơi cung cấp nguyên liệu, tài khoản và công cụ chiến MMO đỉnh nhất hiện nay!\n\n'
            '<tg-emoji emoji-id="5471952986970267163">📌</tg-emoji> <b>CHÚNG TÔI CÓ:</b>\n'
            '<tg-emoji emoji-id="5471978009449731768">👉</tg-emoji> Đa dạng tài khoản: Gmail, Telegram, TikTok, Facebook...\n'
            '<tg-emoji emoji-id="5471978009449731768">👉</tg-emoji> Công cụ AI & Đồ họa: ChatGPT Plus, Canva Pro, CapCut, Adobe...\n'
            '<tg-emoji emoji-id="5471978009449731768">👉</tg-emoji> Proxy, API, Bot và vô vàn tài nguyên MMO chất lượng cao.\n'
            '<tg-emoji emoji-id="5431449001532594346">👉</tg-emoji> Hệ thống nạp tiền và giao hàng tự động 100% cực nhanh!\n\n'
            '<tg-emoji emoji-id="5467406098367521267">👑</tg-emoji> <b>Admin/Support hỗ trợ 24/7:</b> @roxie_usa1998\n\n'
            'Chúc anh em mua sắm vui vẻ và "bão đơn" cùng <b>TÀI NGUYÊN MMO</b>! <tg-emoji emoji-id="5436040291507247633">🎉</tg-emoji>'
        ),
        "shop_title": "🛒 <b>Chọn danh mục hoặc sản phẩm bên dưới:</b>",
        "cat_title": "{icon} <b>{name}</b>\nChọn sản phẩm bạn muốn mua:",
        "cat_empty": "Danh mục này hiện chưa có sản phẩm.",
        "cat_paused": "❌ Danh mục đang tạm ngưng!",
        "refresh": "Cập nhật sản phẩm",
        "refreshed": "✅ Đã cập nhật kho hàng!",
        "all_products": "Tất cả sản phẩm",
        "back": "« Quay lại",
        "home": "🏠 Menu",
        "product_info": "{icon} <b>{name}</b>\n\n💰 Giá: <b>{price}</b>{disc}\n📦 Còn lại: <b>{stock}</b>\n"
                        "🛡 Bảo hành: {warranty}\n{desc}\n👛 Số dư của bạn: <b>{balance}</b>\n\n👇 Chọn số lượng muốn mua:",
        "disc_note": " <s>{old}</s> (giảm {rate}%)",
        "enter_qty": "✏️ Nhập số lượng",
        "ask_qty": "✏️ Gửi số lượng muốn mua (1 - {max}):",
        "bad_qty": "❌ Số lượng không hợp lệ.",
        "confirm": "🧾 <b>XÁC NHẬN ĐƠN HÀNG</b>\n\n📦 Sản phẩm: <b>{name}</b>\n🔢 Số lượng: <b>{qty}</b>\n"
                   "💵 Đơn giá: {price}\n💰 Tổng thanh toán: <b>{total}</b>\n👛 Số dư Ví: {balance}\n\n"
                   "👇 Chọn hình thức thanh toán:",
        "btn_confirm": "👛 Mua bằng Số dư Ví",
        "btn_pay_qr": "🏦 Thanh toán trực tiếp bằng QR ({total})",
        "btn_quick_qr": "🏦 Mua ngay bằng QR (1 SP - {price})",
        "btn_cancel": "❌ Hủy",
        "not_enough": "\n\n💡 Bạn có thể <b>Thanh toán trực tiếp bằng mã QR</b> bên dưới (hệ thống tự gửi hàng ngay sau khi chuyển khoản) hoặc nạp thêm <b>{need}</b> vào Ví.",
        "direct_qr": "🏦 <b>THANH TOÁN TRỰC TIẾP ĐƠN HÀNG</b>\n\n"
                     "📦 Sản phẩm: <b>{product}</b>\n"
                     "🔢 Số lượng: <b>{qty}</b>\n"
                     "📝 Nội dung CK: <code>{content}</code>\n\n"
                     "⚡ Vui lòng quét mã QR bên trên để thanh toán, sau đó bấm nút <b>Tôi đã thanh toán</b> bên dưới để nhận sản phẩm!",
        "direct_qr_paid_btn": "✅ Tôi đã thanh toán — Nhận sản phẩm",
        "btn_topup": "👛 Nạp tiền",
        "out_of_stock": "❌ Sản phẩm <b>{name}</b> đã hết hàng (còn {avail}).",
        "suggest": "\n\n💡 Gợi ý sản phẩm tương tự:",
        "inactive": "❌ Sản phẩm đang tạm ngưng bán.",
        "processing_buy": "⏳ Đang xử lý đơn hàng...",
        "buy_ok": "✅ <b>MUA HÀNG THÀNH CÔNG!</b>\n\n🧾 Mã đơn: <code>{order_id}</code>\n📦 Sản phẩm: <b>{name}</b>\n"
                  "🔢 Số lượng: {qty}\n💰 Tổng tiền: {total}\n👛 Số dư còn lại: {balance}",
        "buy_accounts": "\n━━━━━━━━━━━━━━\n{accounts}\n━━━━━━━━━━━━━━",
        "buy_file": "\n\n📄 Tài khoản được gửi trong file đính kèm.",
        "buy_service": "\n\n⏳ Đây là sản phẩm dịch vụ — Admin sẽ xử lý và gửi thông tin cho bạn sớm nhất.",
        "buy_warranty": "\n\n🛡 Bảo hành: {warranty}\n👉 Nếu tài khoản lỗi, bấm <b>🛡 Bảo hành</b> và nhập mã đơn <code>{order_id}</code>.",
        "profile": "👤 <b>HỒ SƠ CỦA BẠN</b>\n\n🆔 UID: <code>{uid}</code>\n👤 Username: {username}\n"
                   "💰 Số dư: <b>{balance}</b>\n📥 Tổng nạp: {deposited}\n📤 Tổng tiêu: {spent}\n"
                   "👑 Cấp bậc: <b>{role}</b>{disc}\n🧾 Số đơn đã mua: {orders}\n📅 Ngày tham gia: {joined}",
        "role_member": "Thành viên", "role_reseller": "Đại lý / CTV",
        "history_title": "🧿 <b>LỊCH SỬ MUA HÀNG</b> (trang {page})\nBấm vào đơn để xem chi tiết / tải lại file:",
        "history_empty": "🧿 Bạn chưa có đơn hàng nào.",
        "order_detail": "🧾 <b>ĐƠN HÀNG</b> <code>{order_id}</code>\n\n📦 {name}\n🔢 Số lượng: {qty}\n💰 Tổng: {total}\n"
                        "📌 Trạng thái: {status}\n🕒 Thời gian: {time}",
        "btn_download": "📥 Tải file tài khoản",
        "wallet": "👛 <b>VÍ CỦA BẠN</b>\n\n💰 Số dư: <b>{balance}</b>\n📥 Tổng nạp: {deposited}\n\nChọn phương thức nạp tiền:",
        "btn_bank": "🏦 Nạp Ngân hàng (VietQR)",
        "btn_crypto": "💎 Nạp Crypto (USDT)",
        "btn_txhist": "📜 Lịch sử giao dịch",
        "bank_choose": "🏦 <b>NẠP TIỀN NGÂN HÀNG</b>\nChọn số tiền muốn nạp (tối thiểu {min}):",
        "bank_custom": "✏️ Số khác",
        "ask_amount": "✏️ Gửi số tiền muốn nạp (VNĐ, tối thiểu {min}):",
        "bad_amount": "❌ Số tiền không hợp lệ.",
        "bank_qr": "🏦 <b>NẠP TIỀN QUA MÃ QR</b>\n\n"
                   "📝 Nội dung CK: <code>{content}</code>\n\n"
                   "⚠️ Vui lòng quét mã QR bên trên để chuyển khoản, sau đó bấm nút <b>Tôi đã chuyển khoản</b> bên dưới.",
        "bank_paid_btn": "✅ Tôi đã chuyển khoản",
        "bank_off": "❌ Nạp ngân hàng chưa được cấu hình. Vui lòng liên hệ Admin.",
        "crypto_menu": "💎 <b>NẠP CRYPTO (USDT)</b>\n💱 Tỷ giá: 1 USDT = <b>{rate}</b>\nChọn mạng:",
        "crypto_trc20": "💎 <b>NẠP USDT - TRC20</b>\n\n📮 Địa chỉ ví:\n<code>{addr}</code>\n💱 1 USDT = {rate}\n\n"
                        "Sau khi chuyển, gửi <b>TXID (mã giao dịch)</b> vào đây để hệ thống tự động kiểm tra:",
        "crypto_manual": "💎 <b>NẠP USDT - {net}</b>\n\n📮 {label}:\n<code>{addr}</code>\n💱 1 USDT = {rate}\n\n"
                         "✏️ Gửi số USDT bạn đã chuyển:",
        "ask_txid": "🔎 Gửi TXID / Mã đơn Binance Pay:",
        "crypto_off": "❌ Phương thức này chưa được cấu hình.",
        "tx_checking": "⏳ Đang kiểm tra giao dịch trên blockchain...",
        "tx_not_found": "❌ Không tìm thấy giao dịch USDT hợp lệ tới ví shop với TXID này. Kiểm tra lại sau 1-2 phút.",
        "tx_used": "❌ TXID này đã được sử dụng.",
        "tx_pending": "⏳ Yêu cầu nạp đã gửi tới Admin duyệt. Bạn sẽ nhận thông báo khi được cộng tiền.",
        "deposit_ok": "✅ <b>NẠP TIỀN THÀNH CÔNG!</b>\n\n💰 Số tiền: +{amount}\n🔖 Phương thức: {method}\n👛 Số dư mới: <b>{balance}</b>",
        "txhist_title": "📜 <b>20 GIAO DỊCH GẦN NHẤT</b>\n\n",
        "txhist_empty": "📜 Chưa có giao dịch nào.",
        "api_info": "🔗 <b>LIÊN KẾT API</b>\n\n🔑 API Key của bạn:\n<code>{key}</code>\n⏱ Giới hạn: {rate} request/phút\n"
                    "🌐 Base URL: <code>{base}</code>\n\n⚠️ Không chia sẻ API Key cho người khác!",
        "btn_api_reset": "🔄 Tạo Key mới",
        "btn_api_docs": "📖 Tài liệu đấu nối",
        "api_reset_ok": "✅ Đã tạo API Key mới!",
        "support": "💬 <b>HỖ TRỢ</b>\n\n👤 Admin: @{support}\n👥 Group: {group}\n📢 Channel: {channel}",
        "btn_contact": "💬 Nhắn Admin",
        "warranty_ask_order": "🛡 <b>YÊU CẦU BẢO HÀNH</b>\n\nGửi <b>mã đơn hàng</b> cần bảo hành (vd: <code>ORDABC12345</code>):",
        "warranty_bad_order": "❌ Không tìm thấy đơn hàng của bạn với mã này.",
        "warranty_dup": "⏳ Đơn này đang có phiếu bảo hành chờ xử lý.",
        "warranty_ask_reason": "✏️ Mô tả lỗi / lý do bảo hành:",
        "warranty_sent": "✅ Đã gửi phiếu bảo hành <b>#{tid}</b> cho Admin. Vui lòng chờ xử lý!",
        "lang_choose": "🌐 Chọn ngôn ngữ / Choose language:",
        "lang_ok": "✅ Đã đổi ngôn ngữ sang Tiếng Việt.",
        "cancel": "❌ Đã hủy.",
        "banned": "🚫 Tài khoản của bạn đã bị khóa.",
        "status_completed": "✅ Hoàn thành", "status_processing": "⏳ Đang xử lý", "status_refunded": "💸 Đã hoàn tiền",
        "notify_add": "💰 Tài khoản của bạn được <b>cộng {amount}</b>\n📝 Lý do: {reason}\n👛 Số dư: <b>{balance}</b>",
        "notify_sub": "💸 Tài khoản của bạn bị <b>trừ {amount}</b>\n📝 Lý do: {reason}\n👛 Số dư: <b>{balance}</b>",
    },
    "en": {
        "m_buy": "Shop", "m_profile": "Profile", "m_history": "Orders", "m_wallet": "Wallet",
        "m_api": "API Link", "m_support": "Support", "m_warranty": "Warranty", "m_language": "Language",
        "start_1": "Hello! Choose the product you want to buy 🛒",
        "start_2": "🎉 Quick menu enabled below the chat box.",
        "start_3": "🎉 Please choose a menu:",
        "placeholder": "Choose quick menu below",
        "welcome": "- Welcome to <b>{shop}</b> - ACCOUNT SOCIAL\n- Community group: {group}\n"
                   "- News channel: {channel}\n- Support: @{support}",
        "shop_title": "🛒 <b>Choose a category or product below:</b>",
        "cat_title": "{icon} <b>{name}</b>\nChoose a product:",
        "cat_empty": "No products in this category yet.",
        "cat_paused": "❌ This category is paused!",
        "refresh": "Refresh products",
        "refreshed": "✅ Stock refreshed!",
        "all_products": "All products",
        "back": "« Back",
        "home": "🏠 Menu",
        "product_info": "{icon} <b>{name}</b>\n\n💰 Price: <b>{price}</b>{disc}\n📦 In stock: <b>{stock}</b>\n"
                        "🛡 Warranty: {warranty}\n{desc}\n👛 Your balance: <b>{balance}</b>\n\n👇 Choose quantity:",
        "disc_note": " <s>{old}</s> (-{rate}%)",
        "enter_qty": "✏️ Enter quantity",
        "ask_qty": "✏️ Send the quantity (1 - {max}):",
        "bad_qty": "❌ Invalid quantity.",
        "confirm": "🧾 <b>ORDER CONFIRMATION</b>\n\n📦 Product: <b>{name}</b>\n🔢 Quantity: <b>{qty}</b>\n"
                   "💵 Unit price: {price}\n💰 Total: <b>{total}</b>\n👛 Wallet balance: {balance}\n\n"
                   "👇 Choose payment method:",
        "btn_confirm": "👛 Pay with Wallet Balance",
        "btn_pay_qr": "🏦 Direct QR Payment ({total})",
        "btn_quick_qr": "🏦 Buy now via QR (1 item - {price})",
        "btn_cancel": "❌ Cancel",
        "not_enough": "\n\n💡 You can use <b>Direct QR Payment</b> below (auto-delivers right after transfer) or top up <b>{need}</b> to your Wallet.",
        "direct_qr": "🏦 <b>DIRECT ORDER QR PAYMENT</b>\n\n"
                     "📦 Product: <b>{product}</b>\n"
                     "🔢 Quantity: <b>{qty}</b>\n"
                     "📝 Content: <code>{content}</code>\n\n"
                     "⚡ Scan the QR code above to pay, then click the confirm button below to receive your product!",
        "direct_qr_paid_btn": "✅ I have paid — Receive product",
        "btn_topup": "👛 Top up",
        "out_of_stock": "❌ <b>{name}</b> is out of stock ({avail} left).",
        "suggest": "\n\n💡 Similar products:",
        "inactive": "❌ This product is paused.",
        "processing_buy": "⏳ Processing your order...",
        "buy_ok": "✅ <b>PURCHASE SUCCESSFUL!</b>\n\n🧾 Order ID: <code>{order_id}</code>\n📦 Product: <b>{name}</b>\n"
                  "🔢 Quantity: {qty}\n💰 Total: {total}\n👛 Balance: {balance}",
        "buy_accounts": "\n━━━━━━━━━━━━━━\n{accounts}\n━━━━━━━━━━━━━━",
        "buy_file": "\n\n📄 Accounts are attached in the file.",
        "buy_service": "\n\n⏳ This is a service product — Admin will process and send you details soon.",
        "buy_warranty": "\n\n🛡 Warranty: {warranty}\n👉 If something is wrong, tap <b>🛡 Warranty</b> and send order ID <code>{order_id}</code>.",
        "profile": "👤 <b>YOUR PROFILE</b>\n\n🆔 UID: <code>{uid}</code>\n👤 Username: {username}\n"
                   "💰 Balance: <b>{balance}</b>\n📥 Total deposited: {deposited}\n📤 Total spent: {spent}\n"
                   "👑 Rank: <b>{role}</b>{disc}\n🧾 Orders: {orders}\n📅 Joined: {joined}",
        "role_member": "Member", "role_reseller": "Reseller",
        "history_title": "🧿 <b>ORDER HISTORY</b> (page {page})\nTap an order to view / re-download:",
        "history_empty": "🧿 You have no orders yet.",
        "order_detail": "🧾 <b>ORDER</b> <code>{order_id}</code>\n\n📦 {name}\n🔢 Quantity: {qty}\n💰 Total: {total}\n"
                        "📌 Status: {status}\n🕒 Time: {time}",
        "btn_download": "📥 Download accounts file",
        "wallet": "👛 <b>YOUR WALLET</b>\n\n💰 Balance: <b>{balance}</b>\n📥 Total deposited: {deposited}\n\nChoose a top-up method:",
        "btn_bank": "🏦 Bank transfer (VietQR)",
        "btn_crypto": "💎 Crypto (USDT)",
        "btn_txhist": "📜 Transactions",
        "bank_choose": "🏦 <b>BANK TOP-UP</b>\nChoose amount (min {min}):",
        "bank_custom": "✏️ Other amount",
        "ask_amount": "✏️ Send the amount (VND, min {min}):",
        "bad_amount": "❌ Invalid amount.",
        "bank_qr": "🏦 <b>BANK TOP-UP</b>\n\n🏛 Bank: <b>{bank}</b>\n💳 Account: <code>{acc}</code>\n"
                   "👤 Name: <b>{name}</b>\n💰 Amount: <b>{amount}</b>\n📝 Content: <code>{content}</code>\n\n"
                   "⚠️ Use the <b>EXACT</b> transfer content. Balance is credited automatically in 5-15 seconds or tap confirm below after sending.",
        "bank_paid_btn": "✅ I have transferred",
        "bank_off": "❌ Bank top-up is not configured. Please contact Admin.",
        "crypto_menu": "💎 <b>CRYPTO TOP-UP (USDT)</b>\n💱 Rate: 1 USDT = <b>{rate}</b>\nChoose network:",
        "crypto_trc20": "💎 <b>USDT - TRC20</b>\n\n📮 Address:\n<code>{addr}</code>\n💱 1 USDT = {rate}\n\n"
                        "After sending, reply with the <b>TXID</b> for automatic verification:",
        "crypto_manual": "💎 <b>USDT - {net}</b>\n\n📮 {label}:\n<code>{addr}</code>\n💱 1 USDT = {rate}\n\n"
                         "✏️ Send the USDT amount you transferred:",
        "ask_txid": "🔎 Send TXID / Binance Pay order ID:",
        "crypto_off": "❌ This method is not configured.",
        "tx_checking": "⏳ Checking the transaction on blockchain...",
        "tx_not_found": "❌ No valid USDT transfer to the shop wallet found for this TXID. Try again in 1-2 minutes.",
        "tx_used": "❌ This TXID has already been used.",
        "tx_pending": "⏳ Your top-up request was sent to Admin for approval.",
        "deposit_ok": "✅ <b>TOP-UP SUCCESSFUL!</b>\n\n💰 Amount: +{amount}\n🔖 Method: {method}\n👛 New balance: <b>{balance}</b>",
        "txhist_title": "📜 <b>LAST 20 TRANSACTIONS</b>\n\n",
        "txhist_empty": "📜 No transactions yet.",
        "api_info": "🔗 <b>API LINK</b>\n\n🔑 Your API Key:\n<code>{key}</code>\n⏱ Limit: {rate} requests/min\n"
                    "🌐 Base URL: <code>{base}</code>\n\n⚠️ Never share your API key!",
        "btn_api_reset": "🔄 Reset Key",
        "btn_api_docs": "📖 API Docs",
        "api_reset_ok": "✅ New API key generated!",
        "support": "💬 <b>SUPPORT</b>\n\n👤 Admin: @{support}\n👥 Group: {group}\n📢 Channel: {channel}",
        "btn_contact": "💬 Contact Admin",
        "warranty_ask_order": "🛡 <b>WARRANTY REQUEST</b>\n\nSend the <b>order ID</b> (e.g. <code>ORDABC12345</code>):",
        "warranty_bad_order": "❌ Order not found.",
        "warranty_dup": "⏳ This order already has a pending ticket.",
        "warranty_ask_reason": "✏️ Describe the problem:",
        "warranty_sent": "✅ Warranty ticket <b>#{tid}</b> has been sent to Admin!",
        "lang_choose": "🌐 Chọn ngôn ngữ / Choose language:",
        "lang_ok": "✅ Language switched to English.",
        "cancel": "❌ Cancelled.",
        "banned": "🚫 Your account has been banned.",
        "status_completed": "✅ Completed", "status_processing": "⏳ Processing", "status_refunded": "💸 Refunded",
        "notify_add": "💰 Your balance was <b>credited {amount}</b>\n📝 Reason: {reason}\n👛 Balance: <b>{balance}</b>",
        "notify_sub": "💸 Your balance was <b>debited {amount}</b>\n📝 Reason: {reason}\n👛 Balance: <b>{balance}</b>",
    },
}


def t(lang: str, key: str, **kw) -> str:
    s = TEXTS.get(lang or "vi", TEXTS["vi"]).get(key) or TEXTS["vi"].get(key, key)
    return s.format(**kw) if kw else s


def menu_label_map() -> dict[str, str]:
    """Map mọi biến thể chữ nút menu nhanh -> action key."""
    out = {}
    for lang in TEXTS:
        for key, emo in MENU_ITEMS:
            label = TEXTS[lang][f"m_{key}"]
            out[label] = key
            out[f"{emo} {label}"] = key
    return out
