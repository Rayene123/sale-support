"""Local measurements and optional, allowlisted LangSmith traces."""
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import json
import os
from queue import Full, Queue
from threading import Lock, Thread
from time import perf_counter


_active = ContextVar("specialist_observation", default=None)


def model_attempt():
    observation = _active.get()
    if observation is not None:
        observation["model_calls"] += 1


def model_tokens(response):
    observation = _active.get()
    if observation is not None and isinstance(response, dict):
        observation["model_usage"].append({
            name: response[key] if type(response.get(key)) is int and response[key] >= 0 else None
            for name, key in (("input_tokens", "prompt_eval_count"), ("output_tokens", "eval_count"))
        })


def capture_event(event):
    observation = _active.get()
    if observation is not None:
        observation["events"].append({key: event[key] for key in
            ("actor", "action", "at", "elapsed_ms", "remaining_steps", "revision")})


class Observability:
    def __init__(self, path, *, exporter=None):
        self.path = path
        self.lock = Lock()
        self.queue = None
        if exporter:
            self.queue = Queue(maxsize=32)
            Thread(target=self._export, args=(exporter,), daemon=True).start()

    def _export(self, exporter):
        while True:
            payload = self.queue.get()
            try:
                exporter(payload)
            except Exception:
                # A telemetry outage cannot fail a case or replay a sandbox action.
                pass
            finally:
                self.queue.task_done()

    def run(self, command, call):
        started = perf_counter()
        record = {"command": command, "started_at": datetime.now(timezone.utc).isoformat(),
                  "model_calls": 0, "model_usage": [], "events": [], "status": "error"}
        token = _active.set(record)
        try:
            result = call()
            record.update({key: result[key] for key in ("case_id", "run_id", "revision", "status")})
            return result
        finally:
            _active.reset(token)
            record["latency_ms"] = round((perf_counter() - started) * 1000, 2)
            with self.lock:
                try:
                    with self.path.open("a", encoding="utf-8") as log:
                        log.write(json.dumps(record) + "\n")
                except OSError:
                    pass
            if self.queue is not None:
                try:
                    self.queue.put_nowait(record)
                except Full:
                    pass


def langsmith_exporter():
    key = os.getenv("LANGSMITH_API_KEY")
    if os.getenv("LANGSMITH_TRACING", "").lower() != "true" or not key:
        return None
    from langsmith import Client
    from langsmith.run_trees import RunTree

    project = os.getenv("LANGSMITH_PROJECT", "the-specialist")
    client = Client(api_url="https://api.smith.langchain.com", api_key=key,
                    auto_batch_tracing=False, timeout_ms=2500, omit_traced_runtime_info=True)

    def export(record):
        start = datetime.fromisoformat(record["started_at"])
        ids = {key: record[key] for key in ("case_id", "run_id", "revision") if key in record}
        root = RunTree(name="specialist." + record["command"], inputs=ids, client=client,
                       project_name=project, start_time=start, run_type="chain")
        root.end(outputs={"status": record["status"], "model_calls": record["model_calls"],
                          "model_usage": record["model_usage"]},
                 end_time=start + timedelta(milliseconds=record["latency_ms"]))
        root.post()
        for event in record["events"]:
            end = datetime.fromisoformat(event["at"])
            child = root.create_child(
                name=f"{event['actor']}.{event['action']}",
                run_type="tool" if event["actor"] in {"researcher", "sandbox"} else "chain",
                start_time=end - timedelta(milliseconds=event["elapsed_ms"]),
                inputs={"revision": event["revision"]},
            )
            child.end(outputs={"remaining_steps": event["remaining_steps"]}, end_time=end)
            child.post()

    return export
