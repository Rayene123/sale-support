import json
import os
import sys
import time
from pathlib import Path

from groq import Groq


PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system_v2.txt"


def load_system_prompt():
    return PROMPT_PATH.read_text(encoding="utf-8")


def generate_response(client, model, system_prompt, item):
    customer_message = item["customer_message"]
    order_context = item["order_context"]

    user_message = (
        "Customer message:\n"
        f"{customer_message}\n\n"
        "Order context:\n"
        f"{json.dumps(order_context, ensure_ascii=False, indent=2)}"
    )

    start_time = time.perf_counter()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_message,
            },
        ],
    )

    latency_ms = (time.perf_counter() - start_time) * 1000
    usage = response.usage

    return {
        "id": item.get("id"),
        "response": response.choices[0].message.content,
        "model": model,
        "latency_ms": round(latency_ms, 2),
        "prompt_tokens": usage.prompt_tokens if usage else None,
        "completion_tokens": usage.completion_tokens if usage else None,
        "total_tokens": usage.total_tokens if usage else None,
        "prompt_version": "v2",
    }


def main():
    # Force UTF-8 output on Windows.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL")

    if not api_key:
        print(
            "ERROR: GROQ_API_KEY environment variable is not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not model:
        print(
            "ERROR: GROQ_MODEL environment variable is not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = Groq(api_key=api_key)
    system_prompt = load_system_prompt()

    for line in sys.stdin:
        line = line.strip()

        if not line:
            continue

        try:
            item = json.loads(line)

            result = generate_response(
                client,
                model,
                system_prompt,
                item,
            )

            print(json.dumps(result, ensure_ascii=False))

        except Exception as exc:
            print(
                json.dumps(
                    {
                        "error": str(exc),
                        "id": item.get("id") if "item" in locals() else None,
                    },
                    ensure_ascii=False,
                )
            )


if __name__ == "__main__":
    main()
