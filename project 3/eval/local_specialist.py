"""Opt-in benchmark using the installed local LLM and fixed catalog ground truth."""
from argparse import ArgumentParser
from dataclasses import dataclass
import json
from math import ceil
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.observability import Observability
from agent.specialist.coordinator import Specialist
from agent.specialist.planner import OllamaPlanner
from agent.specialist.store import CaseStore

from .hybrid_smoke import CHECK_PROMPT, PROMPT
from .specialist_demo_catalog import DemoCatalog


@dataclass(frozen=True)
class Scenario:
    name: str
    prompt: str
    status: str
    items: tuple[tuple[str, int], ...] = ()
    card_length: str | None = "300 mm"


PROPOSAL = "awaiting_approval"
BLOCKED = "verification_blocked"
CASES = (
    Scenario("direct_display", "Find a new laptop and an external monitor that connect under 2900 TND total.",
             PROPOSAL, (("L1", 1), ("M1", 1))),
    Scenario("three_types_and_quantities", PROMPT, PROPOSAL, (("D1", 1), ("K1", 2), ("P1", 1))),
    Scenario("network_pair", "Find a new router and a new network switch with a wired Ethernet link under 250 TND total.",
             PROPOSAL, (("R1", 1), ("S1", 1))),
    Scenario("physical_fit", CHECK_PROMPT, PROPOSAL, (("C100", 1), ("G300", 1))),
    Scenario("card_too_long", CHECK_PROMPT, BLOCKED, card_length="330 mm"),
    Scenario("unknown_card_length", CHECK_PROMPT, BLOCKED, card_length=None),
    Scenario("over_budget", "Find all new equipment under 100 TND total: a desktop and a wired USB keyboard.",
             BLOCKED),
    Scenario("clarify_budget", "Find a new desktop computer.", "awaiting_clarification"),
)


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[ceil(fraction * len(ordered)) - 1]


def evaluate(output):
    planner = OllamaPlanner.from_env()
    results = []
    with TemporaryDirectory() as temp:
        folder = Path(temp)
        metrics = folder / "metrics.jsonl"
        observer = Observability(metrics)
        store = CaseStore(folder / "cases.db")
        for scenario in CASES:
            catalog = DemoCatalog()
            attrs = catalog.rows["G300"]["characteristics"]
            if scenario.card_length is None:
                attrs.pop("GPU length")
            else:
                attrs["GPU length"] = scenario.card_length
            service = Specialist(store, catalog.researcher(), planner=planner)
            case = observer.run("start", lambda: service.start("C-001", scenario.prompt))
            proposal = case.get("proposal")
            actual = sorted((item["product_id"], item["quantity"])
                            for item in proposal["actions"][0]["payload"]["items"]) if proposal else []
            expected = sorted(scenario.items)
            match = case["status"] == scenario.status and actual == expected
            results.append({"case": scenario.name, "expected_status": scenario.status, "status": case["status"],
                            "expected_items": expected, "items": actual, "correct": match,
                            "false_positive": bool(proposal) and not expected,
                            "questions": case.get("questions", []),
                            "findings": [[f["code"], f["verdict"]] for f in case["findings"]]})
            print(f"{scenario.name}: {'PASS' if match else 'FAIL'} ({case['status']})", flush=True)
        measurements = [json.loads(line) for line in metrics.read_text(encoding="utf-8").splitlines()]
    for result, measured in zip(results, measurements, strict=True):
        result.update(latency_ms=measured["latency_ms"], model_calls=measured["model_calls"],
                      catalog_calls=sum(e["actor"] == "researcher" and e["action"] in
                                        {"search_catalog", "inspect_listing"} for e in measured["events"]),
                      model_usage=measured["model_usage"])
    latency = [row["latency_ms"] for row in results]
    report = {"model": planner.model, "catalog": "fictional fixtures", "cases": results,
              "summary": {"correct": sum(row["correct"] for row in results), "cases": len(results),
                          "false_positives": sum(row["false_positive"] for row in results),
                          "p50_ms": percentile(latency, .50), "p95_ms": percentile(latency, .95),
                          "provider_fee_per_100_runs": 0, "local_hardware_and_electricity_cost": None}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report["summary"]


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".specialist/local-benchmark.json"))
    args = parser.parse_args()
    summary = evaluate(args.output)
    print(json.dumps(summary, indent=2))
    return int(summary["cases"] != summary["correct"])


if __name__ == "__main__":
    raise SystemExit(main())
