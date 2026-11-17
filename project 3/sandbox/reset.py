
"""Reset the dedicated Sale Support Supabase sandbox."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from sandbox.store import SandboxStore, StoreError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT.parent / ".env"

logger = logging.getLogger(__name__)


def reset_supabase() -> None:
    """Safely restore the dedicated sandbox to its original fixtures."""

    # Load environment variables from the repository-root .env.
    load_dotenv(ENV_FILE)

    url = os.getenv("SUPABASE_URL")
    allowed_url = os.getenv("SUPABASE_SANDBOX_URL")

    # Require an explicit sandbox URL allowlist.
    if not url or not allowed_url:
        raise RuntimeError(
            "Sandbox configuration is missing. Check the root .env file."
        )

    if url.rstrip("/") != allowed_url.rstrip("/"):
        raise RuntimeError(
            "Reset refused: configured database is not the approved sandbox."
        )

    # Reuse the existing store connection and its safety checks.
    store = SandboxStore.from_env()

    if store.mode != "supabase" or store.client is None:
        raise RuntimeError("Reset requires a Supabase connection.")

    print("Connected to the approved sandbox.")
    # Migration 004 restores all fixtures and clears effects in one transaction.
    print("Calling the PostgreSQL reset function...")

    try:
        response = store.client.rpc(
            "reset_sale_support_sandbox"
        ).execute()

        result = response.data

    except Exception:
        logger.exception("Sandbox reset RPC failed")
        raise RuntimeError(
            "Sandbox reset failed. Check the database function and permissions."
        ) from None

    # Validate the response before reporting success.
    if not isinstance(result, dict) or result.get("success") is not True:
        raise RuntimeError(
            "The database did not confirm a successful reset."
        )

    expected_counts = {
        "customers": 10,
        "orders": 10,
        "tickets": 12,
    }

    for table, expected in expected_counts.items():
        actual = result.get(table)

        if actual != expected:
            raise RuntimeError(
                f"Unexpected reset count for {table}: "
                f"expected {expected}, received {actual}."
            )

    if result.get("operation_history_cleared") is not True:
        raise RuntimeError(
            "The reset did not confirm that operation history was cleared."
        )

    print("\nSandbox reset completed successfully.")
    print(f"Customers restored: {result['customers']}")
    print(f"Orders restored:    {result['orders']}")
    print(f"Tickets restored:   {result['tickets']}")
    print("Operation history:  cleared")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset the dedicated Sale Support sandbox."
    )

    parser.add_argument(
        "--supabase",
        action="store_true",
        help="Reset the approved Supabase sandbox.",
    )

    args = parser.parse_args()

    if not args.supabase:
        parser.error(
            "Specify --supabase to explicitly confirm the sandbox reset."
        )

    try:
        reset_supabase()
    except (RuntimeError, StoreError) as error:
        print(f"\nReset refused or failed: {error}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
