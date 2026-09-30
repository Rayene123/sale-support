"""Run the evaluated customer-support system over the dataset.

One model call per item, no agents, no retrieval, no retries. Every item
produces exactly one row containing the reply, latency, token usage, and the
prompt version used, or a categorised error.
"""
from .dataset import text_warnings
from .errors import SystemError
from .prompts import build_user_message


def _base_row(item, prompt_version, prompt_sha256, response_id, source):
    return {
        "item_id": item["id"],
        "split": item.get("split"),
        "category": item.get("category"),
        "difficulty": item.get("difficulty"),
        "response_id": response_id,
        "prompt_version": prompt_version,
        "system_prompt_sha256": prompt_sha256,
        "source": source,
        "status": "error",
        "requests": 0,
        "system_model": None,
        "response_text": None,
        "latency_ms": None,
        "tokens": {"prompt": None, "completion": None, "total": None},
        "warnings": [],
        "error": None,
    }


def run_system(client, items, prompt_version, prompt_sha256, response_id="system",
               sink=None, skip_ids=(), limit=None, source="live"):
    """Generate one reply per item.

    ``sink`` receives each row as soon as it is produced so an interrupted run
    keeps its completed work. ``skip_ids`` supports ``--resume``.
    """
    rows, produced = [], 0
    for item in items:
        if item["id"] in skip_ids:
            continue
        if limit is not None and produced >= limit:
            break
        produced += 1
        row = _base_row(item, prompt_version, prompt_sha256, response_id, source)
        try:
            result = client.generate(build_user_message(item))
        except SystemError as exc:
            row["error"] = {"category": exc.kind, "type": type(exc).__name__, "message": str(exc),
                            "metadata": exc.metadata}
            row["latency_ms"] = exc.metadata.get("latency_ms")
            rows.append(row)
            if sink:
                sink(row)
            continue
        row.update({
            "status": "ok",
            "requests": 1,
            "system_model": result["response_model"] or client.config.model,
            "response_text": result["text"],
            "latency_ms": round(result["latency_ms"], 2),
            "tokens": result["usage"],
            "warnings": text_warnings(result["text"]),
        })
        if result.get("decode_tokens_per_second"):
            row["decode_tokens_per_second"] = round(result["decode_tokens_per_second"], 3)
        rows.append(row)
        if sink:
            sink(row)
    return rows


def replay_system(responses, items, prompt_version, prompt_sha256, sink=None, response_id=None):
    """Reuse replies that were already generated (Person 4's saved runs).

    No model is called, so no latency or usage is invented: the values saved
    with the original run are carried over and marked ``source="replay"``.
    """
    known = {item["id"]: item for item in items}
    rows = []
    for response in responses:
        item = known.get(response["item_id"])
        if item is None:
            raise SystemError("dataset_error",
                              f"Saved response for unknown item {response['item_id']!r}")
        text = response.get("response_text")
        identifier = response_id or response.get("response_id") or "system"
        row = _base_row(item, prompt_version, prompt_sha256, identifier, "replay")
        if not isinstance(text, str) or not text.strip():
            row["error"] = {"category": "system_error", "type": "SystemError",
                            "message": "Saved response is empty", "metadata": {}}
            rows.append(row)
            if sink:
                sink(row)
            continue
        row.update({
            "status": "ok",
            "requests": 0,
            "system_model": response.get("system_model"),
            "response_text": text,
            "latency_ms": response.get("system_latency_ms"),
            "tokens": response.get("system_tokens") or {"prompt": None, "completion": None, "total": None},
            "warnings": text_warnings(text),
            "replayed_from": response.get("source_file"),
            "replayed_prompt_version": response.get("system_prompt_version"),
        })
        recorded = response.get("system_prompt_version")
        if recorded and recorded != prompt_version:
            # Person 4's baseline_v2.jsonl is recorded as prompt_version v1; a
            # mismatch must be visible instead of silently relabelling the run.
            row["warnings"] = row["warnings"] + ["prompt_version_mismatch"]
        rows.append(row)
        if sink:
            sink(row)
    return rows
