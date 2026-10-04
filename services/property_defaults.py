"""
Default value generator for propertiesToGet fields.
Mirrors the _default_for_property logic from server.py.
"""


def default_for_property(name: str):
    """Best-guess default value for a propertiesToGet field name."""
    n = name.lower()

    # Known account flags expected as numeric toggle fields.
    if n == "shouldforcerefresh":
        return 0

    # Door-shaped objects
    if n.startswith("door_"):
        return {"block": 0, "position": [0, 0]}

    # Boolean-ish ints
    if n.startswith(("is", "has", "no", "block", "skip", "first")):
        return 0

    # Counters / versions
    if n.endswith(("version", "depth", "level", "count", "id", "direction",
                   "sessionid", "timestamp", "offset")):
        return 0

    # Lists
    if n.endswith(("keys", "ids", "patterns", "cosmetics", "bundles",
                   "messages", "events")):
        return []

    # Maps / dicts
    if n == "savedata":
        return ""
    if n.endswith(("data", "states", "map")):
        return {}

    # Names / strings
    if any(s in n for s in ("name", "key", "color", "message", "reason", "code")):
        return ""

    # Dimensions
    if "dimension" in n:
        return [100, 100, 100]

    # Numeric defaults
    if "currency" in n or "amount" in n:
        return 0

    return ""
