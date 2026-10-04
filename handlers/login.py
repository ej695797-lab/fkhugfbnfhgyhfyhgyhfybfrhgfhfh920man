"""
Handler for g2_questLogIntoAccount.
Auto-creates accounts on first login.
"""

import uuid
import secrets
import base64
import json
import string
from datetime import datetime, timezone
from pathlib import Path

from config import BASE_DIR, LOG_DIR
from services.db import accounts, bundles
from services.property_defaults import default_for_property

LOGIN_LOG_FILE = LOG_DIR / "login_traffic.log"

# Profile applied to every newly created account. Colours are packed ARGB
# ints (0xAARRGGBB); -16777216 is opaque black.
PROFILE_PATH = Path(BASE_DIR) / "data" / "account_profile.json"


def _credential_shaped(prefix: str, length: int) -> str:
    """
    Build a credential-shaped placeholder.

    The client treats these fields as AWS SigV4 credentials and signs its
    DynamoDB calls with them, but this server issues and accepts them itself,
    so only the shape matters. Generating them at runtime (instead of storing
    literals) keeps real-looking secrets out of version control - GitHub push
    protection rejects any commit containing an ASIA-prefixed key ID.
    """
    alphabet = string.ascii_uppercase + string.digits
    body = "".join(secrets.choice(alphabet) for _ in range(length - len(prefix)))
    return prefix + body


# Stable for the lifetime of the process, so a client that caches them keeps
# working until the server restarts.
ACCESS_KEY = _credential_shaped("ASIA", 20)
SECRET_KEY = _credential_shaped("", 40)


def _load_profile() -> dict:
    """Load the default account profile, ignoring keys that start with '_'."""
    try:
        raw = PROFILE_PATH.read_text(encoding="utf-8")
        return {k: v for k, v in json.loads(raw).items() if not k.startswith("_")}
    except FileNotFoundError:
        print(f"[login] Profile not found at {PROFILE_PATH}, using built-in defaults")
    except Exception as exc:
        print(f"[login] Failed to load profile: {exc}")
    return {}


async def _all_bundle_keys() -> list:
    """Every bundle key in the database, so players own all current bundles."""
    keys = await bundles.distinct("bundleKey")
    return sorted(k for k in keys if isinstance(k, str) and k)


def _server_time() -> str:
    """Current time in the game's format: 'YYYY MM/DD HH:mm:ss'"""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y %m/%d %H:%M:%S")


def _random_session_id() -> str:
    return str(uuid.uuid4().int % 100_000_000)


def _random_nonce() -> str:
    return base64.b64encode(secrets.token_bytes(16)).decode("ascii")


def _random_key(length: int = 48) -> str:
    return base64.b64encode(secrets.token_bytes(length)).decode("ascii")


def _append_login_log(request_body: dict, response_body: dict) -> None:
    """Append login request/response payloads (no headers) to a file."""
    LOGIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = (
        f"[{timestamp}]\n"
        f"RequestBody: {json.dumps(request_body, ensure_ascii=False)}\n"
        f"ResponseBody: {json.dumps(response_body, ensure_ascii=False)}\n"
        f"{'=' * 80}\n"
    )
    with LOGIN_LOG_FILE.open("a", encoding="utf-8") as log_file:
        log_file.write(entry)


# Default account template for new players
DEFAULT_ACCOUNT = {
    "displayName": "<color=blue>920Man</color>",
    "ownedPatterns": ["AirGrabber","AirGrabber_octopus","alarmClock","AmoogusKnife","Anchor","Arrow","AutoTurretTargeter","Balloon","Balloon_Anniversary","Ballot","Banner","Baseball","BaseballBat","BasicBoxingGlove","Basketball","Bazooka","Bazooka_Krampus","BearTrap","BiggieBat","BlankGun","BlankHelmet","BlankPalm","BlankWand","BlankWrist","Boomerang","BowAndArrow","Bullet","Buttcoin","Buttjo","Buttjo_Electric","Buttjo_Techno","CameraDrone","CameraTarget","CandyBlindness","CandyCaneHook","CandyExplosive","CandyFeign","CandyFire","CandyFreeze","CandyRainbow","CandySpeed","CandyStuffing","CardGun","Chainsaw","Chainsaw_evilScientist","Coal","Compass","ConfettiGun","ConfettiGun_Impulse","Cosmetic","Crab","CrabCage","CrewTaskList","Crossbow","Dagger","Dagger_spy","Detonator","Detonator_GameMaker","DiscLauncher","DragonEgg_black","DragonEgg_green","DragonEgg_purple","Drumstick","Dumbbell","DungeonKey","ExplosiveArrow","ExplosiveGrenade","ExplosiveGrenade_frag","FireArrow","FireAxe","FireAxe_bone","Fireburst","Fireburst_golden","FireExtinguisher","FireGrenade","Firework","Firework_ringmaster","Fish","FishBucket","FishingBait_JellyFish","FishingBait_Magnet","FishingBait_Minnow","FishingBait_Worm","FishingJunk_Boot","FishingJunk_Can","FishingJunk_CellPhone","FishingJunk_LicensePlate","FishingJunk_MessageInBottle","FishingJunk_MessageInBottle_Message","FishingJunk_ToiletSeat","FishingRod_Advanced","FishingRod_Basic","FishingRod_Intermediate","Flag","Flail","Flail_golden","FlameThrower","FlameThrower_Dragon","FlareGun","FlareGun_Dragon","Flashlight","Flipper","FlySwatter","Football","FPVGoggles","FreezeArrow","FreezeGlove","FreezeGlove_Yeti","FreezeGrenade","FreezeRay","FreezeRay_villain","Frisbee","FrostSword","GatlingGun","GatlingGunMagazine","GeigerCounter","GiftBox","GrapplingArrow","GrapplingHook","GrapplingHook_golden","GrapplingHook_Spider","HandBell","HandCamera","HandGimbalCamera","Harpoon","HarpoonGun","HeadCameraReverse","HeadTurret","HealingDart","HealingGun","HelmetFlashlight","Holster_medium","Holster_small","HorrorDetector","HotCoco","ImpulseGrenade","Ingredient_bacon","Ingredient_baconSandwich","Ingredient_bagel","Ingredient_bakedPotato","Ingredient_batter","Ingredient_beef","Ingredient_beefStew","Ingredient_berries","Ingredient_bone","Ingredient_bread","Ingredient_breakfast","Ingredient_burntGarbage","Ingredient_cake","Ingredient_cheese","Ingredient_cheeseburger","Ingredient_cheeseSandwich","Ingredient_chicken","Ingredient_chickenNoodleSoup","Ingredient_chickenParm","Ingredient_chickenTender","Ingredient_cookie","Ingredient_crab","Ingredient_crabBurger","Ingredient_crabCake","Ingredient_crepe","Ingredient_donut","Ingredient_dumpling","Ingredient_egg","Ingredient_eyeball","Ingredient_fancyMacAndCheese","Ingredient_feather","Ingredient_fish","Ingredient_fishAndChips","Ingredient_fishSticks","Ingredient_flour","Ingredient_flowerEvil","Ingredient_flowerGood","Ingredient_frenchFry","Ingredient_frenchToast","Ingredient_friedChicken","Ingredient_friedChickenSandwich","Ingredient_friedEgg","Ingredient_friedEggSandwich","Ingredient_frogLeg","Ingredient_fruit","Ingredient_fruitSalad","Ingredient_garbage","Ingredient_grilledCheeseSandwich","Ingredient_hamburger","Ingredient_hawaiianPizza","Ingredient_hotdog","Ingredient_jelly","Ingredient_jellySandwich","Ingredient_lasagna","Ingredient_leaf","Ingredient_lettuce","Ingredient_lobsterRoll","Ingredient_macAndCheese","Ingredient_milk","Ingredient_mushroom","Ingredient_mushroomLong","Ingredient_noodle","Ingredient_pancake","Ingredient_pepperoniPizza","Ingredient_pie","Ingredient_pizza","Ingredient_pizzaBagel","Ingredient_potato","Ingredient_pumaShoe","Ingredient_pumpkin","Ingredient_pumpkinBread","Ingredient_pumpkinPie","Ingredient_pumpkinSpiceLatte","Ingredient_quesadilla","Ingredient_ramen","Ingredient_salad","Ingredient_sausage","Ingredient_spaghettiAndMeatballs","Ingredient_steak","Ingredient_steakSub","Ingredient_steamedCrab","Ingredient_steamedFish","Ingredient_stirFry","Ingredient_sugar","Ingredient_syrup","Ingredient_tacoBeef","Ingredient_tacoChicken","Ingredient_tacoFish","Ingredient_tail","Ingredient_tentacle","Ingredient_tomato","Ingredient_tomatoSoup","Ingredient_tortilla","IngredientDiscard_appleCore","IngredientDiscard_bowl","IngredientDiscard_plateLarge","IngredientDiscard_plateSmall","InnerTube","InnerTube_Duck","ItemDecoration","JackInTheBox","Jetpack","key","keyCard","LaserGun","LaserSword_basic","LaserSword_crossGuard","LaserSword_curved","LaserSword_doubleSided","LaserSword_short","Letter","Lighter","LightningHammer","localKey_crescent","localKey_diamond","localKey_star","loot_alienEgg","loot_batWing","loot_blueCrystal","loot_briefcase","loot_coalOre","loot_copperIngot","loot_copperOre","loot_desertTablet","loot_fabric","loot_flint","loot_goldIngot","loot_horn","loot_insectWing","loot_ironIngot","loot_ironOre","loot_obsidian","loot_pearl","loot_purpleCrystal","loot_redCrystal","loot_seashell","loot_sticks","loot_stone","loot_sulfurOre","loot_tooth","loot_uranium","loot_wood","LootSack","LootSack_ccJuly2025","LostNote","Mace","Machete","Machete_Pirate","Machete_Samurai","Machete_Spartan","Machete_Voyager","Magnet","MagnifyingGlass","MagnifyingGlass_invisible","MapObject","Match","MegaLootSack","MeleePaintBrush","Microphone","Microphone_Cursed","Microphone_PitchDown","Microphone_PitchUp","Minecart","Minion_energy","Minion_laser","Minion_lightning","MinionCapsule","MinionController","Missile","Missile_gogNuke","MobSpawnEgg","PaintBomb","PaintBrush","PaintGun","PaintJar","PaintRollerSled","PaintRoomba","PelletGun","PelletGun_Army","PelletGun_Pirate","PelletGun_Voyager","PelletShotgun","PelletShotgun_exterminator","PelletShotgun_outlaw","PelletSniper","Pet_alien","Pet_base","Pet_bunny","Pet_cat","Pet_chicken","Pet_cow","Pet_deer","Pet_dino","Pet_dog","Pet_dragon","Pet_fox","Pet_grub","Pet_hedgehog","Pet_lizard","Pet_monkey","Pet_panda","Pet_pig","Pet_platypus","Pet_puma","Pet_rat","Pet_sheep","Pet_snail","Pet_spider","Pet_turtle","PetBackflipSign","PetBrush","PetBrush_ccMarch2025","PetCosmetic","PetLaserPointer","PetNametag","PetStopSign","PillowGrenade","Pin","PinGrenade","PlushBat","PlushBatProxy","PlushFrisbee","PlushFrisbeeProxy","PlushSleepCap_blue","PlushSleepCap_red","PlushSleepCapProxy_blue","PlushSleepCapProxy_red","PlushStickyImpulseBomb","PlushStickyImpulseBombProxy","PlushYP1C1","PlushYP1C2","PlushYP1C3","poisonApple","PortalGun","Potion","PowerSword","PropSelector","PumaClaw","PumaShoe","PumaShoe_PumpkinGrenade","PumaShoeBola","PumaShoeLauncher","PumpkinGrenade","PuzzlePiece","RadiationGrenade","RandomPetEgg","RCAdvancedCar","RCAdvancedCar_blue","RCAdvancedCar_green","RCAdvancedCar_red","RCBiplane","RCBiplane_sleigh","RCBoat","RCFighterJet","RCSimpleCar","RCTank","RCToyRemote","RCTrain","RCUFO","Record","Revolver","Revolver_Bone","Rose","RubberChicken","Saddle","SawbladeLauncher","Scythe","SelfieStick","Shield","Shield_Knight","Shield_superyeep","SilverBean","Sled","Sled_Skateboard","SmashGlove","SmokeGrenade","Snowball","Snowball_Skull","Snowball_SnowPile","SnowGlobe","Soundboard","Soundboard_Halloween","Sparkler","Sparkler_Ringmaster","Spear","Spear_swarmslayer","Spear_trident","SpikedShield","SprayCan","Stealable_banana","Stealable_chalice","Stealable_diamondNecklace","Stealable_moneyBag","Stealable_painting","SteampunkCrossbow","StuffedFlashlight","StuffedFlashlight_lich","SuperpowerModule","Surfboard","Surfboard_FishingBoat","Tape","Taser","TennisBall","TerrainDecoration","TerrainMaterialPaintBrush","TerrainShaper","ThrowableCake","ThrowingBasicBomb","ThrowingBlackHoleBomb","ThrowingDecoy","ThrowingFireBomb","ThrowingFreezeBomb","ThrowingImpulseBomb","ThrowingMegaphone","ThrowingPillowBomb","ThrowingPumpkinBomb","ThrowingRadiationBomb","ThrowingSmokeBomb","ThrowingSnowflake","ThrowingTeleporter","ThrowingTeleporter_alien","TradingCard","TradingCardBinder","TradingCardPack","TransformerGun","TronDisc","TronDisc_RGB","UmbrellaGlider","UmbrellaGlider_leaf","WarHorn","WearableBackpack_large","WearableBackpack_medium","WearableBackpack_small","WindupBomb","WishlistScroll","WitchesBroom","WristAirBlaster","WristCape","WristCape_royal","WristCape_villain","WristLaserTagGun","WristPropellor","WristRCToyRemote","WristTradingCardDisplay","WristVacuum","WristWebShooter","WristWing","WristWing_angel","WristWing_bob","WristWing_demon","YAWPSniper","MobSpawnEgg","Pet_base"],
    "activeCosmetics": ["roleBadge_tester"],
    "ownedBundles": ["bundle_party","bundle_pirate","bundle_hazmat","bundle_halloween2024","bundle_spartan","bundle_holiday2024","bundle_commando","bundle_druid","bundle_techno","bundle_exterminator","bundle_krampus","bundle_toymaker"],
    "wishlist": [],
    "eyeColor": -2039846657,
    "skinColor": -3489025,
    "mobileCode": "9200",
    "hasCreatorPack": 1,
    "hasUnlockedPrivateRooms": 1,
    "isIsolated": 0,
    "hasPendingMobileLogin": 0,
    "roleKeys": [],
    "currency": 0,
    "redeemedStashIDs": [],
    "cw_admin": ["920MAN"],
    "cw_staff": [],
    "cw_favorites": [],
    "cw_nextCanUseFreeFuelTimestamp": "1970 01/01 00:00:00",
    "analyticEventKeys": [],
    "firstLogin": "",
    "loginStreakFreezeTimestamp": "1970 01/01 00:00:00",
    "hasPendingWarning": 0,
    "shouldForceRefresh": 0,
    "isPermabanned": 0,
    "isMutebanned": 1,
    "remainingBanHours": 1,
    "banReason": "<color=blue>920Man</color>",
    "skipAttestation": 1,
    "lastChallengeRedeemedTime_login": "1970 01/01 00:00:00",
    "lastChallengeRedeemedTime_easy": "1970 01/01 00:00:00",
    "lastChallengeRedeemedTime_hard": "1970 01/01 00:00:00",
    "pendingMessages": [],
    "loginStreakData": {"length": 1, "currentTier": None, "nextTierThreshold": 3, "nextTier": "bronze"},
    "matchmakingSegment": None,
}


async def handle_login(body: dict) -> dict:
    """
    Process a login request. Auto-creates the account if it doesn't exist.
    Returns the 'data' payload (will be wrapped by the Lambda envelope).
    """
    account_id = body.get("accountID", "")
    oculus_id = body.get("oculusID", "")
    initial_skin = body.get("initialSkinColor", 0)
    initial_eye = body.get("initialEyeColor", -1)
    props_to_get = body.get("propertiesToGet", [])

    # Look up or create account
    account = await accounts.find_one({"accountID": account_id}, {"_id": 0})

    if account is None:
        # Auto-create new account from the template + admin profile.
        profile = _load_profile()
        account = dict(DEFAULT_ACCOUNT)
        account.update(profile)

        # Own every bundle currently in the database.
        account["ownedBundles"] = await _all_bundle_keys()

        account["accountID"] = account_id
        account["displayName"] = oculus_id or account_id
        # Client-supplied colours only apply when the profile leaves them unset.
        if "skinColor" not in profile:
            account["skinColor"] = initial_skin
        if "eyeColor" not in profile:
            account["eyeColor"] = initial_eye
        account["firstLogin"] = _server_time()
        await accounts.insert_one({**account})
        print(f"[login] Created new account: {account_id} ({oculus_id}) "
              f"bundles={len(account['ownedBundles'])} "
              f"roles={len(account.get('roleKeys', []))}")
    else:
        print(f"[login] Existing account: {account_id}")

    # Build response from the full account payload to match legacy behavior.
    # Older clients often tolerate/expect additional fields beyond
    # propertiesToGet, so we include all known account fields.
    data = {k: v for k, v in account.items() if k != "accountID"}

    # Ensure requested properties always exist.
    for prop in props_to_get:
        if prop not in data:
            data[prop] = default_for_property(prop)

    # Always include session/auth fields
    data["serverTime"] = _server_time()
    data["gameSessionID"] = "52759867"
    data["publicSessionID"] = "64827527"
    data["challengeNonce"] = "-4DJfVUq6G0_glnZzeV8ng=="
    data["skipAttestation"] = 1
    data["accessKey"] = ACCESS_KEY
    data["secretKey"] = SECRET_KEY
    data["sessionToken"] = "IQoJb3JpZ2luX2VjEKT//////////wEaCXVzLXdlc3QtMSJGMEQCIGux7ko80bOc/A6uIGmqpS30/lrR+BnmX4MOvh3/QILuAiAOBM/D4cVQN6p6JJZOpkufXsa2kcGbsn2ugIADV6Py7yrHAgh9EAMaDDY3MzQ5MzU2Mzk1NSIMlwPaIA+3J2hs9HXxKqQC8uRuzR0yjH65TFEOvzruUIo3FKIK+1n8JkDY1ocNpJM2dbFhvO/8DCXd0P44OG/RF7H5CkMsr5M4S5GAf9AZfZrrGakyTQlfJDX3AElzIjci1h5FRdMtjxZxXTUze/A05r8q7giQ9p6AA3ztE0aQTQcHNMK3VoAU1dbr/+Vb/ctvGVNL8ghoXLPnkIy3/ACHxtZie1VwtmVeTJ3bbrGdjIET8PlIIH4RerAbALwOH54NVln4sWFduZWLMWSKKs65WoEwXRfaShzIsMnDzZqUK/P6Q3ZmtnKpD/1gM2sWF+zYcnj8r4chdROpXHWteaF7sB5JGGepetVAkZlbgDxo3gVIQXwL4WaXKjl8iyPD1hBPo+WQAt2qlTtmfR5ps8qhUZ956zD0yMa7BjrYAeGmBxUhgipjxgcVGnsNqU4a9CKP9l4FYWsVR4c6JqkNllSXG0AklAqGUBAcD5iBiPef0lGsugjCkbINfFNWIn4MMbM4Ez0O34YSpJL9hGjOFzz8RtWdH6eRlQmc3QPttj9LaQKNXrnyl7ibTikRLGMI2+m3ha0/nG8Ytx4iHIKLzGfYGNGlOLcVWJ1ehekkMpUAY7IdOYupiz4ZUByuWye32O9i8hXUVW14b6bGaN4IgDIwFKqOQkgE+UIn4XFfhrNUK8qhrPNj+7MuLvNUmzdQzPcJ4J1ERQ=="
    data["e_accessKey"] = "eRi9T0nMr6NzYfPn9atAYRULSDLM5hy5jzcjiDRO/x4wvzjE6/kjFW5Ygj1EupKZ"
    data["e_secretKey"] = "9YuDOxB0EHRYW0xu4OFzg5bMabZuV4U8fcTE7TVrJBsQfm16Ld0Ld0KJHjGP7758hb0uEznFuUjD2BS7caBnm66ThP4/27+FV6QVCqJOZziqwchMdagxogbQIDOKYG2P"


    result = {"data": data}
    _append_login_log(body, result)
    return result
