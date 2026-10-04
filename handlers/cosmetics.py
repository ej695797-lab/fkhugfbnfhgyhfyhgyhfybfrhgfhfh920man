"""
Cosmetics handler: g2_putActiveCosmetics
"""

from services.db import accounts


async def handle_put_active_cosmetics(body: dict) -> dict:
    account_id = body.get("accountID", "")
    active_cosmetics = body.get("activeCosmetics", [])

    if account_id:
        await accounts.update_one(
            {"accountID": account_id},
            {"$set": {"activeCosmetics": active_cosmetics}},
        )

    return {"success": 1}
