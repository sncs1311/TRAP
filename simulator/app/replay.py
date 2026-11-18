"""Optional CSV replay (Kaggle 'Credit Card Transactions Fraud Detection' schema)."""
from __future__ import annotations

import csv
import math
import zlib
from pathlib import Path

REQUIRED = {"cc_num", "category", "amt", "lat", "long", "merch_lat", "merch_long",
            "trans_date_trans_time", "is_fraud"}

CAT_MAP = {
    "grocery_pos": 0, "grocery_net": 0, "food_dining": 1, "gas_transport": 2,
    "shopping_pos": 3, "home": 3, "misc_pos": 3, "kids_pets": 3, "travel": 4,
    "entertainment": 5, "personal_care": 6, "health_fitness": 6,
    "shopping_net": 7, "misc_net": 7,
}


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def row_to_event(row: dict) -> dict:
    cat, cc = row["category"], row["cc_num"]
    dist = haversine_km(float(row["lat"]), float(row["long"]),
                        float(row["merch_lat"]), float(row["merch_long"]))
    return {
        "card_id": cc, "amount": max(round(float(row["amt"]), 2), 0.01),
        "merchant_cat": CAT_MAP.get(cat, 3), "is_online": int(cat.endswith("_net")),
        "distance_km": round(dist, 2), "is_foreign": 0,
        "account_age_days": 30 + zlib.crc32(cc.encode()) % 3000,     # dataset has no account age
        "hour": int(row["trans_date_trans_time"][11:13]),
        "label": int(row["is_fraud"]), "pattern": "replay",
    }


class CsvReplay:
    def __init__(self, path: Path, limit: int | None = None, loop: bool = False):
        self.path, self.limit, self.loop = path, limit, loop
        self.count, self.done, self._got = 0, False, 0
        self._open()

    def _open(self) -> None:
        self.f = open(self.path, newline="", encoding="utf-8")
        self.reader = csv.DictReader(self.f)
        missing = REQUIRED - set(self.reader.fieldnames or [])
        if missing:
            self.f.close()
            raise ValueError(f"CSV is missing columns: {sorted(missing)}")

    def _end(self) -> None:
        self.f.close()
        if self.loop and self._got > 0:
            self._open()
            self._got, self.count = 0, 0
        else:
            self.done = True

    def next_batch(self, n: int) -> list[dict]:
        out: list[dict] = []
        while len(out) < n and not self.done:
            if self.limit is not None and self.count >= self.limit:
                self._end()
                break
            try:
                row = next(self.reader)
            except StopIteration:
                self._end()
                continue
            out.append(row_to_event(row))
            self.count += 1
            self._got += 1
        return out