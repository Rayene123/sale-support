"""Fictional retailer snapshots exercising exact model and connection checks."""
from copy import deepcopy
from datetime import datetime, timezone
from unicodedata import normalize

from specialist.catalog.research import Researcher


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


class DemoCatalog(Catalog):
    def __init__(self):
        super().__init__()
        self.rows.update({
            "D1": product("D1", "Desktop Office", "1200", {"Ports": "3x USB-A"}),
            "K1": product("K1", "Clavier USB", "40", {
                "Ports": "1x USB-A", "Stock quantity": "8", "Connection type": "wired",
            }),
            "P1": product("P1", "Souris USB", "35", {"Ports": "1x USB-A", "Connection type": "wired"}),
            "C100": product("C100", "Boîtier PC Studio", "130", {
                "Maximum GPU length": "32 cm", "Compatible models": "GPU-300",
                "Supported GPU form factor": "full height",
            }),
            "G300": product("G300", "Carte graphique Studio", "800", {
                "MPN": "GPU-300", "GPU length": "300 mm", "GPU form factor": "full height",
            }),
            "R1": product("R1", "Routeur Ethernet", "120", {"Ports": "4x RJ45 Ethernet"}),
            "S1": product("S1", "Switch Ethernet", "100", {"Ports": "5x RJ45 Ethernet"}),
        })

    def search(self, query, *, max_results):
        text = normalize("NFKD", query.casefold()).encode("ascii", "ignore").decode()
        groups = (
            (("portable", "laptop", "notebook"), ("L1", "L2", "L0")),
            (("ecran", "moniteur", "monitor"), ("M1", "M2", "M0")),
            (("bureau", "desktop"), ("D1",)),
            (("clavier", "keyboard"), ("K1",)),
            (("souris", "mouse"), ("P1",)),
            (("boitier", "chassis", "case"), ("C100",)),
            (("carte graphique", "graphics card", "gpu"), ("G300",)),
            (("routeur", "router"), ("R1",)),
            (("switch", "commutateur"), ("S1",)),
        )
        ids = next((ids for terms, ids in groups if any(term in text for term in terms)), ())
        rows = [self._fresh(self.rows[id]) for id in ids if id in self.rows][:max_results]
        return {"success": True, "data": {"products": rows}}

    @staticmethod
    def _fresh(row):
        record = deepcopy(row)
        record["retrieved_at"] = datetime.now(timezone.utc).isoformat()
        return record

    def inspect(self, product_id, url):
        result = super().inspect(product_id, url)
        if result.get("success"):
            result["data"] = self._fresh(result["data"])
        return result
