"""
Challenge & store rotation handlers:
  - g2_redeemChallengeReward
  - g2_fetchGlobalRotation
"""


async def handle_redeem_challenge_reward(body: dict) -> dict:
    return {
        "success": 1,
        "currencyAmount": 0,
        "newCurrency": 0,
        "items": [],
        "newLastChallengeRedeemedTime": "2099 01/01 00:00:00",
    }


async def handle_fetch_global_rotation(body: dict) -> dict:
    return {
        "items": [],
        "rotationKey": body.get("rotationKey", ""),
    }
