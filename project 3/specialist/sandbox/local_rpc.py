"""Transport for the same sandbox SQL on a local, persistent PGlite database."""
from contextlib import AbstractContextManager
import json
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace


class LocalSandbox(AbstractContextManager):
    def __init__(self, database: Path):
        runtime = Path(__file__).with_name("sql")
        database.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._process = subprocess.Popen(
            ["node", str(runtime / "local_rpc.mjs"), str(database.resolve())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding="utf-8",
        )
        try:
            if self._read() != {"ready": True}:
                raise RuntimeError("Local sandbox failed to initialize")
        except Exception:
            self.close()
            raise

    def _read(self):
        line = self._process.stdout.readline()
        if not line:
            raise RuntimeError("Local sandbox stopped. Check Node and the specialist/sandbox/sql dependencies.")
        return json.loads(line)

    def rpc(self, method, params=None):
        def execute():
            with self._lock:
                self._process.stdin.write(json.dumps({"method": method, "params": params or {}}) + "\n")
                self._process.stdin.flush()
                reply = self._read()
            if "error" in reply:
                raise RuntimeError(reply["error"])
            return SimpleNamespace(data=reply["data"])

        return SimpleNamespace(execute=execute)

    def close(self):
        self._process.stdin.close()
        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        self._process.stdout.close()

    def __exit__(self, *_exc):
        self.close()
