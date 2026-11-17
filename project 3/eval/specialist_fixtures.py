"""Fictional retailer snapshots exercising exact model and connection checks."""
from copy import deepcopy
from datetime import datetime, timezone

from agent.specialist.research import Researcher


def product(id, name, price, specs, stock="in_stock"):
    return {"product_id": id, "name": name, "price_tnd": price, "characteristics": specs,
            "source_url": f"https://www.tunisianet.com.tn/{id}.html", "availability": stock,
            "retrieved_at": datetime.now(timezone.utc).isoformat()}


class Catalog:
    def __init__(self):
        self.rows = {
            "L0": product("L0", "Laptop Entry", "1350.00", {"RAM": "8 GB", "Storage": "256 GB SSD",
                          "Video outputs": "USB-C data only"}),
            "L1": product("L1", "Laptop Studio", "1800.00", {"RAM": "16 GB", "Storage": "512 GB SSD",
                          "Video outputs": "HDMI 2560x1440 @ 120 Hz"}),
            "L2": product("L2", "Laptop Workstation", "2100.00", {"RAM": "32 GB", "Storage": "1 TB SSD",
                          "Video outputs": "DisplayPort 2560x1440 @ 165 Hz"}),
            "M0": product("M0", "Monitor Entry", "450.00", {"Screen size": "24 inch",
                          "Native resolution": "1920x1080", "Refresh rate": "60 Hz", "Video inputs": "VGA"}),
            "M1": product("M1", "Monitor Studio", "830.00", {"Screen size": "27 inch",
                          "Native resolution": "2560x1440", "Refresh rate": "120 Hz",
                          "Video inputs": "HDMI 2560x1440 @ 120 Hz"}),
            "M2": product("M2", "Monitor Motion", "890.00", {"Screen size": "27 inch",
                          "Native resolution": "2560x1440", "Refresh rate": "165 Hz",
                          "Video inputs": "DisplayPort 2560x1440 @ 165 Hz"}),
        }
        self.queries = {"pc portable": ["L0", "L1"], "ordinateur portable": ["L1", "L2"],
                        "écran pc": ["M0", "M1"], "moniteur": ["M1", "M2"]}
        self.lookups = []

    def search(self, query, *, max_results):
        self.lookups.append(("search", query))
        return {"success": True, "data": {"products": [deepcopy(self.rows[id])
                for id in self.queries.get(query, []) if id in self.rows][:max_results]}}

    def inspect(self, product_id, url):
        self.lookups.append(("inspect", product_id))
        row = self.rows.get(product_id)
        if row is None or url != row["source_url"]:
            return {"success": False, "error": "product_identity_unknown"}
        return {"success": True, "data": deepcopy(row)}

    def researcher(self):
        return Researcher(self.search, self.inspect)
