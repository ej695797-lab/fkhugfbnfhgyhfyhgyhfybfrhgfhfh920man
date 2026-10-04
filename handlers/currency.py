"""
Currency handler: g2_devResetCurrency
"""

from services.db import accounts


async def handle_dev_reset_currency(body: dict) -> dict:
    account_id = body.get("accountID", "")
    new_currency = body.get("newCurrency", 0)

    if account_id:
        await accounts.update_one(
            {"accountID": account_id},
            {"$set": {"currency": new_currency}},
        )

    return {"success": 1, "newCurrency": new_currency}
