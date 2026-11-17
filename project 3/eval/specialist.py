"""Compare fixed, adaptive, and independently verified research on the same inputs."""
from argparse import ArgumentParser
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory
from time import perf_counter

from agent.specialist.coordinator import Specialist
from agent.specialist.store import CaseStore
from eval.specialist_fixtures import Catalog


PAIR = "Find a laptop and monitor under 3,000 TND"
QUALIFIED = "Find a 16 GB laptop and 27-inch monitor under 2,900 TND at 1440p 120 Hz"
MODES = ("fixed", "adaptive", "adaptive_verifier")

# Expected product identities, rather than the verifier verdict, are the scoring oracle.
CASES = [
    ("original request", "Find a programming laptop and compatible monitor under 3,000 TND", ["L1", "M1"], {}),
    ("1440p at 120 Hz", QUALIFIED, ["L1", "M1"], {}),
    ("adaptive 165 Hz", "Find a 32 GB laptop and a monitor under 3,100 TND at 1440p 165 Hz", ["L2", "M2"], {}),
    ("displayport required", PAIR + " via DisplayPort", ["L2", "M2"], {}),
    ("HDMI required", PAIR + " via HDMI", ["L1", "M1"], {}),
    ("French catalog terms", "Cherche un ordinateur portable et un moniteur sous 3 000 TND", ["L1", "M1"], {}),
    ("exact combined budget", "Find a laptop and monitor under 2630 TND", ["L1", "M1"], {}),
    ("below verified pair", "Find a laptop and monitor under 2629 TND", None, {}),
    ("no shared video transport", PAIR, None, {"M1": {"Video inputs": "VGA"}, "M2": {"Video inputs": "VGA"}}),
    ("USB-C data only", PAIR, None, {"L1": {"Video outputs": "USB-C data only"}, "L2": {"Video outputs": "USB-C data only"}}),
    ("bare USB-C on both products", PAIR + " via USB-C", None, {"L1": {"Video outputs": "USB-C"}, "M1": {"Video inputs": "USB-C"}}),
    ("confirmed USB-C DP Alt Mode", PAIR + " via USB-C", ["L1", "M1"], {
        "L1": {"Video outputs": "USB-C supports DisplayPort Alt Mode"}, "M1": {"Video inputs": "USB-C DisplayPort Alt Mode"}}),
    ("only monitor shows refresh rate", QUALIFIED, None, {"L1": {"Video outputs": "HDMI"}}),
    ("monitor mode is too slow", QUALIFIED, None, {"M1": {"Video inputs": "HDMI 2560x1440 @ 60 Hz"}}),
    ("native monitor resolution differs", QUALIFIED, None, {"M1": {"Native resolution": "1920x1080"}}),
    ("wrong laptop port direction", QUALIFIED, None, {"L1": {"Video outputs": "", "Video inputs": "HDMI 2560x1440 @ 120 Hz"}}),
    ("unknown stock", QUALIFIED, None, {"L1": {"_stock": "unknown"}}),
    ("out of stock", QUALIFIED, None, {"L1": {"_stock": "out_of_stock"}}),
    ("alternative after out-of-stock item", PAIR, ["L2", "M2"], {"L1": {"_stock": "out_of_stock"}}),
    ("price missing", QUALIFIED, None, {"L1": {"_price": None}}),
    ("expired exact listing", QUALIFIED, None, {"L1": {"_old": True}}),
    ("RAM too low", "Find a laptop with 64 GB RAM and monitor under 4,000 TND", None, {}),
    ("RAM evidence missing", QUALIFIED, None, {"L1": {"RAM": ""}}),
    ("RAM evidence clashes", QUALIFIED, None, {"L1": {"RAM (detail table)": "8 GB"}}),
    ("monitor size not met", "Find a laptop and 32-inch monitor under 3000 TND", None, {}),
    ("missing monitor size proof", QUALIFIED, None, {"M1": {"Screen size": ""}}),
    ("storage requires broader search", "Find a laptop with 1 TB SSD and monitor under 3,100 TND", ["L2", "M2"], {}),
    ("standalone laptop", "Find a 16 GB laptop under 1900 TND", ["L1"], {}),
    ("standalone 1080p screen", "Find a 24-inch monitor under 500 TND at 1080p 60 Hz", ["M0"], {}),
    ("one item per category", "Find a laptop and 27-inch monitor under 3,000 TND", ["L1", "M1"], {}),
]


def fixture(changes):
    catalog = Catalog()
    for sku, fields in changes.items():
        for field, value in fields.items():
            if field == "_stock":
                catalog.rows[sku]["availability"] = value
            elif field == "_price":
                catalog.rows[sku]["price_tnd"] = value
            elif field == "_old":
                catalog.rows[sku]["retrieved_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            else:
                catalog.rows[sku]["characteristics"][field] = value
    return catalog


def run_comparison(path):
    rows = []
    with TemporaryDirectory(prefix="specialist-eval-") as root:
        store = CaseStore(Path(root) / "cases.sqlite3")
        for mode in MODES:
            for name, prompt, expected, changes in CASES:
                catalog = fixture(changes)
                worker = Specialist(store, catalog.researcher(), mode=mode)
                started = perf_counter()
                outcome = worker.start("C-001", prompt)
                elapsed_ms = (perf_counter() - started) * 1000
                proposal, candidate = outcome["proposal"], outcome.get("candidate")
                evidence = proposal["evidence"] if proposal else candidate
                actual = [row["product_id"] for row in evidence.values()] if evidence else None
                rows.append({"case": name, "mode": mode, "expected": expected,
                             "actual": actual, "correct": actual == expected, "status": outcome["status"],
                             "false_positive": expected is None and actual is not None,
                             "tool_calls": len(catalog.lookups), "steps": outcome["steps"],
                             "latency_ms": round(elapsed_ms, 3),
                             "findings": [{"code": finding["code"], "verdict": finding["verdict"]}
                                          for finding in outcome["findings"]]})
    summary = {}
    for mode in MODES:
        cases = [row for row in rows if row["mode"] == mode]
        summary[mode] = {"cases": len(cases), "correct": sum(row["correct"] for row in cases),
                         "false_positives": sum(row["false_positive"] for row in cases),
                         "mean_tool_calls": round(mean(row["tool_calls"] for row in cases), 2),
                         "mean_latency_ms": round(mean(row["latency_ms"] for row in cases), 2)}
    result = {"baseline": "offline fictional catalog", "cost": "no provider calls",
              "summary": summary, "cases": rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("eval/results/specialist-comparison.json"))
    args = parser.parse_args()
    result = run_comparison(args.output)
    for mode, row in result["summary"].items():
        print(f"{mode}: {row['correct']}/{row['cases']} correct; {row['false_positives']} false positives; "
              f"{row['mean_tool_calls']} average tool calls")
    failures = [r for r in result["cases"] if r["mode"] == "adaptive_verifier" and not r["correct"]]
    for row in failures:
        print(f"FAIL {row['case']}: expected {row['expected']}, got {row['actual']}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
