"""Kiểm tra giao dịch USDT TRC20 qua TronGrid."""
import logging

import aiohttp

from config import TRONGRID_API_KEY, USDT_TRC20_ADDRESS

log = logging.getLogger(__name__)
USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


async def check_trc20(txid: str) -> float | None:
    """Trả về số USDT nhận được của TXID tới ví shop, hoặc None."""
    if not USDT_TRC20_ADDRESS:
        return None
    url = f"https://api.trongrid.io/v1/accounts/{USDT_TRC20_ADDRESS}/transactions/trc20"
    params = {"only_to": "true", "limit": "200", "contract_address": USDT_TRC20_CONTRACT}
    headers = {"TRON-PRO-API-KEY": TRONGRID_API_KEY} if TRONGRID_API_KEY else {}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, headers=headers,
                             timeout=aiohttp.ClientTimeout(total=20)) as r:
                data = await r.json()
    except Exception as e:  # noqa
        log.warning("TronGrid error: %s", e)
        return None
    for tx in data.get("data", []):
        if tx.get("transaction_id", "").lower() == txid.lower() and tx.get("to") == USDT_TRC20_ADDRESS:
            dec = int((tx.get("token_info") or {}).get("decimals", 6))
            return int(tx["value"]) / (10 ** dec)
    return None
