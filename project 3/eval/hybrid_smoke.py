"""One locally served model check using synthetic purchasing requests."""
from argparse import ArgumentParser
import re

from agent.specialist.planner import ModelUnavailable, OllamaPlanner
from agent.specialist.setup_research import read_plan_findings

PROMPT = ("I am buying all new equipment under 1,500 TND total: a desktop, "
          "two identical wired USB keyboards, and a wired USB mouse. "
          "All three peripherals must connect to the desktop.")
CHECK_PROMPT = ("Find a PC case and a graphics card under 2,000 TND. "
                "They have to fit together.")


def checks_clearance(plan):
    kinds = {item.id: item.kind for item in plan.items}
    for link in plan.links:
        case_is_source = re.search(r"boitier|case|chassis", kinds[link.source])
        case_is_target = re.search(r"boitier|case|chassis", kinds[link.target])
        for check in link.checks:
            print(f"{link.source} -> {link.target}:", check.source_field, check.comparison, check.target_field)
            if bool(case_is_source) == bool(case_is_target):
                continue
            case_field, card_field = (check.source_field, check.target_field) if case_is_source else (
                check.target_field, check.source_field)
            expected = "at_least" if case_is_source else "at_most"
            if (check.comparison == expected and re.search(r"max|clearance|dégagement", case_field, re.I)
                    and re.search(r"length|longueur", card_field, re.I)):
                return True
    return False


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--checks", action="store_true", help="Check the model's proposed clearance comparison")
    args = parser.parse_args()
    try:
        model = OllamaPlanner.from_env()
        result = model.plan(CHECK_PROMPT if args.checks else PROMPT)
    except (ModelUnavailable, ValueError) as error:
        print(f"Local planner unavailable: {error}")
        return 1
    found = sorted((item.kind, item.quantity) for item in result.items)
    questions = result.missing() + read_plan_findings(result, CHECK_PROMPT if args.checks else PROMPT)
    print("Local model:", model.model)
    print("Parsed item kinds and quantities:", found)
    if questions:
        print("Clarifications:", questions)
    if args.checks:
        clearance = checks_clearance(result)
        correct = len(found) == 2 and result.budget_tnd == 2000 and not questions and clearance
    else:
        links = {frozenset((link.source, link.target)) for link in result.links if link.kind == "usb"}
        ids = {item.kind: item.id for item in result.items}
        expected = [("desktop", 1), ("keyboard", 2), ("mouse", 1)]
        correct = (found == expected and not questions
                   and all(frozenset((ids["desktop"], ids[role])) in links for role in ("keyboard", "mouse")))
        print("USB relationships:", len(links))
    print("Result:", "PASS" if correct else "FAIL")
    return int(not correct)


if __name__ == "__main__":
    raise SystemExit(main())
