"""
Calculate API benchmark cost.

Prices are entered in .env as USD per 1 million tokens.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]

SUMMARY_PATH = ROOT / "results" / "summary.csv"

load_dotenv(ROOT.parent / ".env")


def price(provider, kind):

    key = (
        f"{provider.upper()}_"
        f"{kind.upper()}_PRICE_PER_M"
    )

    value = os.getenv(key)

    if not value:
        return None

    return float(value)


def main():

    if not SUMMARY_PATH.exists():
        raise RuntimeError(
            "Run score.py first."
        )

    with SUMMARY_PATH.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:

        rows = list(csv.DictReader(file))

    print()
    print("=" * 60)
    print("API COST")
    print("=" * 60)

    for row in rows:

        provider = row["provider"]

        if provider == "ollama":
            print()
            print(
                f"{provider} / {row['model']}: "
                "local model — no API token cost"
            )
            continue

        input_price = price(
            provider,
            "input",
        )

        output_price = price(
            provider,
            "output",
        )

        if (
            input_price is None
            or output_price is None
        ):
            print()
            print(
                f"{provider} / {row['model']}: "
                "pricing not configured"
            )
            continue

        input_tokens = int(
            row["input_tokens"]
        )

        output_tokens = int(
            row["output_tokens"]
        )

        total_cost = (
            input_tokens
            / 1_000_000
            * input_price
            +
            output_tokens
            / 1_000_000
            * output_price
        )

        cost_per_1000 = (
            total_cost
            / int(row["items"])
            * 1000
        )

        print()
        print(
            f"{provider} / {row['model']}"
        )

        print(
            f"Total cost: "
            f"${total_cost:.6f}"
        )

        print(
            f"Cost per 1,000 requests: "
            f"${cost_per_1000:.6f}"
        )


if __name__ == "__main__":
    main()