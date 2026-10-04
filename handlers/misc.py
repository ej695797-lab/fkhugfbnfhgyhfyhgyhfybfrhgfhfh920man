"""
Misc Lambda handlers:
  - g2_fetchFeaturedWorldList
  - g2_fetchPopularWorldList
  - g2_logDebug
  - g2_refreshAccountOnline
  - g2_tryRedeemCurrencyStash
"""


async def handle_fetch_featured_world_list(body: dict) -> dict:
    return {"worlds": []}


async def handle_fetch_popular_world_list(body: dict) -> dict:
    return {"worlds": []}


async def handle_log_debug(body: dict) -> dict:
    # Silently accept debug logs
    return {"success": 1}


async def handle_refresh_account_online(body: dict) -> dict:
    return {"success": 1}


async def handle_try_redeem_currency_stash(body: dict) -> dict:
    return {
        "success": 1,
        "newCurrency": 0,
        "currencyAmount": 0,
    }
