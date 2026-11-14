"""
Feature contract shared by offline training and online serving.

RULES (Phase 2's Redis extractor MUST follow these exactly):
  * Timestamps are integer milliseconds.
  * Window features cover (t - window, t] and INCLUDE the current transaction
    (online: ZADD current event first, then ZCOUNT / sum over the window).
  * `hist_mean` = mean of the card's PREVIOUS transaction amounts (excludes
    current). If the card has no history, hist_mean = current amount.
    The card profile is updated AFTER scoring.
      amount_ratio    = amount / hist_mean
      spend_ratio_1h  = (sum of amounts in the 1h window) / hist_mean
"""

FEATURE_NAMES = [
    "amount",
    "hour",
    "merchant_cat",
    "is_online",
    "distance_km",
    "is_foreign",
    "account_age_days",
    "txn_count_1m",
    "txn_count_10m",
    "txn_count_1h",
    "amount_ratio",
    "spend_ratio_1h",
]

WINDOWS_MS = {"1m": 60_000, "10m": 600_000, "1h": 3_600_000}

MERCHANT_CATEGORIES = [
    "grocery", "restaurant", "fuel", "retail", "travel",
    "entertainment", "utilities", "electronics", "luxury_goods", "crypto_giftcards",
]

# Features (plus the model score) monitored for drift in Phase 2
PSI_FEATURES = [
    "amount", "distance_km", "txn_count_1h", "amount_ratio",
    "spend_ratio_1h", "account_age_days", "hour", "merchant_cat", "is_online",
]