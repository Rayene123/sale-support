"""One optional hosted model check using synthetic purchasing text only."""
from argparse import ArgumentParser
from getpass import getpass
import os
from unittest.mock import patch

from agent.specialist.planner import ModelUnavailable, OpenAIPlanner
from agent.specialist.setup_research import read_plan_findings

PROMPT = ("Find a desktop, two keyboards, and a mouse under 1,500 TND. "
          "The keyboards and mouse must connect to the desktop.")


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--ask-key", action="store_true", help="Read the key without echoing it")
    args = parser.parse_args()
    key = getpass("OpenAI key (hidden): ") if args.ask_key else os.environ.get("OPENAI_API_KEY", "")
    try:
        with patch.dict(os.environ, {"OPENAI_API_KEY": key.strip()}):
            result = OpenAIPlanner.from_env().plan(PROMPT)
    except ModelUnavailable as error:
        print(f"OpenAI planner unavailable: {error}")
        return 1
    found = sorted((item.kind, item.quantity) for item in result.items)
    links = {frozenset((link.source, link.target)) for link in result.links if link.kind == "usb"}
    ids = {item.kind: item.id for item in result.items}
    expected = [("desktop",1), ("keyboard",2), ("mouse",1)]
    correct = (found == expected and not result.missing() and not read_plan_findings(result, PROMPT)
               and all(frozenset((ids["desktop"], ids[role])) in links for role in ("keyboard", "mouse")))
    print("Parsed item kinds and quantities:", found)
    print("USB relationships:", len(links))
    print("Result:", "PASS" if correct else "FAIL")
    return int(not correct)


if __name__ == "__main__":
    raise SystemExit(main())
