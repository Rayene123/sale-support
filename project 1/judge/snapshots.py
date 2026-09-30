"""Preserve historical code once per comparison, verifying reused content."""
import hashlib
import os
from pathlib import Path


def save_snapshot(output, shared=None, prompt=""):
    directory = Path(shared) if shared else Path(output) / "snapshot"
    sources = {name: (Path(__file__).parent / name).read_bytes()
               for name in ("client.py", "run.py")}
    sources["judge_prompt.txt"] = prompt.encode("utf-8")
    for name, content in sources.items():
        path = directory / name
        if path.exists() and path.read_bytes() != content:
            raise ValueError(f"Snapshot content differs: {path}")
    directory.mkdir(parents=True, exist_ok=True)
    result = {}
    for name, content in sources.items():
        path = directory / name
        if not path.exists():
            path.write_bytes(content)
        result[name] = {"path": Path(os.path.relpath(path, output)).as_posix(),
                        "sha256": hashlib.sha256(content).hexdigest()}
    return result
