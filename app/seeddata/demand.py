"""Branch demand assumptions for the synthetic history.

These weights are planted so the coursework database has visible patterns.
They are not measurements from real Lahore restaurants.
"""
from datetime import date

HISTORY_START = date(2025, 5, 1)
HISTORY_END = date(2026, 10, 31)
# Planted iftar window for Lahore Grill House only. It is a scenario label,
# not a claim about moon sighting or about real restaurant sales.
RAMADAN_START = date(2026, 2, 18)
RAMADAN_END = date(2026, 3, 19)

# Opening and closing local times, Monday through Sunday.
HOURS = {
    "lahore-grill-house": ("08:00", "23:30"),
    "urban-bites-lahore": ("12:00", "23:30"),
    "daily-mart-lahore": ("09:00", "22:00"),
}

# base is the weekday order count before Friday/weekend, season and noise.
BRANCH_PROFILES = {
    "JT": {
        "slug": "lahore-grill-house",
        "kind": "restaurant",
        "base": 2,
        "weekend_boost": 1,
        "ramadan": True,
        "winter_boost": True,
        "hour_weights": {8: 2, 9: 3, 10: 3, 11: 2, 12: 2, 13: 3, 14: 2, 15: 1, 16: 1, 17: 2, 18: 3, 19: 5, 20: 5, 21: 4, 22: 3, 23: 1},
        "tag_boost": {"bbq": 2, "karahi": 2, "breakfast": 2, "bread": 1},
    },
    "DHA": {
        "slug": "lahore-grill-house",
        "kind": "restaurant",
        "base": 2,
        "weekend_boost": 1,
        "ramadan": True,
        "winter_boost": True,
        "hour_weights": {8: 1, 9: 1, 10: 1, 11: 1, 12: 2, 13: 3, 14: 2, 15: 1, 16: 1, 17: 2, 18: 3, 19: 5, 20: 6, 21: 5, 22: 3, 23: 1},
        "tag_boost": {"premium": 3, "karahi": 2, "deal": 1},
    },
    "GUL": {
        "slug": "urban-bites-lahore",
        "kind": "restaurant",
        "base": 3,
        "weekend_boost": 1,
        "ramadan": False,
        "winter_boost": False,
        "hour_weights": {12: 4, 13: 5, 14: 4, 15: 2, 16: 1, 17: 2, 18: 3, 19: 4, 20: 4, 21: 5, 22: 4, 23: 2},
        "tag_boost": {"burger": 3, "shawarma": 3, "pizza": 2},
    },
    "MT": {
        "slug": "urban-bites-lahore",
        "kind": "restaurant",
        "base": 2,
        "weekend_boost": 1,
        "ramadan": False,
        "winter_boost": False,
        "hour_weights": {12: 2, 13: 3, 14: 2, 15: 1, 16: 1, 17: 2, 18: 3, 19: 4, 20: 4, 21: 3, 22: 2, 23: 1},
        "tag_boost": {"burger": 2, "deal": 2, "pizza": 1},
    },
    "WT": {
        "slug": "daily-mart-lahore",
        "kind": "retail",
        "base": 2,
        "weekend_boost": 1,
        "ramadan": False,
        "winter_boost": False,
        "summer_boost": True,
        "hour_weights": {9: 3, 10: 4, 11: 3, 12: 2, 13: 2, 14: 1, 15: 1, 16: 2, 17: 4, 18: 5, 19: 4, 20: 3, 21: 2},
        "tag_boost": {"staple": 3},
    },
    "FT": {
        "slug": "daily-mart-lahore",
        "kind": "retail",
        "base": 1,
        "weekend_boost": 1,
        "ramadan": False,
        "winter_boost": False,
        "summer_boost": True,
        "hour_weights": {9: 2, 10: 3, 11: 2, 12: 2, 13: 1, 14: 1, 15: 1, 16: 2, 17: 3, 18: 4, 19: 4, 20: 3, 21: 2},
        "tag_boost": {"snack": 3, "beverage": 2},
    },
}

STATIONS = {
    "lahore-grill-house": [
        ("GRILL", "Charcoal grill", ("bbq", "premium")),
        ("KARAHI", "Karahi bench", ("karahi", "handi")),
        ("TANDOOR", "Tandoor", ("bread", "breakfast")),
        ("RICE", "Rice station", ("rice",)),
        ("FRY", "Fryer", ("chinese", "side")),
        ("COLD", "Cold section", ("drink", "dessert", "soup", "deal", "general")),
    ],
    "urban-bites-lahore": [
        ("GRIDDLE", "Burger griddle", ("burger", "deal", "premium", "general")),
        ("SHAW", "Shawarma", ("shawarma", "wrap")),
        ("OVEN", "Pizza oven", ("pizza", "pasta")),
        ("FRY", "Fryer", ("side", "chinese")),
        ("COLD", "Cold section", ("drink", "dessert")),
    ],
}
