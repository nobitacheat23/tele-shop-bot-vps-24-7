import base64
import json
import os
from dotenv import load_dotenv

_BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_BASE, ".env"))

# Tự động giải mã cấu hình khi chạy trên Cloud VPS 24/7 (cloud_env.dat)
_CLOUD_DAT = os.path.join(_BASE, "cloud_env.dat")
if not os.getenv("BOT_TOKEN") and os.path.exists(_CLOUD_DAT):
    try:
        _raw = base64.b64decode(open(_CLOUD_DAT, "r", encoding="ascii").read().strip())
        _key = b"TAINGUYENMMO_CLOUD_VPS_KEY_2026"
        _dec = json.loads(bytes(b ^ _key[i % len(_key)] for i, b in enumerate(_raw)).decode("utf-8"))
        for _k, _v in _dec.items():
            if _k and _v is not None and not os.getenv(_k):
                os.environ[_k] = str(_v)
    except Exception:
        pass


def _get(name, default=""):
    return os.getenv(name, default).strip()


def _bool(name, default="false"):
    return _get(name, default).lower() in ("1", "true", "yes", "on")


BOT_TOKEN = _get("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in _get("ADMIN_IDS").replace(" ", "").split(",") if x]

SHOP_NAME = _get("SHOP_NAME", "MY SHOP")
GROUP_LINK = _get("GROUP_LINK")
CHANNEL_LINK = _get("CHANNEL_LINK")
SUPPORT_USERNAME = _get("SUPPORT_USERNAME").lstrip("@")

BUTTON_STYLE = _get("BUTTON_STYLE", "success") or None
CUSTOM_EMOJI_IN_TEXT = _bool("CUSTOM_EMOJI_IN_TEXT", "true")
RESELLER_DEFAULT_DISCOUNT = float(_get("RESELLER_DEFAULT_DISCOUNT", "10") or 0)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, _get("DB_PATH", "shop.db"))

WEB_ENABLED = _bool("WEB_ENABLED", "true")
WEB_HOST = _get("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("PORT") or _get("WEB_PORT", "8080") or 8080)
PUBLIC_URL = _get("PUBLIC_URL", f"http://localhost:{WEB_PORT}").rstrip("/")

BANK_ID = _get("BANK_ID", "MB")
BANK_ACCOUNT = _get("BANK_ACCOUNT")
BANK_ACCOUNT_NAME = _get("BANK_ACCOUNT_NAME")
DEPOSIT_PREFIX = _get("DEPOSIT_PREFIX", "NAP").upper()
MIN_DEPOSIT = int(_get("MIN_DEPOSIT", "10000") or 10000)
SEPAY_API_KEY = _get("SEPAY_API_KEY")
CASSO_SECURE_TOKEN = _get("CASSO_SECURE_TOKEN")
BANK_WEBHOOK_KEY = _get("BANK_WEBHOOK_KEY")

USDT_RATE = float(_get("USDT_RATE", "26000") or 26000)
USDT_TRC20_ADDRESS = _get("USDT_TRC20_ADDRESS")
USDT_BEP20_ADDRESS = _get("USDT_BEP20_ADDRESS")
BINANCE_PAY_ID = _get("BINANCE_PAY_ID")
TRONGRID_API_KEY = _get("TRONGRID_API_KEY")


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
