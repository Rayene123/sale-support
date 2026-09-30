"""Send generated replies to Person 3's LLM judge and record every grade.

The judge is used as a library (``judge.Judge``) so the harness controls the
pipeline, the error taxonomy, and the row schema. Saved judge results can be
replayed instead, which keeps a report reproducible without a running model.
"""
from judge.client import JudgeError

from .errors import HarnessError, category_for_judge_kind
from .results import read_rows

MAX_REASON_CHARACTERS = 400


def judge_usage(usage):
    """Normalise a judge client's usage dict into the harness token shape.

    ``judge.client`` reports ``prompt_tokens``/``completion_tokens``; the
    metrics code works in ``prompt``/``completion``/``total``. A number the
    provider did not report stays ``None`` so an unmeasured token count is
    never read as zero.
    """
    usage = usage if isinstance(usage, dict) else {}
    prompt = usage.get("prompt_tokens", usage.get("prompt"))
    completion = usage.get("completion_tokens", usage.get("completion"))
    total = usage.get("total_tokens", usage.get("total"))
    if total is None and (prompt is not None or completion is not None):
        total = (prompt or 0) + (completion or 0)
    return {"prompt": prompt, "completion": completion, "total": total}


def _base_row(system_row):
    return {
        "item_id": system_row["item_id"],
        "response_id": system_row.get("response_id"),
        "status": "error",
        "judged": False,
        "scores": None,
        "reason": None,
        "judge_model": None,
        "judge_prompt_version": None,
        "judge_prompt_sha256": None,
        "judge_latency_ms": None,
        "judge_usage": {"prompt": None, "completion": None, "total": None},
        "judge_declared_total": None,
        "judge_total_corrected": False,
        "source": "live",
        "error": None,
    }


def run_judge(judge, items, system_rows, sink=None, skip_ids=(), limit=None):
    """Grade every successful system reply once, continuing after failures."""
    index = {item["id"]: item for item in items}
    rows, produced = [], 0
    for system_row in system_rows:
        if system_row.get("status") != "ok":
            continue
        item_id = system_row["item_id"]
        if item_id in skip_ids:
            continue
        if limit is not None and produced >= limit:
            break
        produced += 1
        row = _base_row(system_row)
        item = index.get(item_id)
        if item is None:
            row["error"] = {"category": "missing_field", "type": "DatasetError",
                            "message": f"No dataset item for {item_id}", "metadata": {}}
            rows.append(row)
            if sink:
                sink(row)
            continue
        try:
            grade = judge.grade(item["customer_message"], item["order_context"],
                                system_row["response_text"])
        except JudgeError as exc:
            row["error"] = {"category": category_for_judge_kind(exc.kind),
                            "type": exc.kind, "message": str(exc), "metadata": exc.metadata}
            row["judge_latency_ms"] = round(exc.metadata["latency_ms"], 2) if "latency_ms" in exc.metadata else None
            row["judge_usage"] = judge_usage(exc.metadata.get("usage"))
            rows.append(row)
            if sink:
                sink(row)
            continue
        except Exception as exc:  # a defect here must not lose the whole run
            row["error"] = {"category": "internal", "type": type(exc).__name__,
                            "message": str(exc), "metadata": {}}
            rows.append(row)
            if sink:
                sink(row)
            continue
        usage = grade.get("usage") or {}
        row.update({
            "status": "ok",
            "judged": True,
            "scores": grade["scores"],
            "reason": (grade.get("reason") or "")[:MAX_REASON_CHARACTERS],
            "judge_model": grade.get("response_model") or judge.model,
            "judge_prompt_version": grade.get("prompt_version"),
            "judge_prompt_sha256": grade.get("prompt_sha256"),
            "judge_latency_ms": round(grade["latency_ms"], 2) if "latency_ms" in grade else None,
            "judge_usage": judge_usage(usage),
            "judge_declared_total": grade.get("declared_total"),
            "judge_total_corrected": bool(grade.get("total_corrected")),
        })
        rows.append(row)
        if sink:
            sink(row)
    return rows


def replay_judge(results_path, system_rows, sink=None, require_text_match=True):
    """Reuse saved judge grades.

    The saved text is compared with the reply the harness holds. A mismatch is
    recorded as an error instead of being silently attributed to this run.
    """
    saved = read_rows(results_path)
    if not saved:
        raise HarnessError("configuration", f"No saved judge results in {results_path}")
    system_index = {row["item_id"]: row for row in system_rows}
    rows = []
    for record in saved:
        item_id = record.get("item_id")
        system_row = system_index.get(item_id)
        if system_row is None:
            continue
        row = _base_row(system_row)
        row["source"] = "replay"
        row["replayed_from"] = str(results_path)
        saved_text = record.get("response_text")
        if require_text_match and isinstance(saved_text, str) and saved_text != system_row.get("response_text"):
            row["error"] = {"category": "dataset_error", "type": "ValueError",
                            "message": "Saved judge grade refers to a different reply text",
                            "metadata": {}}
            rows.append(row)
            if sink:
                sink(row)
            continue
        if record.get("status") != "ok" or not isinstance(record.get("result"), dict):
            error = {"category": "judge_error", "type": "replayed_failure",
                     "message": "Saved judge call failed in the original run",
                     "metadata": record.get("error_type")}
            row["error"] = error
            rows.append(row)
            if sink:
                sink(row)
            continue
        grade = record["result"]
        usage = grade.get("usage") or {}
        scores = grade.get("scores")
        row.update({
            "status": "ok",
            "judged": True,
            "scores": scores,
            "reason": (grade.get("reason") or "")[:MAX_REASON_CHARACTERS],
            "judge_model": grade.get("response_model"),
            "judge_prompt_version": grade.get("prompt_version"),
            "judge_prompt_sha256": grade.get("prompt_sha256"),
            "judge_latency_ms": round(grade["latency_ms"], 2) if isinstance(grade.get("latency_ms"), (int, float)) else None,
            "judge_usage": judge_usage(grade.get("usage")),
            "judge_declared_total": grade.get("declared_total"),
            "judge_total_corrected": bool(grade.get("total_corrected")),
        })
        rows.append(row)
        if sink:
            sink(row)
    if not rows:
        raise HarnessError("configuration",
                           f"{results_path} has no grades for the replies in this run")
    return rows
