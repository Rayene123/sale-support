"""A fictional catalog used by the local review app and broader offline evaluations."""
from copy import deepcopy
from datetime import datetime, timezone
from unicodedata import normalize

from .specialist_fixtures import Catalog, product


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
